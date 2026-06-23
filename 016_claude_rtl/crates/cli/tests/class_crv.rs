//! Phase B1 (N7-REST): constrained-random verification — `rand` class members,
//! `constraint` blocks with range/relational constraints, and `obj.randomize()`.
//! Determinism is part of the contract: same design → byte-identical draw sequence
//! on every OS (seeded `dist_uniform`). iverilog 13 does NOT support randomization,
//! so the oracle is IEEE 1800 §18 semantics + determinism + constraint satisfaction.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_crv_{}_{n}", std::process::id()));
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

#[test]
fn randomize_respects_range_constraint() {
    // A rand field with a [1:6] range constraint: every randomize() draw must land
    // in range. Loop several draws; all must satisfy the constraint.
    let (out, err, code) = run("class Die;\n\
           rand int v;\n\
           constraint c { v >= 1; v <= 6; }\n\
         endclass\n\
         module top; Die d; integer i; integer ok;\n\
         initial begin\n\
           d = new;\n\
           ok = 1;\n\
           for (i = 0; i < 20; i = i + 1) begin\n\
             d.randomize();\n\
             if (d.v < 1 || d.v > 6) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "got:\n{out}");
}

#[test]
fn randomize_is_deterministic() {
    // The same program run twice must produce the identical draw sequence (seeded).
    let src = "class P;\n\
           rand int x;\n\
           constraint c { x >= 0; x <= 99; }\n\
         endclass\n\
         module top; P p; integer i;\n\
         initial begin\n\
           p = new;\n\
           for (i = 0; i < 5; i = i + 1) begin\n\
             p.randomize();\n\
             $display(\"x=%0d\", p.x);\n\
           end\n\
           $finish;\n\
         end\n\
         endmodule\n";
    let (out1, _, c1) = run(src);
    let (out2, _, c2) = run(src);
    assert_eq!(c1, Some(0));
    assert_eq!(c2, Some(0));
    assert_eq!(out1, out2, "randomize must be deterministic across runs");
    // and the draws must vary (not all identical) — a real distribution.
    let xs: Vec<&str> = out1.lines().filter(|l| l.starts_with("x=")).collect();
    assert_eq!(xs.len(), 5, "got:\n{out1}");
    assert!(xs.iter().any(|&l| l != xs[0]), "draws must vary:\n{out1}");
}

#[test]
fn randomize_returns_success() {
    // `r = obj.randomize();` returns 1 on success (feasible constraints).
    let (out, err, code) = run("class P;\n\
           rand int x;\n\
           constraint c { x >= 5; x <= 5; }\n\
         endclass\n\
         module top; P p; integer r;\n\
         initial begin\n\
           p = new;\n\
           r = p.randomize();\n\
           $display(\"r=%0d x=%0d\", r, p.x);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    // single-value constraint x==5 -> always 5, success.
    assert!(out.contains("r=1 x=5"), "got:\n{out}");
}

#[test]
fn randomize_multiple_fields_each_in_range() {
    let (out, err, code) = run("class P;\n\
           rand int a;\n\
           rand int b;\n\
           constraint c { a >= 10; a <= 12; b >= 100; b <= 102; }\n\
         endclass\n\
         module top; P p; integer i; integer ok;\n\
         initial begin\n\
           p = new; ok = 1;\n\
           for (i = 0; i < 20; i = i + 1) begin\n\
             p.randomize();\n\
             if (p.a < 10 || p.a > 12 || p.b < 100 || p.b > 102) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "got:\n{out}");
}

#[test]
fn randomize_conjunction_in_single_expr() {
    // A single constraint expr with `&&` narrows the field on both sides.
    let (out, err, code) = run("class P;\n\
           rand int x;\n\
           constraint c { x > 3 && x < 7; }\n\
         endclass\n\
         module top; P p; integer i; integer ok;\n\
         initial begin\n\
           p = new; ok = 1;\n\
           for (i = 0; i < 20; i = i + 1) begin\n\
             p.randomize();\n\
             if (p.x <= 3 || p.x >= 7) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "got:\n{out}");
}

#[test]
fn randomize_inherited_rand_and_constraint() {
    // A rand field + constraint declared in the BASE applies to a derived instance.
    let (out, err, code) = run("class Base;\n\
           rand int v;\n\
           constraint cb { v >= 1; v <= 4; }\n\
         endclass\n\
         class Der extends Base;\n\
           int tag;\n\
         endclass\n\
         module top; Der d; integer i; integer ok;\n\
         initial begin\n\
           d = new; ok = 1;\n\
           for (i = 0; i < 20; i = i + 1) begin\n\
             d.randomize();\n\
             if (d.v < 1 || d.v > 4) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "got:\n{out}");
}

#[test]
fn randomize_wide_field_honors_constraint() {
    // Regression (adversarial hunt): a rand field WIDER than 32 bits must still honor
    // its range constraint — earlier the >32-bit draw path silently dropped [lo,hi].
    let (out, err, code) = run("class C;\n\
           rand bit [40:0] x;\n\
           constraint c { x >= 10; x <= 20; }\n\
         endclass\n\
         module top; C o; integer i; integer oob;\n\
         initial begin\n\
           o = new; oob = 0;\n\
           for (i = 0; i < 100; i = i + 1) begin\n\
             o.randomize();\n\
             if (o.x < 10 || o.x > 20) oob = oob + 1;\n\
           end\n\
           $display(\"oob=%0d\", oob); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("oob=0"), "got:\n{out}");
}

#[test]
fn randomize_upper_unsigned_bounds_honored() {
    // Regression: a 32-bit field with bounds in the UPPER unsigned half (> i32::MAX)
    // must honor them — earlier `hi > i32::MAX` forced the unconstrained draw.
    let (out, err, code) = run("class C;\n\
           rand bit [31:0] u;\n\
           constraint c { u >= 3000000000; u <= 4000000000; }\n\
         endclass\n\
         module top; C o; integer i; reg [31:0] v; integer bad;\n\
         initial begin\n\
           o = new; bad = 0;\n\
           for (i = 0; i < 100; i = i + 1) begin\n\
             o.randomize(); v = o.u;\n\
             if (v < 3000000000 || v > 4000000000) bad = bad + 1;\n\
           end\n\
           $display(\"bad=%0d\", bad); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("bad=0"), "got:\n{out}");
}

#[test]
fn randomize_longint_single_sided_constraint() {
    // Regression: a wide signed field with a single-sided constraint (`x < 5`) must
    // honor it (earlier the full-width draw produced ~half over the bound).
    let (out, err, code) = run("class C;\n\
           rand longint x;\n\
           constraint c { x < 5; }\n\
         endclass\n\
         module top; C o; integer i; integer bad;\n\
         initial begin\n\
           o = new; bad = 0;\n\
           for (i = 0; i < 100; i = i + 1) begin\n\
             o.randomize();\n\
             if (o.x >= 5) bad = bad + 1;\n\
           end\n\
           $display(\"bad=%0d\", bad); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("bad=0"), "got:\n{out}");
}

#[test]
fn randc_is_loud_rejected() {
    let (_, err, code) = run("class P;\n\
           randc bit [1:0] x;\n\
         endclass\n\
         module top; P p; initial begin p = new; p.randomize(); $finish; end endmodule\n");
    assert_ne!(code, Some(0), "must reject randc; stderr:\n{err}");
    assert!(err.contains("randc"), "expected a randc diagnostic:\n{err}");
}

#[test]
fn contradictory_constraint_is_loud_rejected() {
    let (_, err, code) = run("class P;\n\
           rand int x;\n\
           constraint c { x >= 10; x <= 5; }\n\
         endclass\n\
         module top; P p; initial begin p = new; p.randomize(); $finish; end endmodule\n");
    assert_ne!(code, Some(0), "must reject contradiction; stderr:\n{err}");
    assert!(
        err.contains("contradictory") || err.contains("empty solution"),
        "expected a contradiction diagnostic:\n{err}"
    );
}

#[test]
fn staged_randomize_carries_sidecar() {
    // The staged vcmp→velab→vrun path must carry the `class_rand` sidecar (the
    // STAGED-DROP class of bug). If it were dropped, randomize() would be a no-op,
    // leaving `v` at its 2-state default 0 → the `v < 1` $fatal fires → non-zero
    // exit. A clean exit 0 proves the sidecar survived the `.velab` trailer.
    let src = "class Die;\n\
           rand int v;\n\
           constraint c { v >= 1; v <= 6; }\n\
         endclass\n\
         module top; Die d; integer i;\n\
         initial begin\n\
           d = new;\n\
           for (i = 0; i < 8; i = i + 1) begin\n\
             d.randomize();\n\
             if (d.v < 1 || d.v > 6) $fatal(1, \"rand out of range\");\n\
           end\n\
           $finish;\n\
         end\n\
         endmodule\n";
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("vita_crvst_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let sv = dir.join("t.sv");
    std::fs::write(&sv, src).unwrap();
    let s = |p: &std::path::Path| p.to_str().unwrap().to_string();
    let vu = dir.join("t.vu");
    let velab = dir.join("t.velab");
    let o = cli::VitaOpts::default();
    assert_eq!(
        cli::run_vcmp(&[s(&sv)], Some(&s(&vu)), &o),
        0,
        "vcmp failed"
    );
    assert_eq!(cli::run_velab(&s(&vu), &s(&velab), &o), 0, "velab failed");
    // Clean exit 0 ⇒ no $fatal ⇒ every draw was in [1,6] ⇒ sidecar carried.
    assert_eq!(
        cli::run_vrun(&s(&velab), &o),
        0,
        "staged randomize dropped the sidecar"
    );
}

#[test]
fn randomize_unconstrained_field_varies() {
    // A rand field with NO constraint draws across its full range; two draws differ
    // (overwhelmingly likely) — checks the unconstrained path works.
    let (out, err, code) = run("class P;\n\
           rand bit [7:0] b;\n\
         endclass\n\
         module top; P p; integer i; integer seen_hi;\n\
         initial begin\n\
           p = new;\n\
           seen_hi = 0;\n\
           for (i = 0; i < 30; i = i + 1) begin\n\
             p.randomize();\n\
             if (p.b > 200) seen_hi = 1;\n\
           end\n\
           $display(\"seen_hi=%0d\", seen_hi);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("seen_hi=1"), "got:\n{out}");
}

// ───────────────────────── Phase B2: general constraint solver ─────────────────────────

#[test]
fn randomize_inter_variable_lt() {
    // INTER-VARIABLE `x < y` (no single-field [lo,hi] can express it) — enforced by
    // the rejection-sampling solver. Every draw must satisfy x < y.
    let (out, err, code) = run("class P;\n\
           rand int x;\n\
           rand int y;\n\
           constraint c { x >= 0; x <= 100; y >= 0; y <= 100; x < y; }\n\
         endclass\n\
         module top; P p; integer i; integer ok;\n\
         initial begin\n\
           p = new; ok = 1;\n\
           for (i = 0; i < 80; i = i + 1) begin\n\
             p.randomize();\n\
             if (!(p.x < p.y)) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "x<y must always hold:\n{out}");
}

#[test]
fn randomize_arithmetic_inter_variable() {
    // Arithmetic inter-variable `a + b == 50` — the solver must find satisfying pairs.
    let (out, err, code) = run("class P;\n\
           rand int a;\n\
           rand int b;\n\
           constraint c { a >= 0; a <= 50; b >= 0; b <= 50; a + b == 50; }\n\
         endclass\n\
         module top; P p; integer i; integer ok;\n\
         initial begin\n\
           p = new; ok = 1;\n\
           for (i = 0; i < 200; i = i + 1) begin\n\
             p.randomize();\n\
             if (p.a + p.b != 50) ok = 0;\n\
           end\n\
           $display(\"ok=%0d\", ok); $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("ok=1"), "a+b==50 must always hold:\n{out}");
}

#[test]
fn randomize_inter_variable_deterministic() {
    // The rejection-sampling solver consumes the seed deterministically: the same
    // program run twice produces the identical accepted draw sequence.
    let src = "class P;\n\
           rand int x;\n\
           rand int y;\n\
           constraint c { x >= 0; x <= 1000; y >= 0; y <= 1000; x < y; }\n\
         endclass\n\
         module top; P p; integer i;\n\
         initial begin\n\
           p = new;\n\
           for (i = 0; i < 5; i = i + 1) begin p.randomize(); $display(\"%0d %0d\", p.x, p.y); end\n\
           $finish;\n\
         end\n\
         endmodule\n";
    let (a, _, _) = run(src);
    let (b, _, _) = run(src);
    assert_eq!(a, b, "the accepted draw sequence must be deterministic");
}

#[test]
fn staged_inter_variable_carries() {
    // The staged vcmp→velab→vrun path must carry the B2 `class_constraints` predicate
    // (else x<y is dropped → the $fatal-on-violation fires → non-zero exit).
    let src = "class P;\n\
           rand int x;\n\
           rand int y;\n\
           constraint c { x >= 0; x <= 100; y >= 0; y <= 100; x < y; }\n\
         endclass\n\
         module top; P p; integer i;\n\
         initial begin\n\
           p = new;\n\
           for (i = 0; i < 8; i = i + 1) begin\n\
             p.randomize();\n\
             if (!(p.x < p.y)) $fatal(1, \"inter-variable constraint dropped\");\n\
           end\n\
           $finish;\n\
         end\n\
         endmodule\n";
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("vita_crvb2_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let sv = dir.join("t.sv");
    std::fs::write(&sv, src).unwrap();
    let s = |p: &std::path::Path| p.to_str().unwrap().to_string();
    let vu = dir.join("t.vu");
    let velab = dir.join("t.velab");
    let o = cli::VitaOpts::default();
    assert_eq!(
        cli::run_vcmp(&[s(&sv)], Some(&s(&vu)), &o),
        0,
        "vcmp failed"
    );
    assert_eq!(cli::run_velab(&s(&vu), &s(&velab), &o), 0, "velab failed");
    assert_eq!(
        cli::run_vrun(&s(&velab), &o),
        0,
        "staged path dropped the B2 constraint predicate"
    );
}
