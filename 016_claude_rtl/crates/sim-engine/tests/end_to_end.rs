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
