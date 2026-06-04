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
    assert_eq!(out, "fa\n", "two part-select writes land in the right nibbles");
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
