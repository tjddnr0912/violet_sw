//! N4 clocking block — FUNCTIONAL (2026-06-25, §14). v1 = default-skew INPUT
//! sampling + `@(cb)`. A clocking input `cb.sig` reads the PREPONED value (the
//! value `sig` had at the START of the clocking-edge time slot, before any slot
//! activity), synthesized as a holding net committed by a marked handler from an
//! engine preponed snapshot taken at each time advance. `@(cb)` ≡ the clocking
//! event. Output drivers (need the Observed/Reactive region), explicit skews,
//! multi-clock/anonymous blocks, and non-net binds are HONEST-LOUD (E3009).
//!
//! iverilog 13 supports NO clocking blocks → every verdict is HAND-IEEE (no
//! differential oracle), independently cross-checked. Clock: `always #5 clk=~clk`
//! → posedges at t=5,15,25,35,45,55,…
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_clk4_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
        out.status.code(),
    )
}

fn clean(out: &str, err: &str, code: Option<i32>, want: &str, ctx: &str) {
    assert_eq!(code, Some(0), "{ctx}: expected exit 0.\n{err}{out}");
    assert!(
        out.contains(want),
        "{ctx}: expected `{want}` in output.\n{err}{out}"
    );
}

fn loud(out: &str, err: &str, code: Option<i32>, ctx: &str) {
    assert_ne!(
        code,
        Some(0),
        "{ctx}: must be loud, not silent.\n{err}{out}"
    );
    assert!(
        format!("{err}{out}").contains("VITA-E"),
        "{ctx}: expected a loud diagnostic.\n{err}{out}"
    );
}

// ── functional: PREPONED input sampling ──

#[test]
fn input_samples_registered_value() {
    // q increments via NBA (0,1,2,3,…). At the 4th posedge cb.q = preponed q = 3
    // (= the live in-Active value for an NBA-driven signal). Pins basic sampling.
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer q=0;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) q <= q+1;\n\
         clocking cb @(posedge clk); input q; endclocking\n\
         initial begin repeat(4) @(posedge clk); $display(\"q=%0d cbq=%0d\", q, cb.q); $finish; end\n\
         endmodule\n");
    clean(&o, &e, c, "q=3 cbq=3", "NBA-driven input sampling");
}

#[test]
fn input_blocking_toggle_is_preponed_not_racy() {
    // THE discriminating test: `a` is toggled by a BLOCKING assign in the Active
    // region. cb.a must be the value ENTERING each slot (preponed, before this
    // edge's toggle), immune to Active process ordering — the race that a naive
    // Active-region sampler gets wrong. a: 0(init)→1→0→1; cb.a entering each
    // slot = 0,1,0,1 at t=5,15,25,35.
    let (o, e, c) = run("module t;\n\
         logic clk=0; logic a=0;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) a = ~a;\n\
         clocking cb @(posedge clk); input a; endclocking\n\
         always @(posedge clk) $display(\"@%0t cb.a=%b\", $time, cb.a);\n\
         initial #38 $finish;\n\
         endmodule\n");
    assert_eq!(c, Some(0), "exit 0:\n{e}{o}");
    for want in ["@5 cb.a=0", "@15 cb.a=1", "@25 cb.a=0", "@35 cb.a=1"] {
        assert!(o.contains(want), "expected `{want}`:\n{o}");
    }
}

#[test]
fn reader_woken_by_same_edge_sees_committed_sample() {
    // A reader `seen = cb.q` woken by the SAME posedge sees the committed (preponed)
    // value — the handler commits before the reader (handler ProcId sorts first).
    // At edge 5: cb.q = q entering edge5 = 4; after edge5 NBA q = 5.
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer q=0, seen=-1;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) q <= q+1;\n\
         clocking cb @(posedge clk); input q; endclocking\n\
         always @(posedge clk) seen = cb.q;\n\
         initial begin repeat(5) @(posedge clk); #1 $display(\"q=%0d seen=%0d\", q, seen); $finish; end\n\
         endmodule\n");
    clean(
        &o,
        &e,
        c,
        "q=5 seen=4",
        "same-edge reader sees committed preponed",
    );
}

