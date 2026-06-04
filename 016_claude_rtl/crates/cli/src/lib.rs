//! cli — the user-facing `vita` driver that wires the whole pipeline.
//!
//! Pipeline: read source(s) → (preprocess passthrough) → lex → parse →
//! elaborate → simulate → VCD. Diagnostics go to stderr through a concrete
//! [`StderrSink`] (the first real `diag::LogSink`); the numeric exit code follows
//! doc-13 §Exit codes:
//!
//! | code | meaning |
//! |------|---------|
//! | 0    | clean: parse+elaborate ok, simulation finished with no errors |
//! | 1    | user/design error: lex/parse errors, elaborate `None`, runtime `$fatal` |
//! | 3    | CLI/usage error: no source files, file not found, unknown applet |
//!
//! `main()` is a thin wrapper that parses argv, reads files, and calls
//! [`run_vita`]; the staged applets (`vcmp`/`velab`/`vrun`) are deferred stubs
//! (they need vita-artifact body serialization) and return 3.

use std::cell::Cell;

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity, SourceLoc};
use sim_engine::{ExitClass, FinishReason, SimOpts};

/// Exit code for a clean run (doc-13 §Exit codes).
pub const EXIT_OK: i32 = 0;
/// Exit code for a user/design error (lex/parse/elab/runtime-fatal).
pub const EXIT_USER_ERROR: i32 = 1;
/// Exit code for a CLI/usage error (no sources, file not found, unknown applet).
pub const EXIT_CLI_ERROR: i32 = 3;

/// Knobs the `vita` driver threads down into the pipeline. Kept tiny for v1 — the
/// full bucket-C flag surface (doc-13) lands with `vita-log`.
#[derive(Debug, Clone, Default)]
pub struct VitaOpts {
    /// Overrides the design's `$dumpfile` path (CLI `-o`). `None` ⇒ use `$dumpfile`.
    pub vcd_path_override: Option<String>,
}

impl VitaOpts {
    fn sim_opts(&self) -> SimOpts {
        SimOpts {
            vcd_path_override: self.vcd_path_override.clone(),
            ..SimOpts::default()
        }
    }
}

/// A minimal concrete `LogSink`: the first real sink in the workspace.
///
/// - `Diagnostic` → stderr as `<severity>[<CODE>]: <message>` (+ `file:line:col`
///   when a `location` is present).
/// - `Progress` / `RtlOutput` → stdout (the `$display` transcript + run summary).
///
/// Error/Fatal diagnostics bump an interior-mutable counter so the driver can
/// decide the exit code (the trait's `emit(&self)` forbids `&mut`).
pub struct StderrSink {
    errors: Cell<u32>,
    fatals: Cell<u32>,
}

impl StderrSink {
    pub fn new() -> Self {
        StderrSink {
            errors: Cell::new(0),
            fatals: Cell::new(0),
        }
    }

    /// Count of Error-severity diagnostics seen so far.
    pub fn error_count(&self) -> u32 {
        self.errors.get()
    }

    /// Count of Fatal-severity diagnostics seen so far.
    pub fn fatal_count(&self) -> u32 {
        self.fatals.get()
    }

    /// True if any Error or Fatal diagnostic was emitted.
    pub fn had_error_or_fatal(&self) -> bool {
        self.errors.get() > 0 || self.fatals.get() > 0
    }

    fn render_diagnostic(&self, d: &Diagnostic) {
        match d.severity {
            Severity::Error => self.errors.set(self.errors.get() + 1),
            Severity::Fatal => self.fatals.set(self.fatals.get() + 1),
            _ => {}
        }
        let head = format!(
            "{}[{}]: {}",
            d.severity.token(),
            d.code.code_num(),
            d.message
        );
        match &d.location {
            Some(loc) => eprintln!("{}:{}:{}: {}", loc.file, loc.line, loc.col, head),
            None => eprintln!("{head}"),
        }
    }
}

impl Default for StderrSink {
    fn default() -> Self {
        Self::new()
    }
}

impl LogSink for StderrSink {
    fn emit(&self, event: LogEvent) {
        match event {
            LogEvent::Diagnostic(d) => self.render_diagnostic(&d),
            LogEvent::Progress(p) => println!("{}", p.message),
            LogEvent::RtlOutput(t) => print!("{}", t.text),
        }
    }
}

