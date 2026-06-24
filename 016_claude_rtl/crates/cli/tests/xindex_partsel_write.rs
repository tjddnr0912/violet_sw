//! An indexed part-select WRITE (`a[idx +: w] = …` / `a[idx -: w] = …`) whose
//! INDEX is X/Z must DISCARD the whole write (the bit position is unknown) —
//! iverilog parity. vita previously routed the X index through the same OOR
//! sentinel (u32::MAX) as a real `-1`, which P0-IPU partial-writes, so X-index
//! writes corrupted bits. A real negative index (`-1`/`-2`) still partial-writes
//! (only the in-range bits). A bit-select X index already discarded. Oracle:
//! iverilog -g2012.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> String {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("vita_xiw_{}_{n}.sv", std::process::id()));
    std::fs::write(&path, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(&path)
        .output()
        .expect("run vita");
    let _ = std::fs::remove_file(&path);
    let so = String::from_utf8_lossy(&out.stdout).into_owned();
    assert!(
        out.status.success(),
        "stderr:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let mut s = String::new();
    for l in so.lines().filter(|l| !l.starts_with("simulation ended")) {
        s.push_str(l);
        s.push('\n');
    }
    s
}

#[test]
fn x_index_plus_write_discards() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h1234; b = 'x; a[b+:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "1234\n");
}

#[test]
fn x_index_minus_write_discards() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h1234; b = 'x; a[b-:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "1234\n");
}

#[test]
fn z_index_plus_write_discards() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h1234; b = 'z; a[b+:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "1234\n");
}

#[test]
fn x_index_via_task_output_actual_discards() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           task t(output [3:0] o); o = 4'hF; endtask\n\
           initial begin a = 16'h1234; b = 'x; t(a[b+:4]); $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "1234\n");
}

#[test]
fn real_negative_one_index_still_partial_writes() {
    // CONTROL: a real -1 index is NOT unknown — P0-IPU partial-writes the in-range
    // bits (bits 0,1,2 of a[-1+:4]). Must NOT be swept up by the X discard.
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h1234; b = -1; a[b+:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "1237\n");
}

#[test]
fn real_negative_two_index_still_partial_writes() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h0000; b = -2; a[b+:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "0003\n");
}

#[test]
fn valid_index_write_unaffected() {
    let out = run("module top;\n\
           reg [15:0] a; integer b;\n\
           initial begin a = 16'h0000; b = 4; a[b+:4] = 4'hF; $display(\"%h\", a); end\n\
         endmodule\n");
    assert_eq!(out, "00f0\n");
}
