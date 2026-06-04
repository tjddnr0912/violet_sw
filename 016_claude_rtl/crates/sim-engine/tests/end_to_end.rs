//! End-to-end sim-engine tests: build a SimIr via the real lex → parse →
//! elaborate pipeline, simulate it, and assert on captured $display output and
//! the generated VCD file.

use std::cell::RefCell;
use std::rc::Rc;

use diag::{LogEvent, LogSink};
use sim_engine::{simulate, simulate_capture, FinishReason, SimOpts};

// ── pipeline + sink helpers ────────────────────────────────────────────────

#[derive(Default)]
struct DiagSink(RefCell<Vec<String>>);
impl LogSink for DiagSink {
    fn emit(&self, e: LogEvent) {
        if let LogEvent::Diagnostic(d) = e {
            self.0
                .borrow_mut()
                .push(format!("{:?}: {}", d.severity, d.message));
        }
    }
}

fn build(src: &str) -> sim_ir::SimIr {
    let (toks, le) = hdl_lexer::lex(src);
    assert!(le.is_empty(), "lex errors: {le:?}");
    let (su, pe) = hdl_parser::parse(&toks, src);
    assert!(pe.is_empty(), "parse errors: {pe:?}");
    let sink = DiagSink::default();
    let ir = elaborate::elaborate(&su.expect("source unit"), &sink);
    let diags = sink.0.borrow();
    let hard: Vec<&String> = diags
        .iter()
        .filter(|d| d.starts_with("Error") || d.starts_with("Fatal"))
        .collect();
    assert!(hard.is_empty(), "elaborate errors: {hard:?}");
    ir.expect("elaborate returned None")
}

/// Elaborate `src` WITH the fork-mode side table and return `(ir, opts)` where
/// `opts` carries `fork_modes`. Existing non-fork tests keep using
/// `build()`/`SimOpts::default()` unchanged. Fork tests do:
///   `let (ir, opts) = build_fork(src); simulate_capture(&ir, opts);`
fn build_fork(src: &str) -> (sim_ir::SimIr, SimOpts) {
    let (toks, le) = hdl_lexer::lex(src);
    assert!(le.is_empty(), "lex errors: {le:?}");
    let (su, pe) = hdl_parser::parse(&toks, src);
    assert!(pe.is_empty(), "parse errors: {pe:?}");
    let sink = DiagSink::default();
    let (ir, fork_modes) = elaborate::elaborate_with_modes(&su.expect("source unit"), &sink);
    let diags = sink.0.borrow();
    let hard: Vec<&String> = diags
        .iter()
        .filter(|d| d.starts_with("Error") || d.starts_with("Fatal"))
        .collect();
    assert!(hard.is_empty(), "elaborate errors: {hard:?}");
    let ir = ir.expect("elaborate returned None");
    (
        ir,
        SimOpts {
            fork_modes,
            ..SimOpts::default()
        },
    )
}

/// A unique temp VCD path per test.
fn tmp_vcd(tag: &str) -> String {
    let mut p = std::env::temp_dir();
    p.push(format!("vita_sim_{}_{}.vcd", tag, std::process::id()));
    p.to_string_lossy().into_owned()
}

fn opts_with_vcd(path: &str) -> SimOpts {
    SimOpts {
        vcd_path_override: Some(path.to_string()),
        ..SimOpts::default()
    }
}

// ── 1. combinational assign y = a & b ──────────────────────────────────────

#[test]
fn comb_and_writes_correct_value() {
    let src = "module m; reg a; reg b; wire y; \
               assign y = a & b; \
               initial begin a = 1'b1; b = 1'b1; #1 $finish; end endmodule";
    let ir = build(src);
    let (res, _out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // After a=1,b=1 settle, y must be 1. We re-check via a $display variant below;
    // here we just assert the run finished cleanly at t>=1.
    assert!(res.sim_time >= 1);
}

#[test]
fn comb_and_display_truth() {
    // Drive all 4 input combos and print y each time.
    let src = "module m; reg a; reg b; wire y; \
               assign y = a & b; \
               initial begin \
                 a=0; b=0; #1 $display(\"%b\", y); \
                 a=0; b=1; #1 $display(\"%b\", y); \
                 a=1; b=0; #1 $display(\"%b\", y); \
                 a=1; b=1; #1 $display(\"%b\", y); \
                 $finish; \
               end endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(out, "0\n0\n0\n1\n", "AND truth table via continuous assign");
}

// ── 2. flip-flop q <= d on posedge clk ─────────────────────────────────────

#[test]
fn flipflop_follows_d_after_edge() {
    let src = "module m; reg clk; reg d; reg q; \
               always @(posedge clk) q <= d; \
               initial begin \
                 clk=0; d=1; q=0; \
                 #5 $display(\"before %b\", q); \
                 clk=1; \
                 #1 $display(\"after %b\", q); \
                 $finish; \
               end endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // q is 0 before the edge, follows d (=1) after the posedge.
    assert_eq!(out, "before 0\nafter 1\n");
}

// ── 3. initial begin a=1; #5 a=0; $finish advances time to 5 ───────────────

#[test]
fn delay_advances_time_and_finish_stops() {
    let src = "module m; reg a; \
               initial begin a=1; #5 a=0; $finish; end endmodule";
    let ir = build(src);
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(
        res.sim_time, 5,
        "time advanced to the #5 delay before $finish"
    );
}

// ── 4. $display formatting (%d %h %b %0d) ──────────────────────────────────

#[test]
fn display_format_specifiers() {
    let src = "module m; reg [7:0] v; \
               initial begin v = 8'd171; \
                 $display(\"d=%d h=%h b=%b z=%0d\", v, v, v, v); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // 171 = 0xAB = 0b10101011
    assert_eq!(out, "d=171 h=ab b=10101011 z=171\n");
}

// ── 5. NBA ordering: b<=a; c<=b gives OLD b ────────────────────────────────

#[test]
fn nba_uses_sampled_rhs() {
    // At the single posedge: a=5, b=0, c=0. NBA samples RHS (a→b gets 5, b→c
    // gets OLD b=0). So after edge: b=5, c=0 (NOT 5).
    let src = "module m; reg clk; reg [3:0] a; reg [3:0] b; reg [3:0] c; \
               always @(posedge clk) begin b <= a; c <= b; end \
               initial begin \
                 clk=0; a=4'd5; b=4'd0; c=4'd0; \
                 #5 clk=1; \
                 #1 $display(\"b=%0d c=%0d\", b, c); \
                 $finish; \
               end endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(out, "b=5 c=0\n", "NBA samples old b for c");
}

#[test]
fn nba_shifts_one_stage_per_clock() {
    // Two clock pulses: stage propagates one step each posedge.
    // a=7 constant. b<=a; c<=b.
    // After 1st posedge: b=7, c=0.  After 2nd posedge: b=7, c=7.
    let src = "module m; reg clk; reg [3:0] a; reg [3:0] b; reg [3:0] c; \
               always @(posedge clk) begin b <= a; c <= b; end \
               initial begin \
                 clk=0; a=4'd7; b=4'd0; c=4'd0; \
                 #5 clk=1; #5 clk=0; \
                 #1 $display(\"p1 b=%0d c=%0d\", b, c); \
                 #4 clk=1; #5 clk=0; \
                 #1 $display(\"p2 b=%0d c=%0d\", b, c); \
                 $finish; \
               end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "p1 b=7 c=0\np2 b=7 c=7\n");
}

// ── 6. if/else branch + arithmetic ─────────────────────────────────────────

#[test]
fn if_else_and_arithmetic() {
    let src = "module m; reg [3:0] a; reg [3:0] b; reg [3:0] r; \
               initial begin a=4'd6; b=4'd3; \
                 if (a > b) r = a - b; else r = b - a; \
                 $display(\"%0d\", r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "3\n"); // 6 > 3 → r = 6-3 = 3
}

#[test]
fn else_branch_taken() {
    let src = "module m; reg [3:0] a; reg [3:0] b; reg [3:0] r; \
               initial begin a=4'd2; b=4'd9; \
                 if (a > b) r = a - b; else r = b - a; \
                 $display(\"%0d\", r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "7\n"); // 2 > 9 false → r = 9-2 = 7
}

// ── 7. VCD output: $dumpfile + $dumpvars writes a value change ─────────────

#[test]
fn vcd_dump_initial_and_change() {
    let path = tmp_vcd("dump");
    let _ = std::fs::remove_file(&path);
    let src = "module m; reg [3:0] a; \
               initial begin $dumpfile(\"ignored.vcd\"); $dumpvars(0, m); \
                 a=4'd3; #5 a=4'd9; #5 $finish; end endmodule";
    let ir = build(src);
    let (res, _out) = simulate_capture(&ir, opts_with_vcd(&path));
    assert_eq!(res.finish_reason, FinishReason::Finish);
    let vcd = std::fs::read_to_string(&path).expect("vcd written");
    // header, dumpvars, a var declared as n0, and value changes for 3 then 9.
    assert!(vcd.contains("$dumpvars"), "has dumpvars block");
    assert!(vcd.contains("$var reg 4 ! n0 $end"), "net declared:\n{vcd}");
    assert!(vcd.contains("b0011 !"), "a=3 appears:\n{vcd}");
    assert!(vcd.contains("b1001 !"), "a=9 appears:\n{vcd}");
    assert!(vcd.contains("#5"), "time 5 recorded");
    let _ = std::fs::remove_file(&path);
}

#[test]
fn vcd_clock_toggles_recorded() {
    let path = tmp_vcd("clk");
    let _ = std::fs::remove_file(&path);
    let src = "module m; reg clk; \
               initial begin $dumpfile(\"x\"); $dumpvars; clk=0; \
                 #5 clk=1; #5 clk=0; #5 clk=1; #5 $finish; end endmodule";
    let ir = build(src);
    let (res, _out) = simulate_capture(&ir, opts_with_vcd(&path));
    assert_eq!(res.finish_reason, FinishReason::Finish);
    let vcd = std::fs::read_to_string(&path).expect("vcd written");
    // scalar clk = '!': expect 0! at #0-ish, then 1!,0!,1!.
    assert!(vcd.contains("1!"), "posedge recorded:\n{vcd}");
    assert!(vcd.contains("0!"), "negedge recorded:\n{vcd}");
    // distinct timestamps present
    assert!(vcd.contains("#5") && vcd.contains("#10") && vcd.contains("#15"));
    let _ = std::fs::remove_file(&path);
}

// ── 8. infinite-delta guard (combinational loop) ───────────────────────────

#[test]
fn comb_loop_settles_to_x_not_infinite() {
    // In 4-state logic `assign a = ~a;` settles to X in one delta (it does NOT
    // oscillate — ~Z=X, ~X=X). This documents the 4-state convergence: the run
    // finishes normally rather than tripping the delta guard.
    let src = "module m; wire a; assign a = ~a; \
               initial begin #1 $finish; end endmodule";
    let ir = build(src);
    let opts = SimOpts {
        max_deltas: 1000,
        ..SimOpts::default()
    };
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
}

#[test]
fn infinite_delta_guard_trips() {
    // `always @(a) a = a + 1;` re-triggers itself every delta (a never settles:
    // 0→1→2→…) and never advances time → the infinite-delta guard must fire.
    let src = "module m; reg [3:0] a; \
               always @(a) a = a + 1; \
               initial begin a = 0; #1 $finish; end endmodule";
    let ir = build(src);
    let opts = SimOpts {
        max_deltas: 500,
        ..SimOpts::default()
    };
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, opts);
    assert_eq!(res.finish_reason, FinishReason::DeltaLimit);
    assert_eq!(res.exit_class, sim_engine::ExitClass::Fatal);
}

