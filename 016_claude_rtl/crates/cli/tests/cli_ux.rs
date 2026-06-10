//! P2-4: `--help`/`--version` first-impression UX. Before this fix
//! `vita --help` tried to READ a file named `--help` (exit 3, confusing error).
use std::process::Command;

fn vita(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_vita"))
        .args(args)
        .output()
        .expect("run vita")
}

#[test]
fn help_prints_usage_and_exits_zero() {
    let out = vita(&["--help"]);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert_eq!(out.status.code(), Some(0), "stdout:\n{stdout}");
    assert!(stdout.contains("Usage"), "got:\n{stdout}");
    assert!(stdout.contains("vita"), "got:\n{stdout}");
}

#[test]
fn short_help_flag_works() {
    let out = vita(&["-h"]);
    assert_eq!(out.status.code(), Some(0));
    assert!(String::from_utf8_lossy(&out.stdout).contains("Usage"));
}

#[test]
fn version_prints_and_exits_zero() {
    let out = vita(&["--version"]);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert_eq!(out.status.code(), Some(0));
    assert!(stdout.contains(env!("CARGO_PKG_VERSION")), "got:\n{stdout}");
}

#[test]
fn staged_applet_help_via_subcommand() {
    let out = vita(&["vrun", "--help"]);
    let stdout = String::from_utf8_lossy(&out.stdout);
    assert_eq!(out.status.code(), Some(0), "got:\n{stdout}");
    assert!(stdout.contains("Usage"), "got:\n{stdout}");
    assert!(stdout.contains("vrun"), "got:\n{stdout}");
}

// ── P4-T1: `--threads N` / `-j N` / VITA_THREADS ────────────────────────────

fn write_tmp(name: &str, body: &str) -> std::path::PathBuf {
    let p = std::env::temp_dir().join(format!("vita_ux_{}_{name}", std::process::id()));
    std::fs::write(&p, body).unwrap();
    p
}

const DUMP_TB: &str = r#"
module tb;
  reg clk; reg [15:0] n; integer k;
  always @(posedge clk) n <= n + 16'd1;
  initial begin
    $dumpfile("d.vcd"); $dumpvars;
    clk = 0; n = 0;
    for (k = 0; k < 200; k = k + 1) begin #1 clk = 1; #1 clk = 0; end
    $finish;
  end
endmodule
"#;

/// `--threads 1` vs `--threads 4`: accepted on the one-shot applet, and the
/// VCD artifact is byte-identical (the P4 contract).
#[test]
fn threads_flag_byte_identical_vcd() {
    let src = write_tmp("thr.sv", DUMP_TB);
    let v1 = std::env::temp_dir().join(format!("vita_ux_{}_t1.vcd", std::process::id()));
    let v4 = std::env::temp_dir().join(format!("vita_ux_{}_t4.vcd", std::process::id()));
    let o1 = vita(&[
        src.to_str().unwrap(),
        "-o",
        v1.to_str().unwrap(),
        "--threads",
        "1",
    ]);
    let o4 = vita(&[src.to_str().unwrap(), "-o", v4.to_str().unwrap(), "-j", "4"]);
    assert_eq!(
        o1.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&o1.stderr)
    );
    assert_eq!(
        o4.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&o4.stderr)
    );
    let b1 = std::fs::read(&v1).expect("threads=1 VCD");
    let b4 = std::fs::read(&v4).expect("threads=4 VCD");
    assert!(b1.len() > 500, "real VCD expected");
    assert_eq!(b1, b4, "VCD must be byte-identical across thread counts");
    for p in [&src, &v1, &v4] {
        let _ = std::fs::remove_file(p);
    }
}

