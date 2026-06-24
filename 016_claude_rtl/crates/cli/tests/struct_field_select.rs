//! READ sub-selecting a packed-struct member — `s.f[i]` / `s.f[a:b]` /
//! `s.f[base+:w]` / `s.f[base-:w]`. The parser desugars `s.f` to the field
//! part-select `pv = s[off+w-1:off]`; a trailing sub-select becomes one
//! `IndexedPart` on `pv`, so elaborate's `IndexedPart`-on-`PartSelect` fold keeps
//! it FIELD-bounded (out-of-field bits read X — they never leak into an adjacent
//! member).
//!
//! For a DESCENDING member (`logic [7:0] f`) field index i = `pv[i]` (identity);
//! oracle = iverilog directly. For an ASCENDING member (`logic [0:7] f`) field
//! index i = `pv[w-1-i]`, so `+:`/`-:` flip and the offset mirrors — vita
//! previously read the field as descending (silent-wrong: `a[0+:4]`=5 vs IEEE
//! `a`). iverilog is itself BUGGY on ascending struct fields, so the oracle is
//! the equivalent ascending NET `logic [0:7] a` (which iverilog handles
//! correctly — a struct field must match it).
//!
//! WRITES to a sub-field (`s.f[…] = …`) are a loud "nested lvalue select" in v1
//! (a field-bounded sub-field write needs elaborate lvalue support — follow-on).
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

fn vita(src: &str) -> std::process::Output {
    let n = NEXT.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!("vita_sfs_{}_{n}.sv", std::process::id()));
    std::fs::write(&path, src).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_vita"))
        .arg(&path)
        .output()
        .expect("run vita");
    let _ = std::fs::remove_file(&path);
    out
}

fn run(src: &str) -> String {
    let out = vita(src);
    assert!(
        out.status.success(),
        "vita failed:\n{}",
        String::from_utf8_lossy(&out.stderr)
    );
    let so = String::from_utf8_lossy(&out.stdout).into_owned();
    let mut s = String::new();
    for l in so.lines().filter(|l| {
        !l.starts_with("simulation ended") && !l.contains("VITA-W1017") && !l.trim().is_empty()
    }) {
        s.push_str(l.trim());
        s.push('\n');
    }
    s
}

/// Assert vita loudly refuses (nonzero exit) — a field-bounded write isn't v1.
fn run_loud(src: &str) {
    let out = vita(src);
    assert!(
        !out.status.success(),
        "expected a loud refusal, but vita succeeded:\n{}",
        String::from_utf8_lossy(&out.stdout)
    );
}

// ── ASCENDING member `logic [0:7] a` (oracle: equivalent ascending net) ──────

#[test]
fn asc_read_all_forms_off0() {
    // a = 8'hA5; idx0 = MSB. a[0+:4]=hi nibble=a, a[4+:4]=lo=5, a[2]=1,
    // a[1:3]=010=2, a[5-:2]=a[4:5]=01=1. (matches `logic [0:7]` net under iverilog)
    let out = run("module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5;\n\
          $display(\"%h %h %b %h %h\", s.a[0+:4], s.a[4+:4], s.a[2], s.a[1:3], s.a[5-:2]);\n\
        end\n\
      endmodule\n");
    assert_eq!(out, "a 5 1 2 1\n");
}

#[test]
fn asc_read_all_forms_nonzero_offset() {
    // `a` now occupies flat bits [11:4] (off=4). The field VALUE is unchanged,
    // so the sub-select results must be identical to off=0.
    let out = run("module top;\n\
        typedef struct packed { logic [0:7] a; logic [3:0] tl; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.tl = 4'h0;\n\
          $display(\"%h %h %b %h %h\", s.a[0+:4], s.a[4+:4], s.a[2], s.a[1:3], s.a[5-:2]);\n\
        end\n\
      endmodule\n");
    assert_eq!(out, "a 5 1 2 1\n");
}

#[test]
fn asc_read_runtime_index() {
    // Runtime bit-select / indexed offset on an ascending field.
    let out = run("module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s; integer k;\n\
        initial begin s.a = 8'hA5; k = 2;\n\
          $display(\"%b %h\", s.a[k], s.a[k+:2]);\n\
        end\n\
      endmodule\n");
    // ascending net oracle: a[2]=1, a[2+:2]=a[2:3]=10=2.
    assert_eq!(out, "1 2\n");
}

// ── DESCENDING member `logic [7:0] a` (oracle: iverilog directly) ────────────

#[test]
fn desc_read_all_forms() {
    let out = run("module top;\n\
        typedef struct packed { logic [7:0] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5;\n\
          $display(\"%h %h %b %h %h\", s.a[0+:4], s.a[4+:4], s.a[2], s.a[3:1], s.a[5-:2]);\n\
        end\n\
      endmodule\n");
    assert_eq!(out, "5 a 1 2 2\n");
}