// ── 9. determinism: identical SimIr → identical output twice ───────────────

#[test]
fn deterministic_repeat_runs() {
    let src = "module m; reg clk; reg [3:0] cnt; \
               always @(posedge clk) cnt <= cnt + 1; \
               initial begin clk=0; cnt=0; \
                 #5 clk=1; #5 clk=0; #5 clk=1; #5 clk=0; \
                 $display(\"%0d\", cnt); $finish; end endmodule";
    let ir = build(src);
    let (_r1, o1) = simulate_capture(&ir, SimOpts::default());
    let (_r2, o2) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(o1, o2, "same SimIr → identical stdout");
    assert_eq!(o1, "2\n", "counter incremented twice");
}

// ── 10. quiescent end (no $finish) ─────────────────────────────────────────

#[test]
fn quiescent_when_no_finish() {
    let src = "module m; reg a; initial begin a=1; #3 a=0; end endmodule";
    let ir = build(src);
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Quiescent);
    assert_eq!(res.sim_time, 3);
}

// ── 11. reduction + bitwise ops with X propagation ─────────────────────────

#[test]
fn reduction_and_xprop() {
    // &4'b1111 = 1 ; |4'b0000 = 0 ; ^4'b1010 = 0
    let src = "module m; reg [3:0] a; reg [3:0] b; reg [3:0] c; \
               initial begin a=4'b1111; b=4'b0000; c=4'b1010; \
                 $display(\"%b %b %b\", &a, |b, ^c); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "1 0 0\n");
}

#[test]
fn x_value_displays_as_x() {
    // Uninitialized reg is X; %d of an all-X value prints x.
    let src = "module m; reg [3:0] a; \
               initial begin $display(\"%d\", a); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "x\n");
}

// ── 12. ternary + concat ───────────────────────────────────────────────────

#[test]
fn ternary_and_concat() {
    let src = "module m; reg sel; reg [3:0] a; reg [3:0] b; reg [7:0] r; \
               initial begin sel=1; a=4'hA; b=4'h5; \
                 r = sel ? {a, b} : {b, a}; \
                 $display(\"%h\", r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // sel=1 → {a,b} = {A,5} = 0xA5
    assert_eq!(out, "a5\n");
}

// ── 13. signed arithmetic + signed %d ──────────────────────────────────────

#[test]
fn signed_subtraction_prints_negative() {
    // signed 8-bit: 3 - 10 = -7, printed as a signed decimal.
    let src = "module m; reg signed [7:0] a; reg signed [7:0] b; reg signed [7:0] r; \
               initial begin a=8'sd3; b=8'sd10; r = a - b; \
                 $display(\"%0d\", r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "-7\n", "signed 3-10 = -7");
}

// ── 14. negedge flip-flop ──────────────────────────────────────────────────

#[test]
fn negedge_flipflop() {
    // q follows d on the negedge of clk (1→0), not on the posedge.
    let src = "module m; reg clk; reg d; reg q; \
               always @(negedge clk) q <= d; \
               initial begin clk=1; d=1; q=0; \
                 #5 clk=0; \
                 #1 $display(\"%b\", q); \
                 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "1\n", "negedge clk captures d=1");
}

// helper to silence unused import warnings if a test path drops them
#[allow(dead_code)]
fn _touch() {
    let _ = Rc::new(RefCell::new(0));
}

#[test]
fn probe_blocking_edge_counter_no_rearm_dup() {
    // Blocking edge body: cnt MUST increment exactly once per posedge.
    // The rearm-duplication bug makes this 2^k-1.
    let src = "module m; reg clk; reg [7:0] cnt; \
               always @(posedge clk) cnt = cnt + 1; \
               initial begin clk=0; cnt=0; \
                 #5 clk=1; #5 clk=0; #5 clk=1; #5 clk=0; #5 clk=1; #5 clk=0; \
                 $display(\"%0d\", cnt); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(
        out, "3\n",
        "blocking edge body increments once per posedge (3 posedges)"
    );
}

#[test]
fn probe_mixed_sign_equality_zero_extends() {
    // 4'sb1111 (=-1 signed) compared to 8'hFF unsigned. Per IEEE 1364 §4.5,
    // if EITHER operand is unsigned the comparison is unsigned: the 4-bit signed
    // operand ZERO-extends to 8'h0F, which != 0xFF → result 0 (not 1).
    let src = "module m; reg signed [3:0] a; reg [7:0] b; reg r; \
               initial begin a=4'sb1111; b=8'hFF; r = (a == b); \
                 $display(\"%b\", r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(
        out, "0\n",
        "mixed signed/unsigned == zero-extends the signed operand"
    );
}