/// An unparsable `--threads` value is a CLI usage error (exit 3).
#[test]
fn threads_invalid_value_exits_three() {
    let src = write_tmp("thrbad.sv", "module t; endmodule");
    let out = vita(&[src.to_str().unwrap(), "--threads", "abc"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(out.status.code(), Some(3));
}

/// `VITA_THREADS` env applies when no flag is given (flag wins otherwise).
#[test]
fn threads_env_accepted() {
    let src = write_tmp("threnv.sv", DUMP_TB);
    let v = std::env::temp_dir().join(format!("vita_ux_{}_env.vcd", std::process::id()));
    let out = std::process::Command::new(env!("CARGO_BIN_EXE_vita"))
        .args([src.to_str().unwrap(), "-o", v.to_str().unwrap()])
        .env("VITA_THREADS", "4")
        .output()
        .expect("run vita");
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(v.exists(), "VCD written under VITA_THREADS=4");
    for p in [&src, &v] {
        let _ = std::fs::remove_file(p);
    }
}

// ── P2-9: `--timeout <ticks>` CI killswitch ─────────────────────────────────

/// A design that never `$finish`es is bounded by `--timeout` (clean exit 0).
#[test]
fn timeout_bounds_endless_design() {
    let src = write_tmp(
        "tmo.sv",
        "module t; reg clk; initial clk = 0; always #1 clk = ~clk; endmodule",
    );
    let out = vita(&[src.to_str().unwrap(), "--timeout", "200"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
}

#[test]
fn timeout_invalid_value_exits_three() {
    let src = write_tmp("tmobad.sv", "module t; endmodule");
    let out = vita(&[src.to_str().unwrap(), "--timeout", "soon"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(out.status.code(), Some(3));
}

// ── P2-12: defensive clamp of the VCD `$timescale` unit renderer ─────────────

#[test]
fn timescale_unit_string_clamps_to_vcd_range() {
    // VCD admits only 1|10|100 × s..fs (exp ∈ [-15, +2]). Out-of-range
    // exponents must saturate, never misrender (old fallback: -16 → "100s").
    assert_eq!(cli::timescale_unit_string(-16), "1fs");
    assert_eq!(cli::timescale_unit_string(3), "100s");
    // Boundaries and representative in-range values keep exact rendering.
    assert_eq!(cli::timescale_unit_string(-15), "1fs");
    assert_eq!(cli::timescale_unit_string(2), "100s");
    assert_eq!(cli::timescale_unit_string(-9), "1ns");
    assert_eq!(cli::timescale_unit_string(-10), "100ps");
}

#[test]
fn out_clobbering_input_dot_spelling_rejected() {
    // P2-12 regression: `-o` naming an input through a different spelling
    // (./x.sv vs x.sv) is caught by canonicalization — exit 3, input intact.
    let src = write_tmp("clob.sv", "module m; endmodule\n");
    let dotted = format!(
        "{}/./{}",
        src.parent().unwrap().display(),
        src.file_name().unwrap().to_string_lossy()
    );
    let out = vita(&["vcmp", &dotted, "-o", src.to_str().unwrap()]);
    let body = std::fs::read_to_string(&src).unwrap();
    let _ = std::fs::remove_file(&src);
    assert_eq!(out.status.code(), Some(3));
    assert_eq!(body, "module m; endmodule\n", "input must be untouched");
}

// ── Phase-1.x D: -Wno-<CODE> / -Werror[=<CODE>] gates + exit class 2 ─────────

/// A design that always emits W1017 (no `timescale) and finishes cleanly.
fn warning_design(name: &str) -> std::path::PathBuf {
    write_tmp(name, "module t; initial $finish; endmodule\n")
}

#[test]
fn wno_suppresses_a_warning() {
    let src = warning_design("wno.sv");
    let base = vita(&[src.to_str().unwrap()]);
    let gated = vita(&[src.to_str().unwrap(), "-Wno-W-PP-TIMESCALE-DEFAULT"]);
    let _ = std::fs::remove_file(&src);
    assert!(
        String::from_utf8_lossy(&base.stderr).contains("VITA-W1017"),
        "baseline must warn"
    );
    assert_eq!(gated.status.code(), Some(0));
    assert!(
        !String::from_utf8_lossy(&gated.stderr).contains("VITA-W1017"),
        "suppressed warning must not print"
    );
}

#[test]
fn werror_promotes_warnings_and_fails() {
    let src = warning_design("werr.sv");
    let out = vita(&[src.to_str().unwrap(), "-Werror"]);
    let _ = std::fs::remove_file(&src);
    let err = String::from_utf8_lossy(&out.stderr);
    assert_eq!(out.status.code(), Some(1), "promoted warning must fail");
    // Rendered as an ERROR but keeps its original (stable) code number.
    assert!(
        err.contains("error[VITA-W1017]"),
        "promotion renders error with the original code, got:\n{err}"
    );
}

#[test]
fn werror_targeted_hits_only_that_code() {
    let src = warning_design("werrt.sv");
    let hit = vita(&[src.to_str().unwrap(), "-Werror=W-PP-TIMESCALE-DEFAULT"]);
    let miss = vita(&[src.to_str().unwrap(), "-Werror=W-PP-MACRO-REDEFINED"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(hit.status.code(), Some(1));
    assert_eq!(
        miss.status.code(),
        Some(0),
        "unrelated promotion must not fire"
    );
}

#[test]
fn gate_flag_with_unknown_mnemonic_is_cli_error() {
    let src = warning_design("wbad.sv");
    let out = vita(&[src.to_str().unwrap(), "-Wno-NOT-A-REAL-CODE"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(out.status.code(), Some(3));
    assert!(String::from_utf8_lossy(&out.stderr).contains("VITA-E0001"));
}

#[test]
fn errors_are_never_suppressible() {
    // -Wno- of an Error code is accepted (valid mnemonic) but has no effect:
    // the always-logged spine keeps every Error/Fatal.
    let src = write_tmp(
        "wnoerr.sv",
        "module t; initial x = 1; endmodule\n", // undeclared name → E3010
    );
    let out = vita(&[src.to_str().unwrap(), "-Wno-E-ELAB-UNRESOLVED-NAME"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        String::from_utf8_lossy(&out.stderr).contains("VITA-E3010"),
        "errors must still print under -Wno-"
    );
}

#[test]
fn promoted_runtime_warning_fails_run() {
    // doc-13: `-Werror=W-RUN-USER-WARNING` turns RTL $warning into a CI failure
    // without editing the RTL.
    let src = write_tmp(
        "werrrun.sv",
        "`timescale 1ns/1ns\nmodule t; initial begin $warning(\"w\"); $finish; end endmodule\n",
    );
    let ok = vita(&[src.to_str().unwrap()]);
    let promoted = vita(&[src.to_str().unwrap(), "-Werror=W-RUN-USER-WARNING"]);
    let _ = std::fs::remove_file(&src);
    assert_eq!(ok.status.code(), Some(0));
    assert_eq!(promoted.status.code(), Some(1));
}

#[test]
fn artifact_gate_failure_exits_class_two() {
    // doc-13 exit table: stale/artifact gates are class 2 — CI re-runs
    // vcmp/velab instead of debugging RTL. Garbage header → magic mismatch.
    let bad = write_tmp("garbage.velab", "this is not a velab artifact\n");
    let out = vita(&["vrun", bad.to_str().unwrap()]);
    let _ = std::fs::remove_file(&bad);
    assert_eq!(out.status.code(), Some(2), "artifact gate must exit 2");
    assert!(String::from_utf8_lossy(&out.stderr).contains("VITA-E9001"));
}