#[test]
fn desc_read_runtime_index() {
    let out = run("module top;\n\
        typedef struct packed { logic [7:0] a; logic [7:0] b; } st_t;\n\
        st_t s; integer k;\n\
        initial begin s.a = 8'hA5; k = 2;\n\
          $display(\"%b %h\", s.a[k], s.a[k+:2]);\n\
        end\n\
      endmodule\n");
    // descending net oracle: a[2]=1, a[2+:2]=a[3:2]=01=1.
    assert_eq!(out, "1 1\n");
}

// ── FIELD-bounded: an out-of-field read is X, never a neighbouring member ────

#[test]
fn oob_read_is_x_not_leak_low_field() {
    // `a` is the LOW member (off=0) with `pad`=FF directly above it. A partial-OOB
    // select must read X for the out-of-field bits, NOT pad's bits (no leak).
    let out = run("module top;\n\
        typedef struct packed { logic [7:0] pad; logic [7:0] a; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.pad = 8'hFF;\n\
          $display(\"%b %b\", s.a[6+:4], s.a[9]);\n\
        end\n\
      endmodule\n");
    // descending net oracle: a[6+:4]=bits 6,7,8(oob),9(oob)=xx10 ; a[9]=x.
    assert_eq!(out, "xx10 x\n");
}

#[test]
fn oob_read_is_x_not_leak_ascending() {
    let out = run("module top;\n\
        typedef struct packed { logic [7:0] pad; logic [0:7] a; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.pad = 8'hFF;\n\
          $display(\"%b %b\", s.a[6+:4], s.a[9]);\n\
        end\n\
      endmodule\n");
    // ascending net oracle.
    assert_eq!(out, "01xx x\n");
}

#[test]
fn oob_regular_range_x_extends_correct_end() {
    // An out-of-field regular range must X-extend on the IEEE-correct end: for an
    // ascending field `a[0:9]` the OOB high indices (8,9 = LSB end) read X →
    // `10100101xx`; for a descending field `a[9:0]` the OOB high bits (MSB end) →
    // `xx10100101`. (Normalizing `[a:b]` to the validated indexed path; a naive
    // offset clamp put the X bits on the wrong end — a silent-wrong.)
    let asc = run("module top;\n\
        typedef struct packed { logic [7:0] pad; logic [0:7] a; } st_t;\n\
        st_t s;\n\
        initial begin s.pad = 8'hFF; s.a = 8'hA5; $display(\"%b\", s.a[0:9]); end\n\
      endmodule\n");
    assert_eq!(asc, "10100101xx\n");
    let desc = run("module top;\n\
        typedef struct packed { logic [7:0] pad; logic [7:0] a; } st_t;\n\
        st_t s;\n\
        initial begin s.pad = 8'hFF; s.a = 8'hA5; $display(\"%b\", s.a[9:0]); end\n\
      endmodule\n");
    assert_eq!(desc, "xx10100101\n");
}

// ── A reversed regular range (against the member's direction) is loud ────────

#[test]
fn asc_reversed_range_is_loud() {
    // `logic [0:7]` is ascending; `s.a[3:0]` runs the wrong way → loud (it was a
    // silent-wrong: vita read it as a flat descending slice).
    run_loud(
        "module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; $display(\"%h\", s.a[3:0]); end\n\
      endmodule\n",
    );
}

#[test]
fn desc_reversed_range_is_loud() {
    run_loud(
        "module top;\n\
        typedef struct packed { logic [7:0] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; $display(\"%h\", s.a[0:3]); end\n\
      endmodule\n",
    );
}

// ── Whole-field access unchanged (regression guard) ──────────────────────────

#[test]
fn whole_field_read_unchanged() {
    let out = run("module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.b = 8'h3C; $display(\"%h %h\", s.a, s.b); end\n\
      endmodule\n");
    assert_eq!(out, "a5 3c\n");
}

// ── Sub-field WRITE is a loud "nested lvalue select" in v1 (follow-on) ────────

#[test]
fn asc_subfield_write_is_loud() {
    run_loud(
        "module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.a[0+:4] = 4'hF; $display(\"%h\", s.a); end\n\
      endmodule\n",
    );
}

#[test]
fn desc_subfield_write_is_loud() {
    run_loud(
        "module top;\n\
        typedef struct packed { logic [7:0] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'hA5; s.a[0+:4] = 4'hF; $display(\"%h\", s.a); end\n\
      endmodule\n",
    );
}

// ── Whole-field WRITE still works (regression guard) ─────────────────────────

#[test]
fn whole_field_write_unchanged() {
    let out = run("module top;\n\
        typedef struct packed { logic [0:7] a; logic [7:0] b; } st_t;\n\
        st_t s;\n\
        initial begin s.a = 8'h00; s.a = 8'hA5; $display(\"%h\", s.a); end\n\
      endmodule\n");
    assert_eq!(out, "a5\n");
}