#[test]
fn probe_shift_context_width() {
    // y[7:0] = (a4 << 5), a4 = 4'b0001. The shifted-in bit must survive into the
    // wider 8-bit LHS → 8'h20 = 32. (The engine grows the left-shift result so no
    // bit is lost; `write_lvalue` then truncates to the LHS width.)
    let src = "module m; reg [3:0] a4; reg [7:0] y; \
               initial begin a4=4'b0001; y = a4 << 5; \
                 $display(\"%0d\", y); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(
        out, "32\n",
        "left-shift into a wider LHS keeps the shifted-in bit (0x20)"
    );
}

#[test]
fn probe_cont_assign_oscillator_bounded() {
    // A 2-net combinational ring `a=~b; b=a`. In 4-state this settles to X (no
    // real oscillation), so it finishes — what we assert is that it TERMINATES
    // (bounded), not that it trips. The HIGH fix guarantees that even a divergent
    // cont-assign loop is bounded by the single shared delta budget.
    let src = "module m; wire a; wire b; assign a = ~b; assign b = a; \
               initial begin #1 $finish; end endmodule";
    let ir = build(src);
    let opts = SimOpts {
        max_deltas: 1000,
        ..SimOpts::default()
    };
    let sink = DiagSink::default();
    let res = simulate(&ir, &sink, opts);
    // Must terminate one way or the other (Finish or DeltaLimit), never hang.
    assert!(matches!(
        res.finish_reason,
        FinishReason::Finish | FinishReason::DeltaLimit | FinishReason::Quiescent
    ));
}

#[test]
fn probe_in_body_edge_wait_fires_once() {
    // In-body `@(posedge clk)` must resume exactly once and not leave a standing
    // net_to_edge orphan that re-fires on later clk edges. We count resumes by
    // incrementing a blocking counter after each wait; two posedges → exactly 2.
    let src = "module m; reg clk; reg [7:0] n; \
               initial begin n=0; @(posedge clk) n=n+1; @(posedge clk) n=n+1; \
                 $display(\"%0d\", n); $finish; end \
               initial begin clk=0; #5 clk=1; #5 clk=0; #5 clk=1; #5 clk=0; end \
               endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "2\n", "two in-body posedge waits resume exactly twice");
}

// ── part-select read/write (regression: Select.width / LvalChunk.offset+width
//    are ExprId const-expr edges, not literal counts; must be const-folded) ──

#[test]
fn part_select_read_folds_width() {
    // c[11:4] of 0xABC = 0xAB. Before the fold fix this read the raw width
    // ExprId as a bit count and produced garbage (0x0B).
    let src = "module m; reg [11:0] c; reg [7:0] hi; \
               initial begin c=12'hABC; #1 hi=c[11:4]; $display(\"%h\", hi); $finish; end \
               endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "ab\n", "part-select reads the correct byte");
}

#[test]
fn part_select_write_folds_offset_and_width() {
    // q[7:4]=f then q[3:0]=a → q=0xFA. Exercises the LHS chunk offset+width fold.
    let src = "module m; reg [7:0] q; \
               initial begin q=8'h00; #1 q[7:4]=4'hf; q[3:0]=4'ha; $display(\"%h\", q); $finish; end \
               endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(
        out, "fa\n",
        "two part-select writes land in the right nibbles"
    );
}

#[test]
fn bit_select_write_folds_offset() {
    // b[3]=1 on a zero reg → 0x08. Exercises the bit-select LHS offset fold.
    let src = "module m; reg [7:0] b; \
               initial begin b=8'h00; #1 b[3]=1'b1; $display(\"%h\", b); $finish; end \
               endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "08\n", "bit-select write targets the indexed bit");
}

// ── $strobe / $monitor postponed-region semantics (§5.1–5.14) ───────────────

#[test]
fn strobe_shows_post_nba_value_vs_display_pre() {
    // q starts 0, d=1. On the posedge: $display(q) prints pre-update 0; the NBA
    // q<=d schedules q→1 (applied in NBA region); $strobe(q) defers to the
    // postponed region and samples the settled post-NBA value 1.
    let src = "module m; reg clk; reg d; reg q; \
               always @(posedge clk) begin \
                 $display(\"disp %b\", q); q <= d; $strobe(\"strb %b\", q); \
               end \
               initial begin clk=0; d=1; q=0; \
                 #5 clk=1; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // $display fires in the active region (q still 0). $strobe fires in the
    // postponed region of the SAME timestep, after NBA set q=1.
    assert_eq!(out, "disp 0\nstrb 1\n");
}

#[test]
fn two_strobes_print_in_call_order() {
    // In one posedge step: register $strobe(a) then $strobe(b). a is NBA-updated
    // to 9 this step. Postponed FIFO drains in call order: a-line (settled 9)
    // before b-line (2).
    let src = "module m; reg clk; reg [3:0] a; reg [3:0] b; \
               always @(posedge clk) begin \
                 $strobe(\"a=%0d\", a); $strobe(\"b=%0d\", b); a <= 4'd9; \
               end \
               initial begin clk=0; a=4'd1; b=4'd2; \
                 #5 clk=1; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // Both strobes sample at end-of-timestep regardless of enqueue position:
    // a shows its settled post-NBA value 9; order is call order (a then b).
    assert_eq!(out, "a=9\nb=2\n");
}

#[test]
fn strobe_is_one_shot_per_call() {
    // $strobe runs once inside the posedge body. The next timestep (a later #5
    // with NO posedge) must NOT reprint it: the FIFO was cleared at flush.
    let src = "module m; reg clk; reg [3:0] a; \
               always @(posedge clk) $strobe(\"s=%0d\", a); \
               initial begin clk=0; a=4'd4; \
                 #5 clk=1; \
                 #5 a=4'd7; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // Exactly one strobe line (from the single posedge); the later a=7 step does
    // not reprint because the strobe FIFO is cleared every flush.
    assert_eq!(out, "s=4\n");
}

#[test]
fn monitor_prints_once_on_establish() {
    // Establish $monitor on flag (=0). It prints once in the postponed region of
    // the establishing timestep (establishment-prints-immediately rule).
    let src = "module m; reg flag; \
               initial begin flag=0; \
                 $monitor(\"flag=%b\", flag); \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "flag=0\n");
}

#[test]
fn monitor_prints_only_on_change() {
    // Establish at t=0 (flag=0 → print). t=10 flag→1 (print). t=20 flag unchanged
    // (NO print). t=30 flag→0 (print). Three lines, the unchanged step is silent.
    let src = "module m; reg flag; \
               initial begin flag=0; \
                 $monitor(\"flag=%b\", flag); \
                 #10 flag=1; \
                 #10 flag=1; \
                 #10 flag=0; \
                 #10 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // establish(0) → 1 → [unchanged, silent] → 0
    assert_eq!(out, "flag=0\nflag=1\nflag=0\n");
}

#[test]
fn monitor_detects_x_transition() {
    // flag starts X (uninitialized 1-bit reg). Establish prints "flag=x". Then
    // flag→0 is a value change (X→0) and prints "flag=0". 4-state-aware equality:
    // a defined↔X transition counts as a change.
    let src = "module m; reg flag; \
               initial begin \
                 $monitor(\"flag=%b\", flag); \
                 #5 flag=0; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // %b of an X 1-bit reg renders 'x' (see fmt_radix X handling).
    assert_eq!(out, "flag=x\nflag=0\n");
}

