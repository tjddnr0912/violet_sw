//! Slice N3 — hierarchical READ-ONLY name references (`tb.dut.x`): referencing a
//! net inside a child module instance from an expression in an ancestor/sibling
//! scope. Currently such refs were loud-rejected (E3009 "deferred"); N3 resolves a
//! downward/outward/absolute hierarchical READ.
//!
//! Mechanism (pure IR-0, elaborate-only — no AST/sim-ir change): a multi-segment
//! path that is not already a known dotted symbol (an interface member alias) emits
//! a PLACEHOLDER `Signal` during pass-7 lowering and is recorded; after ALL
//! instances are elaborated (child nets exist in `symbols` only after pass 8), a
//! fixup patches each placeholder to the resolved NetId. Resolution walks the
//! lowering-scope prefix DOWNWARD (`prefix.path`) → OUTWARD (sibling/ancestor) →
//! ABSOLUTE (root-relative); first hit wins.
//!
//! iverilog 13.0 SUPPORTS hierarchical reads → strong differential oracle; every
//! expected value below was confirmed against iverilog.
//!
//! READ-ONLY: a hierarchical WRITE (`dut.x = ...`) stays loud. Hierarchical PARAM
//! refs (`dut.WIDTH`) and event/dyn-handle/whole-array reads are loud (deferred).
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_hier_{}_{n}", std::process::id()));
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

// ─────────────────────────── downward reads ───────────────────────────