#[test]
fn input_is_x_before_first_edge() {
    // cb.sig before the first clocking edge is X (nothing sampled yet); after the
    // first posedge it holds the bound signal's sampled value.
    let (o, e, c) = run("module t;\n\
         logic clk=0; logic [3:0] d=4'hA;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input d; endclocking\n\
         initial begin\n\
           #2 $display(\"before=%h\", cb.d);\n\
           @(posedge clk); #1 $display(\"after=%h\", cb.d); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(c, Some(0), "exit 0:\n{e}{o}");
    assert!(o.contains("before=x"), "pre-edge X:\n{o}");
    assert!(o.contains("after=a"), "post-edge sampled value:\n{o}");
}

#[test]
fn input_bind_expr_samples_other_signal() {
    // `input sq = q;` samples the bound signal `q` (not a same-named net).
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer q=0;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) q <= q+2;\n\
         clocking cb @(posedge clk); input sq = q; endclocking\n\
         initial begin repeat(3) @(posedge clk); $display(\"sq=%0d\", cb.sq); $finish; end\n\
         endmodule\n");
    // q: 0,2,4,6; entering edge3 q=4 → cb.sq=4.
    clean(&o, &e, c, "sq=4", "bind-expr input sampling");
}

// ── functional: `@(cb)` as the clocking event ──

#[test]
fn at_cb_is_the_clocking_event() {
    // `@(cb)` waits for the clocking event (posedge clk). 3 waits → t=25.
    let (o, e, c) = run("module t;\n\
         logic clk=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input clk; endclocking\n\
         initial begin repeat(3) @(cb); $display(\"t=%0t\", $time); $finish; end\n\
         endmodule\n");
    clean(&o, &e, c, "t=25", "@(cb) ≡ @(posedge clk)");
}

#[test]
fn at_cb_in_always_header() {
    // `@(cb)` as a process header sensitivity.
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer n=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input clk; endclocking\n\
         always @(cb) n = n + 1;\n\
         initial begin #58 $display(\"n=%0d\", n); $finish; end\n\
         endmodule\n");
    // posedges at 5,15,25,35,45,55 → 6 increments by t=58.
    clean(&o, &e, c, "n=6", "@(cb) always header");
}

#[test]
fn cross_hierarchy_reader_matches_in_module_reader() {
    // §14: the committed sample is a property of the holding net, identical for
    // EVERY same-slot reader regardless of hierarchy. A parent reading `u0.cb.q`
    // must match the in-submodule reader on the SAME edge — NOT one clock stale.
    // (Regression for the commit-vs-reader cross-hierarchy ProcId race: the commit
    // is applied at edge detection, before any Active reader, not as a tie-ordered
    // process.) q (NBA) = 1,2,3 after edges t=5,15,25 → cb.q committed = 0,1,2.
    let (o, e, c) = run("module sub(input logic clk);\n\
         integer q=0;\n\
         always @(posedge clk) q <= q+1;\n\
         clocking cb @(posedge clk); input q; endclocking\n\
         always @(posedge clk) $display(\"IN %0t %0d\", $time, cb.q);\n\
         endmodule\n\
         module t;\n\
         logic clk=0;\n\
         always #5 clk=~clk;\n\
         sub u0(clk);\n\
         always @(posedge clk) $display(\"TOP %0t %0d\", $time, u0.cb.q);\n\
         initial #28 $finish;\n\
         endmodule\n");
    assert_eq!(c, Some(0), "exit 0:\n{e}{o}");
    for (t, v) in [("5", "0"), ("15", "1"), ("25", "2")] {
        assert!(
            o.contains(&format!("IN {t} {v}")) && o.contains(&format!("TOP {t} {v}")),
            "@{t}: both IN and TOP readers must see cb.q={v} (not stale):\n{o}"
        );
    }
}

// ── honest-loud: out-of-v1-scope forms ──

#[test]
fn output_driver_is_loud() {
    let (o, e, c) = run("module t;\n\
         logic clk=0, d=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); output d; endclocking\n\
         initial #20 $finish;\n\
         endmodule\n");
    loud(&o, &e, c, "clocking output driver");
}