/// Map a byte offset into `src` to a 1-based `(line, col)`. Columns count
/// Unicode scalar values from the last newline (good enough for v1 caret-less
/// reporting; the real side-table bridge lives in `vita-log`).
///
/// Retained per preprocess-spec §4.3: line/col resolution now flows through
/// `hdl_preprocess::SourceMap` (which carries a byte-identical copy of this
/// function), so this is currently unreferenced. It is kept as the reference
/// the SourceMap copy must agree with byte-for-byte.
#[allow(dead_code)]
fn byte_to_line_col(src: &str, byte: usize) -> (u32, u32) {
    // Clamp out-of-range, then floor to a UTF-8 char boundary so the
    // `src[line_start..byte]` slice cannot split a multibyte scalar. Mirrors
    // `hdl_preprocess::byte_to_line_col` byte-for-byte.
    let mut byte = byte.min(src.len());
    while byte > 0 && !src.is_char_boundary(byte) {
        byte -= 1;
    }
    let mut line = 1u32;
    let mut line_start = 0usize;
    for (i, c) in src.char_indices() {
        if i >= byte {
            break;
        }
        if c == '\n' {
            line += 1;
            line_start = i + 1;
        }
    }
    let col = src[line_start..byte].chars().count() as u32 + 1;
    (line, col)
}

/// Build a `SourceLoc` for the half-open expanded-byte range `[lo, hi)` by
/// resolving it through the preprocessor's `SourceMap` back to original positions.
fn loc_from_span(map: &hdl_preprocess::SourceMap, lo: usize, hi: usize) -> SourceLoc {
    map.resolve_span(lo, hi)
}

/// Emit a front-end (lex/parse) diagnostic with a resolved location.
fn emit_frontend_error(
    sink: &StderrSink,
    map: &hdl_preprocess::SourceMap,
    lo: usize,
    hi: usize,
    msg: String,
) {
    sink.emit(LogEvent::Diagnostic(Diagnostic {
        severity: Severity::Error,
        code: MsgCode::ParseUnexpectedToken,
        message: msg,
        location: Some(loc_from_span(map, lo, hi)),
        context: Vec::new(),
        sim_time: None,
    }));
}

/// Core: run the `vita` one-shot pipeline over already-read source `text`
/// (`file` is the display name used in diagnostics). Returns the process exit
/// code. This is the unit-test entry point — it never reads argv or files and
/// never calls `std::process::exit`.
pub fn run_vita_str(file: &str, text: &str, opts: &VitaOpts) -> i32 {
    let sink = StderrSink::new();

    // ── preprocess ─────────────────────────────────────────────────────────
    // raw source -> expanded text + SourceMap. The expanded text (not `text`) is
    // what the lexer and parser consume; spans they produce index the expanded
    // buffer and resolve back to original files via `pp.map`.
    let base_dir = std::path::Path::new(file)
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."));
    let pre_opts = hdl_preprocess::PreOpts::default(); // incdirs/-D wired from opts later
    let pp = hdl_preprocess::preprocess_str(base_dir, file, text, &pre_opts);
    for d in &pp.diags {
        let loc = pp.map.resolve_span(d.at, d.at);
        sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: d.severity,
            code: d.code,
            message: d.message.clone(),
            location: Some(loc),
            context: Vec::new(),
            sim_time: None,
        }));
    }
    if pp.has_errors() {
        return EXIT_USER_ERROR;
    }
    let expanded: &str = &pp.text;

    // ── lex ──────────────────────────────────────────────────────────────
    let (tokens, lex_errors) = hdl_lexer::lex(expanded);
    if !lex_errors.is_empty() {
        for e in &lex_errors {
            let (mnemonic, _) = e.kind.msg_code_hint();
            let msg = format!("lex error: {} ({mnemonic})", lex_error_message(e.kind));
            emit_frontend_error(&sink, &pp.map, e.span.start, e.span.end, msg);
        }
        return EXIT_USER_ERROR;
    }

    // ── parse ─────────────────────────────────────────────────────────────
    let (unit, parse_errors) = hdl_parser::parse(&tokens, expanded);
    if !parse_errors.is_empty() {
        for e in &parse_errors {
            let found = match e.found {
                Some(k) => format!("{k:?}"),
                None => "end of file".to_string(),
            };
            let msg = format!("expected {}, found {found}", e.expected);
            emit_frontend_error(&sink, &pp.map, e.span.lo as usize, e.span.hi as usize, msg);
        }
        return EXIT_USER_ERROR;
    }
    let Some(unit) = unit else {
        // Empty source with no errors: nothing to simulate. Treat as a usage
        // error — the user pointed `vita` at a file with no design units.
        sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Error,
            code: MsgCode::ParseUnexpectedToken,
            message: "no design units found in source".to_string(),
            location: None,
            context: Vec::new(),
            sim_time: None,
        }));
        return EXIT_USER_ERROR;
    };

    // ── elaborate ──────────────────────────────────────────────────────────
    // The elaborator emits its own diagnostics through `sink`; `None` ⇒ a hard
    // elaboration error was reported.
    let Some(ir) = elaborate::elaborate(&unit, &sink) else {
        return EXIT_USER_ERROR;
    };

    // ── simulate ────────────────────────────────────────────────────────────
    let result = sim_engine::simulate(&ir, &sink, opts.sim_opts());
    sim_exit_code(&result)
}