#[test]
fn second_monitor_replaces_first() {
    // Monitor a (=0) at t=0; a→1 at t=10. At t=20 a SECOND $monitor on b (=7)
    // replaces the first. a→2 at t=30 is now invisible. b→8 at t=40 prints.
    let src = "module m; reg [3:0] a; reg [3:0] b; \
               initial begin a=4'd0; b=4'd7; \
                 $monitor(\"a=%0d\", a); \
                 #10 a=4'd1; \
                 #10 $monitor(\"b=%0d\", b); \
                 #10 a=4'd2; \
                 #10 b=4'd8; \
                 #10 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // a establish(0) → a(1) → b establish(7) → [a→2 invisible] → b(8)
    assert_eq!(out, "a=0\na=1\nb=7\nb=8\n");
}

#[test]
fn strobe_then_monitor_ordering_in_one_step() {
    // In a single timestep both a $strobe fires and the monitor changes. Frozen
    // tie-break: strobe line FIRST, then the monitor line.
    let src = "module m; reg clk; reg [3:0] a; \
               always @(posedge clk) $strobe(\"S=%0d\", a); \
               initial begin clk=0; a=4'd0; \
                 $monitor(\"M=%0d\", a); \
                 #5 a=4'd5; clk=1; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // t=0 postponed: monitor establish prints M=0 (no strobe yet).
    // t=5 postponed: a changed 0→5 AND a strobe fired this step → strobe first
    // (S=5), then monitor (M=5).
    assert_eq!(out, "M=0\nS=5\nM=5\n");
}

#[test]
fn strobe_then_finish_same_step_is_skipped() {
    // $strobe then $finish in the SAME active region with no intervening delay:
    // the engine returns on $finish before the settle break, so the postponed
    // flush never runs for this step → the strobe prints nothing.
    //
    // PORTABILITY NOTE: this DIVERGES from reference simulators. IEEE 1364-2005
    // §5.4/§17 drain the CURRENT timestep's postponed region before terminating
    // on $finish, so Icarus/VCS would print "s=3\n" here. vita's MVP skips it for
    // implementation simplicity/determinism (documented §3.4 + §7.3). The expected
    // target for a future IEEE-strict revision is therefore `"s=3\n"`; this test
    // pins the deliberate MVP behavior (empty output) so the divergence is golden,
    // not accidental.
    let src = "module m; reg [3:0] a; \
               initial begin a=4'd3; $strobe(\"s=%0d\", a); $finish; end endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // MVP: "" (skip). IEEE-strict / Icarus / VCS reference target: "s=3\n".
    assert_eq!(
        out, "",
        "no postponed flush after same-step $finish (MVP divergence)"
    );
}

#[test]
fn strobe_defers_past_later_blocking_writes() {
    // Within one initial block: $strobe(a) is registered while a=1, then a
    // blocking a=2 runs, then $display(a) prints 2. The strobe, deferred to the
    // postponed region, samples the FINAL settled a=2 — proving the strobe reads
    // end-of-timestep state, not the call-site value, even with blocking writes.
    let src = "module m; reg [3:0] a; \
               initial begin a=4'd1; $strobe(\"s=%0d\", a); a=4'd2; \
                 $display(\"d=%0d\", a); #1 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // $display prints d=2 immediately (active region). The strobe flushes at the
    // settle of t=0 (before the #1 advances time) sampling a=2.
    assert_eq!(out, "d=2\ns=2\n");
}

#[test]
fn strobe_monitor_deterministic_repeat() {
    let src = "module m; reg clk; reg [3:0] a; \
               always @(posedge clk) $strobe(\"s=%0d\", a); \
               initial begin clk=0; a=4'd0; \
                 $monitor(\"m=%0d\", a); \
                 #5 a=4'd1; clk=1; \
                 #5 clk=0; #5 a=4'd2; clk=1; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_r1, o1) = simulate_capture(&ir, SimOpts::default());
    let (_r2, o2) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(o1, o2, "same SimIr → byte-identical strobe+monitor output");
}

#[test]
fn monitor_reestablish_same_signal_reprints() {
    // Monitor a (=5) → establish prints. a unchanged. Re-issue $monitor on the
    // SAME a: replace semantics reset `last`, so it prints again at that step
    // even though a's value did not change.
    let src = "module m; reg [3:0] a; \
               initial begin a=4'd5; \
                 $monitor(\"a=%0d\", a); \
                 #5 $monitor(\"a=%0d\", a); \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // First establish prints a=5; re-establish resets last_vals=None → prints
    // a=5 again.
    assert_eq!(out, "a=5\na=5\n");
}

#[test]
fn no_arg_monitor_emits_nothing() {
    // A bare `$monitor;` (fmt=None, args=[]) has zero monitored expressions. The
    // flush guard skips it entirely — it must NOT inject a lone "\n" into RTL
    // output at the establishing timestep (or any later step). This pins the
    // deliberate decision from §7.4 / the flush no-arg guard so the output is
    // golden-checked, not emergent.
    //
    // NOTE: depends on elaborate lowering a bare `$monitor;` to a Monitor node
    // with no args. If the front end does not yet emit such a node, gate this test
    // behind the same support; the assertion (empty output) is the contract.
    let src = "module m; reg flag; \
               initial begin flag=0; \
                 $monitor; \
                 #5 flag=1; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // Zero-expression monitor: no establishment line, no per-step line.
    assert_eq!(
        out, "",
        "no-arg $monitor emits no bytes, not even a newline"
    );
}

#[test]
fn monitor_reprints_on_unknown_to_unknown_value_change() {
    // IEEE-correctness regression for value-level (not rendered-string) change
    // detection. q is a 4-bit reg. Under `%d`, EVERY value containing any X
    // renders to literal "x" (builtins fmt_dec returns "x" on any_unknown). So a
    // rendered-string diff would suppress the second print. Value-level 4-state
    // equality detects 4'b00xx → 4'b0x00 as a genuine change → reprint.
    //
    //   t=0  establish: q = 4'b00xx → "x"   (print)
    //   t=5  q = 4'b0x00           → "x"   (DIFFERENT value, same string → MUST print)
    //   t=10 q = 4'b0x00           → "x"   (unchanged value+string → silent)
    let src = "module m; reg [3:0] q; \
               initial begin q=4'b00xx; \
                 $monitor(\"q=%d\", q); \
                 #5 q=4'b0x00; \
                 #5 q=4'b0x00; \
                 #5 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // Three lines? No — two: establish + the X→X value change. The third step is
    // a true no-op (identical (val,unk) planes) and stays silent. All three
    // render to "q=x"; only value-level equality distinguishes them.
    assert_eq!(out, "q=x\nq=x\n");
}

// ═══════════════════════════════════════════════════════════════════════════
//   FORK / JOIN / JOIN_ANY / JOIN_NONE — concurrent execution
//
// Every behavioral assertion below is chosen to FAIL under the OLD sequential
// fork lowering (noted per test). Output ordering uses the declaration-order
// determinism rule (composed child tie). FORK 13 (.velab sidecar round-trip) is
// DEFERRED: staged .velab trailer lands with vcmp/velab/vrun.
// ═══════════════════════════════════════════════════════════════════════════

// ── FORK 1. concurrent delays interleave: b at 3, a at 5 (NOT a@5 then b@8) ──
#[test]
fn fork_join_concurrent_delays_interleave() {
    let src = "module m; reg a; reg b; \
               initial begin a=0; b=0; \
                 fork #5 a=1; #3 b=1; join \
                 $display(\"%0d %b %b\", $time, a, b); \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Quiescent);
    // join waits for ALL → parent prints at t=5 with both set. Sequential would
    // give a@5 then b@8 → print at t=8. The time token 5 FAILS the old path.
    assert_eq!(out, "5 1 1\n");
    assert_eq!(res.sim_time, 5);
}

// ── FORK 2. join waits for the LATER child (monitor each child) ──────────────
#[test]
fn fork_join_waits_for_all_children() {
    let src = "module m; reg a; reg b; \
               initial begin a=0; b=0; \
                 fork #3 begin b=1; $display(\"b@%0d\", $time); end \
                      #5 begin a=1; $display(\"a@%0d\", $time); end join \
                 $display(\"done@%0d\", $time); \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Quiescent);
    // Concurrent: b@3 first, a@5, then parent done@5. Sequential would give
    // b@3,a@8,done@8. "done@5" FAILS the old path.
    assert_eq!(out, "b@3\na@5\ndone@5\n");
}

