//! v7 P2-C `string` type — heap-handle storage (dyn precedent): reads
//! materialize a packed-ASCII value (8×len, is_str-flagged so context
//! resizing never truncates), writes strip leading NULs (IEEE §6.16),
//! comparisons route through StrCmp (lexicographic — packed zero-extension
//! is NOT lexicographic for unequal lengths). iverilog 13.0 live pins
//! (probe t18): decl/assign/%s/len/substr/relationals/packed-conversion/
//! $sformatf. toupper/tolower/getc/putc/compare are hand-IEEE §6.16 pins —
//! iverilog 13 rejects those methods outright.
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn run(src: &str) -> (String, String, Option<i32>) {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let d = std::env::temp_dir().join(format!("vita_str_{}_{n}", std::process::id()));
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
fn string_assign_display_len_substr() {
    // iverilog-pinned: s=hello| len=5 / sub=ell (inclusive byte range) /
    // empty prints empty with len 0.
    let (out, err, code) = run("module top;\n\
         string s, t;\n\
         initial begin\n\
           s = \"hello\";\n\
           $display(\"s=%s| len=%0d\", s, s.len());\n\
           $display(\"sub=%s\", s.substr(1, 3));\n\
           t = \"\";\n\
           $display(\"empty=[%s] elen=%0d\", t, t.len());\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("s=hello| len=5"), "got:\n{out}");
    assert!(out.contains("sub=ell"), "got:\n{out}");
    assert!(out.contains("empty=[] elen=0"), "got:\n{out}");
}

#[test]
fn string_relationals_are_lexicographic() {
    // iverilog-pinned: "hello" vs "hellp" → eq=0 ne=1 lt=1 gt=0; and the
    // unequal-length case packed compare gets WRONG: "ab" < "abc" is true.
    let (out, err, code) = run("module top;\n\
         string s, t;\n\
         initial begin\n\
           s = \"hello\"; t = \"hellp\";\n\
           $display(\"eq=%b ne=%b lt=%b gt=%b\", s == t, s != t, s < t, s > t);\n\
           s = \"ab\";\n\
           $display(\"cmplit=%b %b\", s == \"ab\", s < \"abc\");\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("eq=0 ne=1 lt=1 gt=0"), "got:\n{out}");
    assert!(out.contains("cmplit=1 1"), "got:\n{out}");
}

#[test]
fn packed_to_string_conversion_strips_nuls() {
    // iverilog-pinned: a 64-bit holding "ab" converts to len-2 "ab".
    let (out, err, code) = run("module top;\n\
         string s;\n\
         reg [63:0] packed_v;\n\
         initial begin\n\
           packed_v = \"ab\";\n\
           s = packed_v;\n\
           $display(\"frompacked=%s flen=%0d\", s, s.len());\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("frompacked=ab flen=2"), "got:\n{out}");
}

#[test]
fn sformatf_into_string_and_packed() {
    // iverilog-pinned: fmt=x=42/yo flen2=7.
    let (out, err, code) = run("module top;\n\
         string s;\n\
         initial begin\n\
           s = $sformatf(\"x=%0d/%s\", 42, \"yo\");\n\
           $display(\"fmt=%s flen2=%0d\", s, s.len());\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("fmt=x=42/yo flen2=7"), "got:\n{out}");
}

#[test]
fn hand_ieee_methods_toupper_getc_putc_compare() {
    // hand-IEEE §6.16 pins (iverilog 13 rejects these methods): getc returns
    // the byte, putc writes in place (OOB/NUL = no-op), toupper/tolower map
    // ASCII, compare() is the strcmp-style backing of the relationals.
    let (out, err, code) = run("module top;\n\
         string s;\n\
         integer c, r;\n\
         initial begin\n\
           s = \"Hello\";\n\
           c = s.getc(1);\n\
           $display(\"getc=%0d\", c);\n\
           $display(\"up=%s low=%s\", s.toupper(), s.tolower());\n\
           s.putc(0, 104);\n\
           $display(\"putc=%s\", s);\n\
           s.putc(99, 65);\n\
           $display(\"oob=%s\", s);\n\
           r = s.compare(\"hello\");\n\
           $display(\"cmp=%0d\", r);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("getc=101"), "got:\n{out}"); // 'e'
    assert!(out.contains("up=HELLO low=hello"), "got:\n{out}");
    assert!(out.contains("putc=hello"), "got:\n{out}");
    assert!(out.contains("oob=hello"), "got:\n{out}");
    assert!(out.contains("cmp=0"), "got:\n{out}");
}

#[test]
fn sformat_task_writes_dest() {
    let (out, err, code) = run("module top;\n\
         string s;\n\
         initial begin\n\
           $sformat(s, \"n=%0d\", 7);\n\
           $display(\"sf=%s\", s);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("sf=n=7"), "got:\n{out}");
}

#[test]
fn string_concat_is_loud_use_sformatf() {
    let (_o, err, code) = run("module top;\n\
         string a, b, c;\n\
         initial begin\n\
           a = \"x\"; b = \"y\";\n\
           c = {a, b};\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_ne!(code, Some(0));
    assert!(err.contains("E3009"), "stderr:\n{err}");
}

#[test]
fn string_in_nba_and_if_condition() {
    // NBA to a string rides the same write funnel; equality in an `if`.
    // hand-IEEE pin: iverilog 13's vvp INTERNAL-ERRORS on a string NBA
    // ("recv_vec4 not implemented"), so there is no oracle lane here.
    let (out, err, code) = run("module top;\n\
         string s;\n\
         initial begin\n\
           s <= \"go\";\n\
           #1;\n\
           if (s == \"go\") $display(\"nba_ok\");\n\
           else $display(\"nba_bad=%s\", s);\n\
           $finish;\n\
         end\n\
         endmodule\n");
    assert_eq!(code, Some(0), "stderr:\n{err}");
    assert!(out.contains("nba_ok"), "got:\n{out}");
}