/// Map a finished `SimResult` to the doc-13 exit code. A clean `$finish`/quiescent
/// run with no error-or-fatal diagnostics is 0; anything else (`$fatal`, runtime
/// `$error`, delta-limit blowup) is a user/design error (1).
fn sim_exit_code(result: &sim_engine::SimResult) -> i32 {
    let clean_reason = matches!(
        result.finish_reason,
        FinishReason::Finish | FinishReason::Quiescent | FinishReason::Stop
    );
    match result.exit_class {
        ExitClass::Ok if clean_reason => EXIT_OK,
        _ => EXIT_USER_ERROR,
    }
}

/// Short human message for a lexer failure reason.
fn lex_error_message(kind: hdl_lexer::LexErrorKind) -> &'static str {
    use hdl_lexer::LexErrorKind as K;
    match kind {
        K::UnexpectedChar => "unexpected character",
        K::UnterminatedString => "unterminated string literal",
        K::UnterminatedBlockComment => "unterminated block comment",
        K::EmptyEscapedIdent => "empty escaped identifier",
        K::LoneSigil => "stray `$` or backtick with no identifier body",
    }
}

/// Run `vita` over one or more source files: read + concatenate (preprocess is a
/// passthrough), then drive the pipeline. Returns the process exit code.
///
/// File-read failures are CLI/usage errors (exit 3). With multiple files the
/// concatenated text uses the FIRST file's name in diagnostics (v1 — the §7
/// file_id→path bridge that disambiguates spans across files lands with vita-log).
pub fn run_vita(sources: &[String], opts: &VitaOpts) -> i32 {
    if sources.is_empty() {
        eprintln!(
            "error[{}]: no source files given",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    let mut text = String::new();
    for path in sources {
        match std::fs::read_to_string(path) {
            Ok(s) => {
                text.push_str(&s);
                // separate files with a newline so a missing trailing newline in
                // one file can't fuse tokens across the boundary.
                if !s.ends_with('\n') {
                    text.push('\n');
                }
            }
            Err(e) => {
                eprintln!(
                    "error[{}]: cannot read '{path}': {e}",
                    MsgCode::FlistNotFound.code_num()
                );
                return EXIT_CLI_ERROR;
            }
        }
    }
    let display_name = sources[0].as_str();
    run_vita_str(display_name, &text, opts)
}

/// Which multicall applet was requested (by `argv[0]` basename, or `vita <sub>`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Applet {
    /// The one-shot driver (implemented).
    Vita,
    /// A staged-flow applet (`vcmp`/`velab`/`vrun`) — deferred stub.
    Staged(&'static str),
}

/// Resolve the applet from `argv` (basename of `argv[0]`, then an optional
/// `vcmp`/`velab`/`vrun` subcommand for the `vita <applet>` explicit form).
/// Returns `(applet, remaining_args)` where `remaining_args` drops a consumed
/// subcommand token.
pub fn resolve_applet(argv: &[String]) -> (Applet, Vec<String>) {
    let base = argv
        .first()
        .map(std::path::Path::new)
        .and_then(|p| p.file_stem())
        .and_then(|s| s.to_str())
        .unwrap_or("vita");
    let rest = &argv[argv.len().min(1)..];
    match base {
        "vcmp" => (Applet::Staged("vcmp"), rest.to_vec()),
        "velab" => (Applet::Staged("velab"), rest.to_vec()),
        "vrun" => (Applet::Staged("vrun"), rest.to_vec()),
        _ => {
            // `vita` (or any other basename): allow an explicit `vita vcmp …` form.
            if let Some(sub) = rest.first().map(|s| s.as_str()) {
                if matches!(sub, "vcmp" | "velab" | "vrun") {
                    let staged: &'static str = match sub {
                        "vcmp" => "vcmp",
                        "velab" => "velab",
                        _ => "vrun",
                    };
                    return (Applet::Staged(staged), rest[1..].to_vec());
                }
            }
            (Applet::Vita, rest.to_vec())
        }
    }
}

/// The full multicall entry: dispatch on `argv[0]` basename / explicit subcommand,
/// then either run the one-shot pipeline or print the staged-flow stub. Returns
/// the process exit code. `main()` is a thin wrapper around this.
pub fn run(argv: &[String]) -> i32 {
    let (applet, args) = resolve_applet(argv);
    match applet {
        Applet::Vita => run_vita(&args, &VitaOpts::default()),
        Applet::Staged(name) => {
            eprintln!(
                "vitamin: {name}: staged flow not yet implemented (needs artifact serialization)"
            );
            EXIT_CLI_ERROR
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Read;

    /// Run `run_vita` against an on-disk temp file holding `src`; return the exit
    /// code. The temp path is unique per call so tests stay parallel-safe.
    fn run_on_temp(src: &str, opts: &VitaOpts) -> (i32, String) {
        let dir = std::env::temp_dir();
        let pid = std::process::id();
        let nonce = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let path = dir.join(format!("vita_cli_test_{pid}_{nonce}.sv"));
        std::fs::write(&path, src).unwrap();
        let code = run_vita(&[path.to_string_lossy().into_owned()], opts);
        let p = path.to_string_lossy().into_owned();
        let _ = std::fs::remove_file(&path);
        (code, p)
    }

    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

    const CLEAN_TB: &str =
        "module tb; reg a; initial begin a=1; $display(\"a=%b\",a); #5 $finish; end endmodule";

    #[test]
    fn clean_testbench_exits_zero_and_prints() {
        // The capture API proves the $display text; the exit code proves the flow.
        let (toks, lex_errs) = hdl_lexer::lex(CLEAN_TB);
        assert!(lex_errs.is_empty(), "lex: {lex_errs:?}");
        let (unit, perrs) = hdl_parser::parse(&toks, CLEAN_TB);
        assert!(perrs.is_empty(), "parse: {perrs:?}");
        let sink = StderrSink::new();
        let ir = elaborate::elaborate(&unit.unwrap(), &sink).expect("elaborate");
        let (result, stdout) = sim_engine::simulate_capture(&ir, SimOpts::default());
        assert!(stdout.contains("a=1"), "stdout was: {stdout:?}");
        assert_eq!(sim_exit_code(&result), EXIT_OK);

        // And the full run_vita path returns 0.
        let (code, _) = run_on_temp(CLEAN_TB, &VitaOpts::default());
        assert_eq!(code, EXIT_OK);
    }

    #[test]
    fn parse_error_exits_one() {
        // A `$display` with a missing `)` / `;` — guaranteed parse error.
        let bad = "module m; initial $display(\"x\" ; endmodule";
        let (code, _) = run_on_temp(bad, &VitaOpts::default());
        assert_eq!(code, EXIT_USER_ERROR);
    }

    #[test]
    fn lex_error_exits_one() {
        let bad = "module m; reg a; initial a = \"unterminated; endmodule";
        let (code, _) = run_on_temp(bad, &VitaOpts::default());
        assert_eq!(code, EXIT_USER_ERROR);
    }

    #[test]
    fn no_source_files_exits_three() {
        assert_eq!(run_vita(&[], &VitaOpts::default()), EXIT_CLI_ERROR);
    }

    #[test]
    fn missing_file_exits_three() {
        let missing = "/nonexistent/path/that/does/not/exist_vita.sv".to_string();
        assert_eq!(run_vita(&[missing], &VitaOpts::default()), EXIT_CLI_ERROR);
    }

    #[test]
    fn unknown_applet_via_run_exits_three() {
        // `vcmp` basename → staged stub → exit 3.
        let argv = vec!["/usr/local/bin/vcmp".to_string(), "top.sv".to_string()];
        assert_eq!(run(&argv), EXIT_CLI_ERROR);
        // explicit `vita vcmp …` form also routes to the stub.
        let argv = vec!["vita".to_string(), "vcmp".to_string(), "top.sv".to_string()];
        assert_eq!(run(&argv), EXIT_CLI_ERROR);
    }

    #[test]
    fn vita_basename_resolves_to_one_shot() {
        let argv = vec!["/usr/local/bin/vita".to_string(), "x.sv".to_string()];
        let (applet, rest) = resolve_applet(&argv);
        assert_eq!(applet, Applet::Vita);
        assert_eq!(rest, vec!["x.sv".to_string()]);
    }

    #[test]
    fn dumpvars_writes_vcd_with_enddefinitions() {
        let dir = std::env::temp_dir();
        let pid = std::process::id();
        let nonce = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        let vcd = dir.join(format!("vita_cli_test_{pid}_{nonce}.vcd"));
        let vcd_str = vcd.to_string_lossy().into_owned();
        let src = format!(
            "module tb; reg a; initial begin $dumpfile(\"{}\"); $dumpvars(0, tb); a=1; #5 $finish; end endmodule",
            vcd_str.replace('\\', "\\\\")
        );
        let opts = VitaOpts {
            vcd_path_override: Some(vcd_str.clone()),
        };
        let (code, _) = run_on_temp(&src, &opts);
        assert_eq!(code, EXIT_OK);
        assert!(vcd.exists(), "VCD not written at {vcd_str}");
        let mut contents = String::new();
        std::fs::File::open(&vcd)
            .unwrap()
            .read_to_string(&mut contents)
            .unwrap();
        assert!(
            contents.contains("$enddefinitions"),
            "VCD missing $enddefinitions:\n{contents}"
        );
        let _ = std::fs::remove_file(&vcd);
    }
}