// ── FORK 3. join_any unblocks at the FIRST completer, surplus runs on ────────
#[test]
fn fork_join_any_unblocks_at_first() {
    let src = "module m; reg slow; reg fast; \
               initial begin slow=0; fast=0; \
                 fork #5 slow=1; #3 fast=1; join_any \
                 $display(\"resume@%0d fast=%b slow=%b\", $time, fast, slow); \
                 #10 $display(\"late@%0d slow=%b\", $time, slow); \
                 $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // join_any resumes at t=3 (fast done), slow still 0 then. Background #5 sets
    // slow=1 at t=5, observed by the late print at t=13. Sequential lowering has
    // no join_any concept → "resume@3" FAILS the old path.
    assert_eq!(out, "resume@3 fast=1 slow=0\nlate@13 slow=1\n");
}

// ── FORK 4. join_none continues IMMEDIATELY (zero blocking) ──────────────────
#[test]
fn fork_join_none_continues_immediately() {
    // `c` is a vector so the literal 9 is representable (the spec's `reg c` would
    // truncate 9→1 in a 1-bit reg; widen to keep the c=9 observation meaningful).
    let src = "module m; reg a; reg [7:0] c; \
               initial begin a=0; c=0; \
                 fork #5 a=1; join_none \
                 c=9; $display(\"cont@%0d c=%0d a=%b\", $time, c, a); \
                 #6 $display(\"after@%0d a=%b\", $time, a); \
                 $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // join_none → c=9 runs at t=0 (no delay), a still 0. Background child sets
    // a=1 at t=5, observed at t=6. Sequential lowering executes #5 a=1 BEFORE
    // c=9 → "cont@5"/a=1. "cont@0 c=9 a=0" FAILS the old path.
    assert_eq!(out, "cont@0 c=9 a=0\nafter@6 a=1\n");
}

// ── FORK 5. two children write DIFFERENT nets, both visible after join ───────
#[test]
fn fork_join_two_children_different_nets() {
    let src = "module m; reg x; reg y; \
               initial begin x=0; y=0; \
                 fork x=1; y=1; join \
                 $display(\"%b %b\", x, y); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // Both children zero-delay → complete at t=0; join releases parent at t=0.
    assert_eq!(out, "1 1\n");
    assert_eq!(res.sim_time, 0);
}

// ── FORK 6. nested begin…end inside a fork child (multi-block child chain) ───
#[test]
fn fork_child_with_nested_begin() {
    let src = "module m; reg p; reg q; \
               initial begin p=0; q=0; \
                 fork \
                   begin #2 p=1; #2 p=0; end \
                   #3 q=1; \
                 join \
                 $display(\"%0d %b %b\", $time, p, q); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // Child-0 chain: p=1@2, p=0@4 (own delays). Child-1: q=1@3. join waits for the
    // later (p=0@4). Parent prints at t=4: p=0,q=1. "4 0 1" FAILS the old path.
    assert_eq!(out, "4 0 1\n");
}

// ── FORK 7. deterministic same-instant ordering: child-0 before child-1 ──────
#[test]
fn fork_same_instant_declaration_order() {
    let src = "module m; integer z; \
               initial begin z=0; \
                 fork $display(\"c0\"); $display(\"c1\"); $display(\"c2\"); join \
                 $display(\"parent\"); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // All zero-delay, same instant → declaration order c0,c1,c2, then parent.
    assert_eq!(out, "c0\nc1\nc2\nparent\n");
}

// ── FORK 8. same-net last-writer-in-declaration-order wins (documented race) ─
#[test]
fn fork_same_net_last_writer_wins() {
    let src = "module m; reg w; \
               initial begin w=0; \
                 fork w=0; w=1; join \
                 $display(\"%b\", w); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // Declaration order: child-0 w=0 then child-1 w=1, both at t=0 → w==1.
    assert_eq!(out, "1\n");
}

// ── FORK 9. a child blocks on @event, parent join waits for it ───────────────
#[test]
fn fork_child_waits_on_event() {
    let src = "module m; reg clk; reg got; \
               initial begin clk=0; got=0; \
                 fork \
                   begin @(posedge clk) got=1; $display(\"woke@%0d\", $time); end \
                   #4 clk=1; \
                 join \
                 $display(\"join@%0d got=%b\", $time, got); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // Child-0 suspends on posedge clk; child-1 drives clk=1 at t=4 → child-0 wakes
    // at t=4, got=1, then join releases parent at t=4. Exercises suspend_on with a
    // CHILD activity id (the collision the scheme fixes).
    assert_eq!(out, "woke@4\njoin@4 got=1\n");
}

// ── FORK 10. parent continuation after join SEES children's net effects ──────
#[test]
fn fork_parent_sees_children_effects() {
    let src = "module m; integer sum; reg d1; reg d2; \
               initial begin sum=0; d1=0; d2=0; \
                 fork #1 d1=1; #2 d2=1; join \
                 if (d1 && d2) sum=42; \
                 $display(\"%0d\", sum); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // After join (t=2) both d1,d2 are 1 (shared scope) → sum=42. "42" FAILS any
    // path where join releases before all children (would print 0).
    assert_eq!(out, "42\n");
}

// ── FORK 11. empty fork…join resumes immediately (zero children) ─────────────
#[test]
fn fork_join_empty_resumes_immediately() {
    let src = "module m; reg r; \
               initial begin r=0; \
                 fork join \
                 r=1; $display(\"%0d %b\", $time, r); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // Zero children → barrier (count 0, ALL) fires same instant → r=1 at t=0.
    assert_eq!(out, "0 1\n");
}

// ── FORK 12. join_any leaves the parent runnable while a slow child survives ──
#[test]
fn fork_join_any_surplus_child_survives_to_finish() {
    let src = "module m; reg first; reg second; \
               initial begin first=0; second=0; \
                 fork #2 first=1; #7 second=1; join_any \
                 $display(\"unblock@%0d\", $time); \
                 #10 $display(\"final@%0d first=%b second=%b\", $time, first, second); \
                 $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // join_any unblocks at t=2 (first child). Surplus #7 child survives, sets
    // second=1 at t=7. Final print at t=12 sees both. "unblock@2" FAILS the old.
    assert_eq!(out, "unblock@2\nfinal@12 first=1 second=1\n");
}

// ── FORK 14. monotonic-append identity stability: a top-level edge process keeps
//    firing AFTER a fork appends activities. ──────────────────────────────────
#[test]
fn fork_does_not_disturb_toplevel_edge_process() {
    let src = "module m; reg clk; integer ticks; \
               always @(posedge clk) ticks = ticks + 1; \
               initial begin clk=0; ticks=0; \
                 fork #1 clk=1; #2 clk=0; #3 clk=1; join \
                 $display(\"ticks=%0d\", ticks); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // The always-block (a top-level EDGE activity armed at t0 into net_to_edge)
    // still fires on each posedge driven by the fork CHILDREN (clk 0→1 at t=1, 0→1
    // at t=3) AFTER the fork appended child activities. Two posedges → ticks=2.
    assert_eq!(out, "ticks=2\n");
}

// ── FORK 15. background join_none child loops forever; parent $finish halts. ──
#[test]
fn fork_join_none_background_child_does_not_block_finish() {
    let src = "module m; reg t; \
               initial begin t=0; \
                 fork begin forever #1 t = ~t; end join_none \
                 #5 $display(\"fin@%0d\", $time); $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (res, out) = simulate_capture(&ir, opts);
    // The forever-looping monitor child keeps the wheel live forever → Quiescent is
    // NEVER reached. The parent's `#5 $finish` is what halts the run. Asserting
    // Finish at t=5 proves: (a) join_none did not block the parent, (b) the
    // background child does not prevent $finish, (c) termination is via $finish.
    assert_eq!(res.finish_reason, FinishReason::Finish);
    assert_eq!(res.sim_time, 5);
    assert_eq!(out, "fin@5\n");
}

