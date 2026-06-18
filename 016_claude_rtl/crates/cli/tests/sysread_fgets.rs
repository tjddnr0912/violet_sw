//! v9 `$fgets(str, fd)` (Medium-bundle rank 5, SYS-READ part 3a; pure IR-0).
//! A direct-rhs-of-blocking-assign special form in the $value$plusargs family:
//! it writes the str destination (arg 0) AND returns the byte count to the lhs.
//!
//! Every expected value is pinned to LIVE iverilog 13.0: $fgets reads up to the
//! destination width in WHOLE bytes (the FULL N, not C's N-1 — no NUL is
//! reserved) OR through a newline (retained), packs the bytes right-justified
//! MSB-first (first byte = most significant) with the high bytes zero-filled,
//! and returns the byte count. At EOF it returns 0 and leaves the destination
//! UNCHANGED.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str, files: &[(&str, &[u8])]) -> (String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_fgets_{}_{n}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    for (name, bytes) in files {
        std::fs::write(d.join(name), bytes).unwrap();
    }
    let f = d.join("t.sv");
    std::fs::write(&f, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(f.to_str().unwrap())
        .current_dir(&d)
        .output()
        .expect("run vita");
    (
        String::from_utf8_lossy(&out.stdout).into_owned(),
        out.status.code(),
    )
}

#[test]
fn fgets_line_with_newline_right_justified() {
    // "hello\nworld\n" into a 128-bit reg => n=6 each, bytes in the low 6 bytes
    // MSB-first ('h' high, '\n' low), high zero-filled; 3rd call EOF=0 unchanged.
    let (out, _c) = run(
        "module t;\n\
         reg [128:1] line; integer fd, n;\n\
         initial begin\n\
           fd = $fopen(\"in.txt\", \"r\");\n\
           n = $fgets(line, fd); $display(\"n1 %0d %h\", n, line);\n\
           n = $fgets(line, fd); $display(\"n2 %0d %h\", n, line);\n\
           n = $fgets(line, fd); $display(\"n3 %0d %h\", n, line);\n\
         end\n\
         endmodule\n",
        &[("in.txt", b"hello\nworld\n")],
    );
    assert!(
        out.contains("n1 6 0000000000000000000068656c6c6f0a"),
        "fgets line 1:\n{out}"
    );
    assert!(
        out.contains("n2 6 00000000000000000000776f726c640a"),
        "fgets line 2:\n{out}"
    );
    // EOF: n=0, destination UNCHANGED (still 'world\n').
    assert!(
        out.contains("n3 0 00000000000000000000776f726c640a"),
        "fgets EOF leaves dest unchanged:\n{out}"
    );
}

#[test]
fn fgets_full_width_stops_at_newline() {
    // 4-byte dest over "ABCDEFGHIJ\nXY\n": reads the FULL 4 bytes (not 3),
    // stopping early at a newline. s1=ABCD s2=EFGH s3=IJ\n(3) s4=XY\n(3) s5=0.
    let (out, _c) = run(
        "module t;\n\
         reg [32:1] buf4; integer fd, n;\n\
         initial begin\n\
           fd = $fopen(\"in.txt\", \"r\");\n\
           n = $fgets(buf4, fd); $display(\"s1 %0d %h\", n, buf4);\n\
           n = $fgets(buf4, fd); $display(\"s2 %0d %h\", n, buf4);\n\
           n = $fgets(buf4, fd); $display(\"s3 %0d %h\", n, buf4);\n\
           n = $fgets(buf4, fd); $display(\"s4 %0d %h\", n, buf4);\n\
           n = $fgets(buf4, fd); $display(\"s5 %0d %h\", n, buf4);\n\
         end\n\
         endmodule\n",
        &[("in.txt", b"ABCDEFGHIJ\nXY\n")],
    );
    assert!(out.contains("s1 4 41424344"), "{out}"); // ABCD
    assert!(out.contains("s2 4 45464748"), "{out}"); // EFGH
    assert!(out.contains("s3 3 00494a0a"), "{out}"); // IJ\n
    assert!(out.contains("s4 3 0058590a"), "{out}"); // XY\n
    assert!(out.contains("s5 0 0058590a"), "{out}"); // EOF, unchanged
}

#[test]
fn fgets_bad_fd_leaves_dest_unchanged() {
    // a failed $fopen => fd 0; $fgets returns 0 and does NOT touch the dest.
    let (out, _c) = run(
        "module t;\n\
         reg [32:1] buf4; integer fd, n;\n\
         initial begin\n\
           buf4 = 32'hdeadbeef;\n\
           fd = $fopen(\"/no/such/path/x\", \"r\");\n\
           n = $fgets(buf4, fd); $display(\"n %0d %h\", n, buf4);\n\
         end\n\
         endmodule\n",
        &[],
    );
    assert!(
        out.contains("n 0 deadbeef"),
        "bad-fd fgets unchanged:\n{out}"
    );
}

#[test]
fn fgets_nested_placement_is_loud() {
    let (out, code) = run(
        "module t;\n\
         reg [32:1] buf4; integer fd, x;\n\
         initial begin\n\
           fd = $fopen(\"in.txt\", \"r\");\n\
           x = $fgets(buf4, fd) + 1;\n\
         end\n\
         endmodule\n",
        &[("in.txt", b"AB")],
    );
    assert!(
        out.contains("VITA-E3009") || code == Some(1),
        "nested $fgets must be loud: {out} code={code:?}"
    );
}
