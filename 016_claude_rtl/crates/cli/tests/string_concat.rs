//! String concatenation `c = {a, b, …}` (IEEE §6.16, §11.4.12) where the parts
//! are strings. Previously loud-rejected ("use $sformatf"); now desugared to the
//! existing $sformatf("%s%s…", a, b, …) string-render machinery when it is the
//! direct rhs of a string assignment. Oracle: iverilog -g2012.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> String {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("vita_strcat_{}_{n}.sv", std::process::id()));
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
fn two_string_vars() {
    let out = run("module t;\n\
           string a, b, c;\n\
           initial begin a = \"Hello\"; b = \"World\"; c = {a, b}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "HelloWorld\n");
}

#[test]
fn mixed_vars_and_literals() {
    let out = run("module t;\n\
           string a, b, c;\n\
           initial begin a = \"Hello\"; b = \"World\";\n\
             c = {a, \", \", b, \"!\"}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "Hello, World!\n");
}

#[test]
fn leading_literal() {
    let out = run("module t;\n\
           string a, c;\n\
           initial begin a = \"Hello\"; c = {\"x\", a}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "xHello\n");
}

#[test]
fn all_literals() {
    let out = run("module t;\n\
           string c;\n\
           initial begin c = {\"ab\", \"cd\", \"ef\"}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "abcdef\n");
}

#[test]
fn integral_byte_element() {
    // IEEE §6.16: an integral concat element is its character bytes (byte 67 = 'C').
    let out = run("module t;\n\
           string a, c; byte ch;\n\
           initial begin a = \"AB\"; ch = 67; c = {a, ch}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "ABC\n");
}

#[test]
fn string_replication() {
    let out = run("module t;\n\
           string a, c;\n\
           initial begin a = \"AB\"; c = {3{a}}; $display(\"%s\", c); end\n\
         endmodule\n");
    assert_eq!(out, "ABABAB\n");
}

#[test]
fn concat_then_reuse() {
    // The destination may also appear on the rhs (a = {a, b} grows a).
    let out = run("module t;\n\
           string a, b;\n\
           initial begin a = \"x\"; b = \"y\"; a = {a, b}; a = {a, b}; $display(\"%s\", a); end\n\
         endmodule\n");
    assert_eq!(out, "xyy\n");
}