// ── determinism regression: FORK 7's source re-run is byte-equal run-to-run. ──
#[test]
fn fork_determinism_regression() {
    let src = "module m; integer z; \
               initial begin z=0; \
                 fork $display(\"c0\"); $display(\"c1\"); $display(\"c2\"); join \
                 $display(\"parent\"); $finish; \
               end endmodule";
    let (ir1, opts1) = build_fork(src);
    let (_r1, o1) = simulate_capture(&ir1, opts1);
    let (ir2, opts2) = build_fork(src);
    let (_r2, o2) = simulate_capture(&ir2, opts2);
    assert_eq!(o1, o2);
    assert_eq!(o1, "c0\nc1\nc2\nparent\n");
}

// ── FORK 17. join_any with TWO children completing at the SAME instant: the
//    parent continuation runs EXACTLY ONCE (the `fired` double-fire guard).
//    (Adversarial-review NIT: previously traced sound but untested.) ──────────
#[test]
fn fork_join_any_same_instant_fires_once() {
    let src = "module m; reg [7:0] a; reg [7:0] b; \
               initial begin a=0; b=0; \
                 fork #3 a=1; #3 b=1; join_any \
                 $display(\"resumed t=%0d\", $time); \
                 #5 $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (_r, out) = simulate_capture(&ir, opts);
    // Both children fire at t=3; a double-fire would print "resumed t=3" twice.
    assert_eq!(out, "resumed t=3\n");
}

// ── FORK 18. two SEQUENTIAL forks in one process use DISTINCT join barriers /
//    join_bb sentinels — the second fork must not satisfy the first's barrier.
//    (Adversarial-review NIT: barrier/sentinel disambiguation, untested.) ─────
#[test]
fn fork_two_sequential_forks_distinct_barriers() {
    let src = "module m; reg [7:0] a; reg [7:0] b; reg [7:0] c; reg [7:0] d; \
               initial begin a=0; b=0; c=0; d=0; \
                 fork #2 a=1; #4 b=1; join \
                 fork #2 c=1; #4 d=1; join \
                 $display(\"a=%0d b=%0d c=%0d d=%0d t=%0d\", a, b, c, d, $time); \
                 $finish; \
               end endmodule";
    let (ir, opts) = build_fork(src);
    let (_r, out) = simulate_capture(&ir, opts);
    // First fork joins at t=4 (a,b set); second runs t=4..8 and joins at t=8.
    assert_eq!(out, "a=1 b=1 c=1 d=1 t=8\n");
}

// ════════════════════════════════════════════════════════════════════════════
// REAL / REALTIME DOMAIN (deliberate sim-ir evolution, format_version 2→3)
// Strings are blessed against the §4.1 formatter algorithms as written.
// ════════════════════════════════════════════════════════════════════════════

/// Build + simulate `src`, returning the captured $display/$write output.
fn run_sv(src: &str) -> String {
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    out
}

// 1. real division is real: 1.0/3.0 prints 0.333333 via %f
#[test]
fn real_division_is_real() {
    let out =
        run_sv("module t; real r; initial begin r = 1.0 / 3.0; $display(\"%f\", r); end endmodule");
    assert_eq!(out.trim(), "0.333333");
}

// 2. int+real promotion: i/2.0 promotes → 3.5 ; i/2 stays integer 3 (then to real)
#[test]
fn int_real_promotion() {
    let out = run_sv(
        "module t; integer i; real r; \
         initial begin i = 7; r = i / 2.0; $display(\"%g\", r); r = i / 2; $display(\"%g\", r); end \
         endmodule",
    );
    assert_eq!(out.trim(), "3.5\n3");
}

// 3. real→int assignment ROUNDS half-away
#[test]
fn real_to_int_assignment_rounds_half_away() {
    let out = run_sv(
        "module t; real r; integer n; \
         initial begin r = 2.5; n = r; $display(\"%0d\", n); r = -2.5; n = r; $display(\"%0d\", n); end \
         endmodule",
    );
    assert_eq!(out.trim(), "3\n-3");
}

// 4. $rtoi TRUNCATES toward zero (contrast with #3)
#[test]
fn rtoi_truncates_toward_zero() {
    let out = run_sv(
        "module t; real r; integer n; \
         initial begin r = 2.9; n = $rtoi(r); $display(\"%0d\", n); r = -2.9; n = $rtoi(r); $display(\"%0d\", n); end \
         endmodule",
    );
    assert_eq!(out.trim(), "2\n-2");
}

// 5. $itor exact int→real
#[test]
fn itor_converts() {
    let out =
        run_sv("module t; real r; initial begin r = $itor(7); $display(\"%g\", r); end endmodule");
    assert_eq!(out.trim(), "7");
}

// 6. $realtobits / $bitstoreal round-trip is identity
#[test]
fn realtobits_bitstoreal_roundtrip() {
    let out = run_sv(
        "module t; real r; reg [63:0] b; real r2; \
         initial begin r = 3.14159; b = $realtobits(r); r2 = $bitstoreal(b); $display(\"%g\", r2); end \
         endmodule",
    );
    assert_eq!(out.trim(), "3.14159");
}

// 7. $realtime returns a real with fractional time (MVP ratio=1)
#[test]
fn realtime_returns_real() {
    let out = run_sv("module t; initial begin #1 $display(\"%g\", $realtime); end endmodule");
    assert_eq!(out.trim(), "1");
}

// 8. %g shortest formatting (C/LRM): exp(0.00001) = -5 < -4 → "1e-05".
#[test]
fn percent_g_shortest() {
    let out = run_sv(
        "module t; real r; \
         initial begin r = 1500.0; $display(\"%g\", r); r = 0.0001; $display(\"%g\", r); r = 0.00001; $display(\"%g\", r); end \
         endmodule",
    );
    assert_eq!(out.trim(), "1500\n0.0001\n1e-05");
}

// 9. %f vs %e — %e is LRM/printf form: 6 mantissa digits, signed 2-digit exponent.
#[test]
fn percent_f_and_e() {
    let out = run_sv(
        "module t; real r; initial begin r = 1500.0; $display(\"%f|%e\", r, r); end endmodule",
    );
    assert_eq!(out.trim(), "1500.000000|1.500000e+03");
}

// 10. %d on a real ROUNDS half-away
#[test]
fn percent_d_on_real_rounds() {
    let out =
        run_sv("module t; real r; initial begin r = 2.7; $display(\"%0d\", r); end endmodule");
    assert_eq!(out.trim(), "3");
}

// 11. real delay #1.5 rounds to integer ticks; $time after = 2
#[test]
fn real_delay_rounds_to_ticks() {
    let out = run_sv("module t; initial begin #1.5 $display(\"%0d\", $time); end endmodule");
    assert_eq!(out.trim(), "2");
}

// 12. NetKind::Real net round-trips through write/read
#[test]
fn real_net_write_read_roundtrip() {
    let out =
        run_sv("module t; real r; initial begin r = 6.022; $display(\"%g\", r); end endmodule");
    assert_eq!(out.trim(), "6.022");
}

// 13. real comparison: value compare, +0.0 == -0.0
#[test]
fn real_compare_value_semantics() {
    let out = run_sv(
        "module t; real a, b; \
         initial begin a = 0.0; b = -0.0; $display(\"%0d\", (a == b)); a = 1.5; b = 2.5; $display(\"%0d\", (a < b)); end \
         endmodule",
    );
    assert_eq!(out.trim(), "1\n1");
}

// 14. unary minus on real
#[test]
fn real_unary_minus() {
    let out =
        run_sv("module t; real r; initial begin r = -(2.5); $display(\"%g\", r); end endmodule");
    assert_eq!(out.trim(), "-2.5");
}

// 14b. signed-zero display: %g canonicalizes -0.0→"0"; %f keeps the sign.
#[test]
fn real_negative_zero_display() {
    let out = run_sv(
        "module t; real r; initial begin r = -(0.0); $display(\"%g|%f\", r, r); end endmodule",
    );
    assert_eq!(out.trim(), "0|-0.000000");
}