#[test]
fn input_skew_1step_is_default_behavior() {
    // `input #1step q` is semantically identical to `input q` (default skew IS
    // #1step = preponed). Explicit #1step must be accepted, not loud-rejected.
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer q=0;\n\
         always #5 clk=~clk;\n\
         always @(posedge clk) q <= q+1;\n\
         clocking cb @(posedge clk); input #1step q; endclocking\n\
         initial begin repeat(4) @(posedge clk); \
         $display(\"q=%0d cbq=%0d\", q, cb.q); $finish; end\n\
         endmodule\n");
    clean(
        &o,
        &e,
        c,
        "q=3 cbq=3",
        "#1step explicit = same as default preponed sampling",
    );
}

#[test]
fn explicit_skew_other_than_1step_is_loud() {
    // Only `#1step` (= default) is accepted. `#1` (1 time unit before edge)
    // requires time-travel sampling — honest-loud until a proper skew engine slice.
    let (o, e, c) = run("module t;\n\
         logic clk=0, a=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input #1 a; endclocking\n\
         initial #20 $finish;\n\
         endmodule\n");
    loud(&o, &e, c, "non-#1step input skew");
}

#[test]
fn anonymous_clocking_is_loud() {
    let (o, e, c) = run("module t;\n\
         logic clk=0, a=0;\n\
         always #5 clk=~clk;\n\
         clocking @(posedge clk); input a; endclocking\n\
         initial #20 $finish;\n\
         endmodule\n");
    loud(&o, &e, c, "anonymous clocking block");
}

#[test]
fn unknown_input_signal_is_loud() {
    let (o, e, c) = run("module t;\n\
         logic clk=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input nonexist; endclocking\n\
         initial #20 $finish;\n\
         endmodule\n");
    loud(&o, &e, c, "undeclared clocking input");
}

#[test]
fn hierarchical_drive_of_clocking_input_is_loud() {
    // §14.3: a clocking INPUT is read-only from ANYWHERE — a parent driving
    // `dut.cb.s = v` (blocking/NBA/select/force) must be loud, NEVER a silent write
    // to the submodule's holding reg that corrupts the sample. (Round-2 adversarial
    // hunt found this silent-wrong on the deferred cross-instance write path.)
    for drive in [
        "dut.cb.s = 4'd9;",
        "dut.cb.s <= 4'd9;",
        "dut.cb.s[0] = 1'b1;",
    ] {
        let (o, e, c) = run(&format!(
            "module sub(input logic clk);\n\
             logic [3:0] s=4'd2;\n\
             clocking cb @(posedge clk); input s; endclocking\n\
             endmodule\n\
             module t;\n\
             logic clk=0; always #5 clk=~clk;\n\
             sub dut(.clk(clk));\n\
             always @(posedge clk) {drive}\n\
             initial #22 $finish;\n\
             endmodule\n"
        ));
        loud(&o, &e, c, &format!("hierarchical drive `{drive}`"));
    }
}

#[test]
fn cross_hier_clocking_event_has_clear_message() {
    // `@(u0.cb)` (cross-hierarchy clocking-event control) is unsupported, but the
    // diagnostic must be an EVENT-control message — NOT the generic hierarchical
    // lvalue/WRITE text (the construct is a read). (Round-2 loud-gap fix.)
    let (o, e, c) = run("module dut(input clk);\n\
         logic [7:0] q=0;\n\
         clocking cb @(posedge clk); input q; endclocking\n\
         always @(posedge clk) q<=q+1;\n\
         endmodule\n\
         module top;\n\
         logic clk=0; always #5 clk=~clk;\n\
         dut u0(.clk(clk));\n\
         always @(u0.cb) $display(\"x\");\n\
         initial #38 $finish;\n\
         endmodule\n");
    loud(&o, &e, c, "cross-hier @(u0.cb)");
    let all = format!("{e}{o}");
    assert!(
        all.contains("clocking-event") && !all.contains("lvalue context"),
        "must be a clocking-event message, not the generic lvalue text:\n{all}"
    );
}

#[test]
fn driving_a_clocking_input_is_loud() {
    // §14.3: a clocking INPUT is read-only — writing `cb.q` must be loud, NEVER a
    // silent write to the holding reg. (Adversarial-probe regression.)
    let (o, e, c) = run("module t;\n\
         logic clk=0; integer q=0;\n\
         always #5 clk=~clk;\n\
         clocking cb @(posedge clk); input q; endclocking\n\
         initial begin @(posedge clk); cb.q = 99; $finish; end\n\
         endmodule\n");
    loud(&o, &e, c, "driving a clocking input");
}
