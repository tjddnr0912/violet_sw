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