// 16. %d of a NaN real → "0"; %d of a huge real saturates to i64::MAX.
#[test]
fn percent_d_real_nan_and_huge() {
    let out = run_sv(
        "module t; real r; \
         initial begin r = 0.0/0.0; $display(\"%0d\", r); r = 1.0e30; $display(\"%0d\", r); end \
         endmodule",
    );
    assert_eq!(out.trim(), "0\n9223372036854775807");
}

// 17. real division by zero is ±inf (NOT X), printed as "inf"/"-inf".
#[test]
fn real_div_zero_is_inf() {
    let out = run_sv(
        "module t; real r; initial begin r = 1.0/0.0; $display(\"%g\", r); r = -1.0/0.0; $display(\"%g\", r); end endmodule",
    );
    assert_eq!(out.trim(), "inf\n-inf");
}

/// Build `src` through lex→parse→elaborate, returning the collected diagnostic
/// strings (severity-prefixed). Used to assert real-operand illegality gates.
fn elaborate_diags(src: &str) -> Vec<String> {
    let (toks, le) = hdl_lexer::lex(src);
    assert!(le.is_empty(), "lex errors: {le:?}");
    let (su, pe) = hdl_parser::parse(&toks, src);
    assert!(pe.is_empty(), "parse errors: {pe:?}");
    let sink = DiagSink::default();
    let _ = elaborate::elaborate(&su.expect("source unit"), &sink);
    let collected = sink.0.borrow().clone();
    drop(sink);
    collected
}

// E1. %h on a real argument is a STATIC elaborate-time rejection (§4.1a).
#[test]
fn real_percent_h_rejected_at_elaborate() {
    let diags = elaborate_diags(
        "module t; real r; initial begin r = 2.5; $display(\"%h\", r); end endmodule",
    );
    assert!(
        diags
            .iter()
            .any(|d| d.contains("binary/hex/octal format not defined on a real argument")),
        "expected %h-on-real rejection, got: {diags:?}"
    );
}

// E2. `**` (power) on a real operand is a permanent ElabUnsupported (§6.2).
#[test]
fn real_power_rejected_at_elaborate() {
    let diags = elaborate_diags(
        "module t; real r; initial begin r = 2.0 ** 3; $display(\"%g\", r); end endmodule",
    );
    assert!(
        diags
            .iter()
            .any(|d| d.contains("power (**) not defined on real operand")),
        "expected **-on-real rejection, got: {diags:?}"
    );
}

// E3. `%` (modulo) on a real operand is rejected (§6.2).
#[test]
fn real_modulo_rejected_at_elaborate() {
    let diags = elaborate_diags(
        "module t; real r; initial begin r = 2.5 % 1.0; $display(\"%g\", r); end endmodule",
    );
    assert!(
        diags
            .iter()
            .any(|d| d.contains("modulo (%) not defined on real operand")),
        "expected %-on-real rejection, got: {diags:?}"
    );
}

// E4. A `real` net lowers to NetKind::Real (width 64, signed) and default-inits
//     to 0.0 (all-zero bits, not X) — a clean real decl elaborates with no diags.
#[test]
fn real_net_lowers_clean() {
    let (toks, le) = hdl_lexer::lex("module t; real r; realtime rt; initial r = 1.0; endmodule");
    assert!(le.is_empty());
    let (su, pe) = hdl_parser::parse(
        &toks,
        "module t; real r; realtime rt; initial r = 1.0; endmodule",
    );
    assert!(pe.is_empty());
    let sink = DiagSink::default();
    let ir = elaborate::elaborate(&su.expect("su"), &sink).expect("ir");
    assert!(
        sink.0.borrow().is_empty(),
        "unexpected diags: {:?}",
        sink.0.borrow()
    );
    // both `r` and `rt` are NetKind::Real, 64-bit signed, init 0.0 (all-zero).
    let reals: Vec<_> = ir
        .nets
        .iter()
        .filter(|n| matches!(n.kind, sim_ir::NetKind::Real))
        .collect();
    assert_eq!(reals.len(), 2, "expected 2 real nets (real + realtime)");
    for n in reals {
        assert_eq!(n.width, 64);
        assert!(n.signed);
        assert!(
            n.init.val.iter().all(|&w| w == 0),
            "real default must be 0.0 bits"
        );
        assert!(
            n.init.unk.iter().all(|&w| w == 0),
            "real default must have unk=0 (never X)"
        );
    }
}

// A real in a boolean/logical context is true iff != 0.0 (IEEE: -0.0 == 0.0).
// Regression for the adversarial-review MAJOR: truthiness must NOT read a real's
// f64 bits as a 4-state vector (which classified -0.0 — sign bit set — as true).
#[test]
fn real_negative_zero_is_logically_false() {
    let src = "module t; real r; integer n; \
               initial begin \
                 r=-0.0; if (r) $display(\"A\"); else $display(\"B\"); \
                 r=-0.0; n=!r; $display(\"%0d\", n); \
                 r=-0.0; n=(r ? 7 : 9); $display(\"%0d\", n); \
                 r=2.5;  if (r) $display(\"T\"); else $display(\"F\"); \
                 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // -0.0 → false (else "B"), !(-0.0)=1, (-0.0 ? 7 : 9)=9, and 2.5 → true ("T").
    assert_eq!(out, "B\n1\n9\nT\n");
}

// ── procedural `for` loop (desugars to `init; while(cond){body; step}`) ──────

#[test]
fn procedural_for_accumulates() {
    // sum 0..4 = 10; nested 5x5 = 25; never-enters keeps the seed.
    let src = "module t; integer i, j, s, c, z; \
               initial begin \
                 s=0; for (i=0;i<5;i=i+1) s=s+i; \
                 c=0; for (i=0;i<5;i=i+1) for (j=0;j<5;j=j+1) c=c+1; \
                 z=99; for (i=0;i<0;i=i+1) z=z+1; \
                 $display(\"s=%0d c=%0d z=%0d\", s, c, z); $finish; \
               end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(out, "s=10 c=25 z=99\n");
}

// A `for` loop that writes a DYNAMIC bit index `a[i]` — the runtime LHS index is
// resolved at statement time, symmetric with the read side. (Before the fix the
// loop was skipped AND the dynamic write landed on bit 0.)
#[test]
fn for_loop_dynamic_bit_write() {
    let src = "module t; integer i; reg [7:0] a; reg [7:0] b; \
               initial begin a=8'h00; b=8'h00; \
                 for (i=0;i<8;i=i+1) a[i]=1; \
                 for (i=0;i<4;i=i+1) b[i]=a[i*2]; \
                 $display(\"a=%h b=%h\", a, b); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // a = all 8 bits = ff; b reads a[0],a[2],a[4],a[6] (all 1) → low nibble = 0f.
    assert_eq!(out, "a=ff b=0f\n");
}

// NBA with a dynamic LHS index samples the index in the ACTIVE region: in
// `a[i] <= 1; i = i+1;` the write must target the OLD `i`, not the bumped one.
#[test]
fn nba_dynamic_index_samples_old_value() {
    let src = "module t; integer i; reg [7:0] a; \
               initial begin a=0; i=2; #1; a[i] <= 1; i = i + 1; \
                 #1 $display(\"a=%h i=%0d\", a, i); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // a[2] set (OLD i=2) → 0x04; i bumped to 3.
    assert_eq!(out, "a=04 i=3\n");
}

// ── parameters / localparams as resolvable constants (sweep gaps 2-6) ────────

#[test]
fn parameters_resolve_as_values_and_widths() {
    // body param as a runtime value; param-sized vector; localparam expr; the
    // {W{..}} replicate count. Before the fix each errored E3010 or gave a
    // silent wrong value (vector→1 bit, replicate→0).
    let src = "module t; \
               parameter W = 8; parameter A = 4; localparam C = A*3 + 1; \
               reg [W-1:0] a; integer x; reg [7:0] r; \
               initial begin a = 200; x = C; r = {A{1'b1}}; \
                 $display(\"a=%h x=%0d r=%h\", a, x, r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // a=200=0xc8 (8-bit holds it), C=4*3+1=13, {4{1'b1}}=0x0f.
    assert_eq!(out, "a=c8 x=13 r=0f\n");
}