#[test]
fn downward_read_tracks_child_state() {
    // top reads dut.x across clocks; iverilog: 43 then 44 (x init 42, +1 each posedge).
    let (out, err, _c) = run("module sub(input wire clk);\n\
           reg [7:0] x = 8'd42;\n\
           always @(posedge clk) x <= x + 1;\n\
         endmodule\n\
         module top;\n\
           reg clk = 0; always #5 clk = ~clk;\n\
           sub dut(.clk(clk));\n\
           initial begin\n\
             #12 $display(\"A=%0d\", dut.x);\n\
             #10 $display(\"B=%0d\", dut.x);\n\
             #5 $finish;\n\
           end\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "must resolve, not reject:\n{err}");
    assert!(
        out.contains("A=43") && out.contains("B=44"),
        "out:\n{out}\nerr:\n{err}"
    );
}

#[test]
fn three_level_downward_read() {
    // top.m.l.v — a 3-level downward read. iverilog: 9.
    let (out, err, _c) = run("module leaf; reg [3:0] v = 4'd9; endmodule\n\
         module mid; leaf l(); endmodule\n\
         module top; mid m();\n\
           initial #1 $display(\"V=%0d\", m.l.v);\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(out.contains("V=9"), "out:\n{out}");
}

#[test]
fn read_preserves_width_and_select() {
    // dut.x = 200 (8-bit); full read, bit-select, part-select, equality. iverilog:
    // cap=200 bit3=1 ps=12 eq=1.
    let (out, err, _c) = run(
        "module sub; reg [7:0] x = 8'd200; endmodule\n\
         module top;\n\
           sub dut(); reg [7:0] cap;\n\
           initial begin\n\
             #1 cap = dut.x;\n\
             $display(\"cap=%0d bit3=%b ps=%0d eq=%b\", cap, dut.x[3], dut.x[7:4], (dut.x==8'd200));\n\
           end\n\
         endmodule\n",
    );
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(
        out.contains("cap=200 bit3=1 ps=12 eq=1"),
        "hierarchical read must preserve width + support bit/part-select:\n{out}\n{err}"
    );
}

#[test]
fn read_in_continuous_assign() {
    // a continuous assign reading a child net: wire w = dut.x. iverilog: 55.
    let (out, err, _c) = run("module sub; reg [7:0] x = 8'd55; endmodule\n\
         module top; sub dut(); wire [7:0] w = dut.x;\n\
           initial #1 $display(\"w=%0d\", w);\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(out.contains("w=55"), "out:\n{out}");
}

#[test]
fn outward_read_to_sibling_via_root() {
    // top reads a child ia.y; the resolver walks downward from top. iverilog: 7.
    let (out, err, _c) = run("module a; reg [7:0] y = 8'd7; endmodule\n\
         module top; a ia(); a ib();\n\
           initial #1 $display(\"y=%0d\", ia.y);\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(out.contains("y=7"), "out:\n{out}");
}

#[test]
fn read_in_clocked_check() {
    // A child net read inside a clocked process driving a comparison — the common
    // testbench assertion shape. dut.cnt reaches 3 by the 3rd posedge; flag set then.
    let (out, err, _c) = run("module sub(input wire clk);\n\
           reg [3:0] cnt = 0;\n\
           always @(posedge clk) cnt <= cnt + 1;\n\
         endmodule\n\
         module top;\n\
           reg clk = 0; always #5 clk = ~clk;\n\
           sub dut(.clk(clk));\n\
           reg flag = 0;\n\
           always @(posedge clk) if (dut.cnt == 4'd3) flag <= 1;\n\
           initial begin #40 $display(\"flag=%b\", flag); $finish; end\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(
        out.contains("flag=1"),
        "child-state comparison must work:\n{out}\n{err}"
    );
}

// ─────────────────────────── determinism ───────────────────────────

#[test]
fn hier_read_deterministic() {
    let src = "module sub(input wire clk); reg [7:0] x = 8'd42;\n\
         always @(posedge clk) x <= x + 1; endmodule\n\
         module top; reg clk=0; always #5 clk=~clk; sub dut(.clk(clk));\n\
         initial begin #22 $display(\"X=%0d\", dut.x); #5 $finish; end endmodule\n";
    let a = run(src);
    let b = run(src);
    assert_eq!(a, b, "hierarchical-read output must be deterministic");
}

// ─────────────────────────── loud rejects ───────────────────────────

#[test]
fn hierarchical_write_is_loud() {
    // Read-only subset: a hierarchical WRITE (assignment target) stays loud.
    let (out, err, code) = run("module sub; reg [7:0] x = 8'd0; endmodule\n\
         module top; sub dut();\n\
           initial begin #1 dut.x = 8'd5; $display(\"%0d\", dut.x); end\n\
         endmodule\n");
    assert_ne!(
        code,
        Some(0),
        "hierarchical write must be loud:\n{err}\n{out}"
    );
    assert!(
        err.to_lowercase().contains("hierarchical") || err.contains("VITA-E"),
        "expected a loud hierarchical-write diagnostic:\n{err}"
    );
}

#[test]
fn unresolved_hierarchical_name_is_loud() {
    let (out, err, code) = run("module sub; reg [7:0] x = 8'd1; endmodule\n\
         module top; sub dut();\n\
           initial #1 $display(\"%0d\", dut.nope);\n\
         endmodule\n");
    assert_ne!(
        code,
        Some(0),
        "unresolved hierarchical name must be loud:\n{err}\n{out}"
    );
    assert!(
        err.contains("undeclared hierarchical name") || err.contains("VITA-E"),
        "expected a loud undeclared-name diagnostic:\n{err}"
    );
}

#[test]
fn single_segment_still_works() {
    // Byte-identity sanity: a plain single-segment local read is unaffected.
    let (out, err, _c) = run("module top; reg [7:0] q = 8'd99;\n\
           initial #1 $display(\"q=%0d\", q);\n\
         endmodule\n");
    assert!(!err.contains("VITA-E"), "{err}");
    assert!(out.contains("q=99"), "out:\n{out}");
}

// ───────────────── review N3: commit-to-scope (IEEE §23.6) ─────────────────
// The leading path segment binds to the innermost enclosing scope where it is
// found; a missing remainder THERE is an error, NOT a reason to grab an outer net.

#[test]
fn inner_scope_leading_segment_does_not_leak_outward() {
    // `b` binds to the inner child instance (which has `w`, not `v`); `b.v` must be
    // LOUD, NOT silently resolved to the unrelated `top.b.v`. (Review N3 HIGH — the
    // old whole-tail outward strip printed 99 here.)
    let (out, err, code) = run("module cnov; reg [7:0] w = 8'd1; endmodule\n\
         module chasv; reg [7:0] v = 8'd99; endmodule\n\
         module inner; cnov b(); reg [7:0] probe;\n\
           initial #2 begin probe = b.v; $display(\"probe=%0d\", probe); end\n\
         endmodule\n\
         module top; inner inner_i(); chasv b(); endmodule\n");
    assert_ne!(
        code,
        Some(0),
        "must be loud (no outward leak):\n{err}\n{out}"
    );
    assert!(
        !out.contains("probe=99"),
        "must NOT grab the outer net:\n{out}"
    );
    assert!(err.contains("VITA-E"), "{err}");
}

#[test]
fn local_shadow_first_segment_is_loud() {
    // `cfg` is a local scalar in `worker`, shadowing the sibling instance `top.cfg`.
    // `cfg.mode` must be LOUD (can't descend into a net), NOT silently resolve to
    // `top.cfg.mode`=200. (Review N3 HIGH.)
    let (out, err, code) = run("module cfgmod; reg [7:0] mode = 8'd200; endmodule\n\
         module worker; reg [7:0] cfg;\n\
           initial begin cfg = 8'd1; #1 $display(\"m=%0d\", cfg.mode); end\n\
         endmodule\n\
         module top; cfgmod cfg(); worker w(); endmodule\n");
    assert_ne!(
        code,
        Some(0),
        "local-shadowed first segment must be loud:\n{err}\n{out}"
    );
    assert!(
        !out.contains("m=200"),
        "must NOT grab the outer instance net:\n{out}"
    );
}

#[test]
fn named_generate_block_read() {
    // A named generate-if/begin block is referenced by its bare label `gblk` (vita
    // names it `gblk[0]` internally — the resolver maps it). iverilog: 7.
    let (out, err, _c) = run("module top;\n\
           generate if (1) begin : gblk reg [7:0] x = 8'd7; end endgenerate\n\
           initial #1 $display(\"v=%0d\", gblk.x);\n\
         endmodule\n");
    assert!(
        !err.contains("VITA-E"),
        "named genblock ref must resolve:\n{err}"
    );
    assert!(out.contains("v=7"), "out:\n{out}");
}

// ───────────────── review N3: element/array selects are loud (deferred) ─────────────────

#[test]
fn packed_multidim_element_read_is_loud() {
    // `dut.pm[1]` on a packed [1:0][7:0] must be LOUD, NOT a silent 1-bit bit-select
    // (review N3 HIGH — it formerly printed r=01 instead of bb). A hierarchical
    // element select on a multi-dim net is a deferred follow-on lane.
    let (out, err, code) = run(
        "module sub; reg [1:0][7:0] pm; initial begin pm[0]=8'hAA; pm[1]=8'hBB; end endmodule\n\
         module top; sub dut(); reg [7:0] r;\n\
           initial #1 begin r = dut.pm[1]; $display(\"r=%h\", r); end\n\
         endmodule\n",
    );
    assert_ne!(
        code,
        Some(0),
        "packed multi-dim hierarchical read must be loud:\n{err}\n{out}"
    );
    assert!(
        !out.contains("r=01"),
        "must NOT silently 1-bit-select:\n{out}"
    );
    assert!(err.contains("VITA-E"), "{err}");
}

#[test]
fn unpacked_array_element_read_is_loud() {
    // `dut.mem[2]` (unpacked array element) is a deferred follow-on → loud (verdict-safe).
    let (out, err, code) = run(
        "module sub; reg [7:0] mem [0:3]; initial begin mem[2]=8'hCC; end endmodule\n\
         module top; sub dut();\n\
           initial #1 $display(\"m=%0d\", dut.mem[2]);\n\
         endmodule\n",
    );
    assert_ne!(
        code,
        Some(0),
        "hierarchical array-element read must be loud:\n{err}\n{out}"
    );
    assert!(err.contains("VITA-E"), "{err}");
}
