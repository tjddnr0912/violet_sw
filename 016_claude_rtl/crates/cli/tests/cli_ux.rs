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