#[test]
fn parameter_override_and_generate_with_param() {
    // child param overridden via #(.P()); generate-for bound + body indexed by a
    // genvar into a memory both fold to the genvar/param scope value.
    let src = "module sub #(parameter P = 1) (output [7:0] y); assign y = P + 10; endmodule \
               module t; parameter N = 4; wire [7:0] y; reg [7:0] v[0:3]; genvar g; \
               sub #(.P(7)) u (y); \
               generate for (g = 0; g < N; g = g + 1) begin: gen assign v[g] = g*2; end endgenerate \
               initial begin #1 $display(\"y=%0d v=%0d %0d %0d %0d\", y, v[0], v[1], v[2], v[3]); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // y = 7+10 = 17; v[g] = g*2 → 0 2 4 6.
    assert_eq!(out, "y=17 v=0 2 4 6\n");
}

// ── implicit sensitivity: @* / always_comb / always_latch infer the read-set
//    and RE-FIRE on any input change (sweep gaps 10-12). ───────────────────────

#[test]
fn implicit_sensitivity_recomputes_on_change() {
    let src = "module t; reg [7:0] a, b, sc, cc; reg en; reg [7:0] din, q; \
               always @*       sc = a + b; \
               always_comb     cc = a * 2; \
               always_latch    if (en) q = din; \
               initial begin \
                 a=3; b=4; en=0; din=0; q=0; \
                 #1 $display(\"%0d %0d %0d\", sc, cc, q); \
                 a=10; en=1; din=42; \
                 #1 $display(\"%0d %0d %0d\", sc, cc, q); \
                 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // t1: sc=3+4=7, cc=3*2=6, q=0 (en=0). t2: sc=10+4=14, cc=10*2=20, q=42 (en=1).
    assert_eq!(out, "7 6 0\n14 20 42\n");
}

// ── casez / casex wildcard matching: `?`/`z`/`x` label bits are don't-care
//    (sweep gaps 14,15). Before the fix every wildcard label fell to default. ──

#[test]
fn casez_casex_wildcards_match() {
    let src = "module t; reg [3:0] v; reg [7:0] z, x; \
               initial begin \
                 v = 4'b1010; \
                 casez (v) 4'b1???: z = 8'd3; 4'b01??: z = 8'd2; default: z = 8'd9; endcase \
                 casex (v) 4'b10xx: x = 8'd1; default: x = 8'd9; endcase \
                 $display(\"z=%0d x=%0d\", z, x); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // casez: 1010 matches 1??? → z=3. casex: 1010 matches 10xx → x=1.
    assert_eq!(out, "z=3 x=1\n");
}

// ── wait(expr) resumes on a false→true transition (sweep gaps 18,19). Before
//    the fix WaitCause::Expr never woke, hanging the process. ──────────────────

#[test]
fn wait_resumes_on_false_to_true() {
    let src = "module t; integer cnt; \
               initial begin cnt = 0; forever #10 cnt = cnt + 1; end \
               initial begin wait(cnt == 3); $display(\"hit@%0d\", $time); $finish; end \
               endmodule";
    let ir = build(src);
    let (res, out) = simulate_capture(&ir, SimOpts::default());
    assert_eq!(res.finish_reason, FinishReason::Finish);
    // cnt reaches 3 at t=30; the wait resumes there (not a hang, not never).
    assert_eq!(out, "hit@30\n");
}

// ── generate-if/else: a labeled block is a generate scope (outer nets resolve
//    THROUGH it); both branches + a block-local net work (sweep gap 7). ─────────

#[test]
fn generate_if_else_scoping() {
    let src = "module t; parameter MODE = 1; reg [7:0] a, b, y; reg [7:0] a2, y2; \
               generate if (MODE == 1) begin: ga assign y = a + b; end \
                        else            begin: gb assign y = a - b; end endgenerate \
               generate if (MODE == 0) begin: gc assign y2 = 0; end \
                        else begin: gd reg [7:0] tmp; assign tmp = a2 + 1; assign y2 = tmp * 2; end \
               endgenerate \
               initial begin a=20; b=5; a2=5; #1 $display(\"y=%0d y2=%0d\", y, y2); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // MODE=1: y=a+b=25. Second gen takes else (gd): tmp=a2+1=6, y2=tmp*2=12.
    assert_eq!(out, "y=25 y2=12\n");
}

// ── non-ANSI ports (sweep gap 1) + a CLOCKED submodule driven through a port
//    binding: a cont-assign-driven clock edge must reach the child's always. ──

#[test]
fn non_ansi_ports_and_bound_clock_edge() {
    // `addr` has non-ANSI ports (body input/output decls); `dff` is a clocked
    // submodule whose clk arrives via the parent's port binding (a cont-assign).
    let src =
        "module addr(a, b, y); input [7:0] a, b; output [7:0] y; assign y = a + b; endmodule \
               module dff(clk, d, q); input clk, d; output q; reg q; \
                 always @(posedge clk) q <= d; initial q = 0; endmodule \
               module t; reg [7:0] x, z; wire [7:0] o; reg c, di; wire q; \
                 addr ua(x, z, o); dff ud(c, di, q); \
                 initial begin x=10; z=5; c=0; di=1; \
                   #1 c=1;  /* posedge → q<=1 */ \
                   #1 $display(\"o=%0d q=%b\", o, q); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // o = 10+5 = 15 (non-ANSI comb). q = 1 (bound-clock posedge sampled d=1).
    assert_eq!(out, "o=15 q=1\n");
}

// ── runtime (variable) memory word index: mem[k] read AND write where k is a
//    runtime value (sweep gaps 8,9). Word is now an evaluated ExprId. ──────────

#[test]
fn memory_runtime_word_index() {
    let src = "module t; reg [7:0] m[0:3]; reg [7:0] o; integer k; reg [1:0] idx; \
               initial begin \
                 for (k = 0; k < 4; k = k + 1) m[k] = k + 5;   /* write by runtime k */ \
                 idx = 2; o = m[idx];                          /* read by runtime idx */ \
                 $display(\"%0d %0d %0d %0d r=%0d\", m[0], m[1], m[2], m[3], o); $finish; \
               end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // m[k]=k+5 → 5 6 7 8; m[idx=2] = 7.
    assert_eq!(out, "5 6 7 8 r=7\n");
}

// ── named block with block-local declarations (sweep gap 16): locals are
//    hoisted to module nets so references inside the block resolve. ────────────

#[test]
fn named_block_local_declarations() {
    let src = "module t; integer s; reg [7:0] r; \
               initial begin: acc_blk integer i; integer acc; \
                 acc = 0; for (i = 1; i <= 5; i = i + 1) acc = acc + i; s = acc; \
                 begin: inner reg [7:0] x; reg [7:0] y; x = 10; y = 5; r = x + y; end \
                 $display(\"s=%0d r=%0d\", s, r); $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // sum 1..5 = 15; nested-block locals x=10,y=5 → r=15.
    assert_eq!(out, "s=15 r=15\n");
}

// ── continuous assign with a delay `assign #d y = a`: the value propagates
//    AFTER d ticks, not immediately (certification BLOCKER-1). Transport delay. ─

#[test]
fn continuous_assign_delay_propagates_after_d() {
    let src = "module t; reg [3:0] a; wire [3:0] y; \
               assign #5 y = a; \
               initial begin a = 7; \
                 #2 $display(\"t2 y=%0d\", y);   /* not propagated yet */ \
                 #4 $display(\"t6 y=%0d\", y);   /* propagated at t=5 */ \
                 a = 3; \
                 #6 $display(\"t12 y=%0d\", y);  /* new value at t=11 */ \
                 $finish; end endmodule";
    let ir = build(src);
    let (_res, out) = simulate_capture(&ir, SimOpts::default());
    // y undriven (x) until t=5 then 7; a=3 at t=6 → y=3 at t=11 (seen at t=12).
    assert_eq!(out, "t2 y=x\nt6 y=7\nt12 y=3\n");
}
