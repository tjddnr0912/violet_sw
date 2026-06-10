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
//! [`run_vita`]; the staged applets ([`run_vcmp`]/[`run_velab`]/[`run_vrun`])
//! serialize the front-end `SourceUnit` to a `.vu`, elaborate it to a `.velab`
//! (golden `SimIr` frame + non-golden `ForkModeTable` trailer), and simulate it,
//! with a `schema_hash` staleness gate between every stage.

use std::cell::Cell;

use diag::{Diagnostic, LogEvent, LogSink, MsgCode, Severity, SourceLoc};
use sim_engine::{ExitClass, FinishReason, SimOpts};

/// Exit code for a clean run (doc-13 §Exit codes).
pub const EXIT_OK: i32 = 0;
/// Exit code for a user/design error (lex/parse/elab/runtime-fatal).
pub const EXIT_USER_ERROR: i32 = 1;
/// Exit code for a stale/artifact-gate rejection (doc-13 class 2): magic/
/// schema/format/version mismatches. Distinct from 1 so CI re-runs vcmp/velab
/// instead of debugging RTL.
pub const EXIT_STALE: i32 = 2;
/// Exit code for a CLI/usage error (no sources, file not found, unknown applet).
pub const EXIT_CLI_ERROR: i32 = 3;

mod filelist;

/// Knobs the `vita` driver threads down into the pipeline. Kept tiny for v1 — the
/// full bucket-C flag surface (doc-13) lands with `vita-log`.
#[derive(Debug, Clone, Default)]
pub struct VitaOpts {
    /// Overrides the design's `$dumpfile` path (CLI `-o`). `None` ⇒ use `$dumpfile`.
    pub vcd_path_override: Option<String>,
    /// Worker-thread budget (P4-T1, CLI `--threads N`/`-j N`). `None` ⇒ auto:
    /// `VITA_THREADS` env if set, else `min(available_parallelism, 8)`. Output is
    /// byte-identical for every value (the P4 contract) — wall-clock only.
    pub threads: Option<u32>,
    /// Hard cap on advanced simulation time in ticks (CLI `--timeout N`, P2-9).
    /// Reaching it ends the run cleanly (Quiescent) — a CI killswitch for
    /// designs that never `$finish`. `None` ⇒ unbounded.
    pub time_limit: Option<u64>,
    /// Diagnostic suppress/promote policy (`-Wno-*` / `-Werror[=*]`, doc-13
    /// bucket C). Pure output-stream filtering — never hashed into artifacts.
    pub gate: vita_log::GatePolicy,
}

impl VitaOpts {
    fn sim_opts(&self) -> SimOpts {
        SimOpts {
            vcd_path_override: self.vcd_path_override.clone(),
            threads: resolve_threads(self.threads),
            time_limit: self.time_limit,
            ..SimOpts::default()
        }
    }
}

/// P4-T1 thread-count resolution: explicit flag > `VITA_THREADS` env > auto
/// (`min(available_parallelism, 8)`). Clamped to ≥1. The count never changes
/// output bytes — only wall-clock — so "auto" is safe as the default.
fn resolve_threads(flag: Option<u32>) -> u32 {
    flag.or_else(|| {
        std::env::var("VITA_THREADS")
            .ok()
            .and_then(|v| v.parse::<u32>().ok())
    })
    .unwrap_or_else(|| {
        std::thread::available_parallelism()
            .map(|n| n.get() as u32)
            .unwrap_or(1)
            .min(8)
    })
    .max(1)
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
    sink: &dyn LogSink,
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

/// Read a single source file, then run the preprocess→lex→parse front-end,
/// emitting any diagnostics through `sink`. Returns `Some(unit)` on a clean
/// parse, `None` if read / preprocess / lex / parse failed OR the parse produced
/// no design units (the caller maps `None` to `EXIT_USER_ERROR`; a single-file
/// read failure also returns `None` after no emit — callers that need exit-3 on a
/// missing file read it themselves first).
///
/// The full pipeline (incl. the preprocessor) runs even for directive-free input,
/// so byte offsets / spans match the production one-shot path exactly. The staged
/// `vcmp` path and the round-trip tests parse through this same function so the
/// comparison never silently depends on a preprocessor bypass.
pub fn frontend_to_unit(file: &str, sink: &dyn LogSink) -> Option<hdl_ast::SourceUnit> {
    let text = std::fs::read_to_string(file).ok()?;
    let text = if text.ends_with('\n') {
        text
    } else {
        format!("{text}\n")
    };
    // `vcmp` serializes only the SourceUnit to `.vu`; timescale resolution happens at
    // `velab` (one-shot) time where it can ride into the SimIr-bearing `.velab`.
    frontend_text_to_unit(file, &text, sink).map(|(u, _)| u)
}

/// The preprocess→lex→parse core, factored so the one-shot driver, multi-file
/// `vcmp` (which concatenates first), and single-file [`frontend_to_unit`] all
/// share one implementation. Returns `None` (after emitting) on any front-end
/// error or an empty unit. `file` is the display name used in diagnostics; `text`
/// is the already-read source buffer.
pub fn frontend_text_to_unit(
    file: &str,
    text: &str,
    sink: &dyn LogSink,
) -> Option<(hdl_ast::SourceUnit, hdl_preprocess::ResolvedTimescales)> {
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
        return None;
    }
    let expanded: &str = &pp.text;

    // ── lex ──────────────────────────────────────────────────────────────
    let (tokens, lex_errors) = hdl_lexer::lex(expanded);
    if !lex_errors.is_empty() {
        for e in &lex_errors {
            let (mnemonic, _) = e.kind.msg_code_hint();
            let msg = format!("lex error: {} ({mnemonic})", lex_error_message(e.kind));
            emit_frontend_error(sink, &pp.map, e.span.start, e.span.end, msg);
        }
        return None;
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
            emit_frontend_error(sink, &pp.map, e.span.lo as usize, e.span.hi as usize, msg);
        }
        return None;
    }
    let Some(unit) = unit else {
        // Empty source with no errors: nothing to simulate. Treat as a usage
        // error — the user pointed the tool at a file with no design units.
        sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Error,
            code: MsgCode::ParseUnexpectedToken,
            message: "no design units found in source".to_string(),
            location: None,
            context: Vec::new(),
            sim_time: None,
        }));
        return None;
    };
    // Resolve each module's `timescale by file order (region offsets and module spans
    // share the expanded-text coordinate space). The result rides into elaborate.
    let modules: Vec<(&str, usize)> = unit
        .items
        .iter()
        .filter_map(|it| match it {
            hdl_ast::TopItem::Module(m) => Some((m.name.name.as_str(), m.span.lo as usize)),
            _ => None,
        })
        .collect();
    let rt = hdl_preprocess::resolve_module_timescales(&modules, &pp.timescales);
    drop(modules); // release the borrow of `unit` before moving it
                   // doc-08: a design with NO `timescale at all gets the 1ns/1ns base + one warning.
    if pp.timescales.is_empty() {
        sink.emit(LogEvent::Diagnostic(Diagnostic {
            severity: Severity::Warning,
            code: MsgCode::PpTimescaleDefault,
            message: "no `timescale in the design; assuming the 1ns/1ns base".to_string(),
            location: None,
            context: Vec::new(),
            sim_time: None,
        }));
    }
    Some((unit, rt))
}

/// Render a base-10 second exponent as a `` `timescale ``-style unit string
/// (`-9` → `1ns`, `-10` → `100ps`, `-8` → `10ns`) for the VCD `$timescale` preamble.
/// VCD admits only 1|10|100 × s..fs, i.e. exp ∈ [-15, +2]; the preprocessor only
/// produces that range, but out-of-range exponents saturate to the nearest
/// representable unit rather than misrendering (old fallback: -16 → "100s").
pub fn timescale_unit_string(exp: i8) -> String {
    let exp = (exp as i32).clamp(-15, 2);
    let unit_exp = exp.div_euclid(3) * 3; // floor to a multiple of 3
    let mantissa = 10i32.pow((exp - unit_exp) as u32);
    let unit = match unit_exp {
        0 => "s",
        -3 => "ms",
        -6 => "us",
        -9 => "ns",
        -12 => "ps",
        _ => "fs", // -15 (the clamp admits nothing lower)
    };
    format!("{mantissa}{unit}")
}

/// Core: run the `vita` one-shot pipeline over already-read source `text`
/// (`file` is the display name used in diagnostics). Returns the process exit
/// code. This is the unit-test entry point — it never reads argv or files and
/// never calls `std::process::exit`.
pub fn run_vita_str(file: &str, text: &str, opts: &VitaOpts) -> i32 {
    let inner = StderrSink::new();
    let sink = vita_log::GatedSink::new(&inner, opts.gate.clone());

    // ── preprocess → lex → parse (shared front-end) ─────────────────────────
    let Some((unit, rt)) = frontend_text_to_unit(file, text, &sink) else {
        return EXIT_USER_ERROR;
    };

    // ── elaborate ──────────────────────────────────────────────────────────
    // The elaborator emits its own diagnostics through `sink`; `None` ⇒ a hard
    // elaboration error was reported. `elaborate_with_timescale` also yields the
    // fork-join, net-name, and per-process time-multiplier side tables threaded into
    // `SimOpts`; the timescale env scales `#delay`/`$time`/`$realtime`.
    let (ir, sc) =
        elaborate::elaborate_with_timescale(&unit, &sink, &rt.unit_exp, rt.global_prec_exp);
    let Some(ir) = ir else {
        return EXIT_USER_ERROR;
    };

    // ── simulate ────────────────────────────────────────────────────────────
    let sim_opts = SimOpts {
        fork_modes: sc.fork_modes,
        net_names: sc.net_names,
        proc_multipliers: sc.proc_multipliers,
        severities: sc.severities,
        radixes: sc.radixes,
        proc_scopes: sc.proc_scopes,
        timescale_unit: timescale_unit_string(rt.global_prec_exp),
        ..opts.sim_opts()
    };
    let result = sim_engine::simulate(&ir, &sink, sim_opts);
    let code = sim_exit_code(&result);
    // A `-Werror`-promoted warning is a real Error in the post-gate stream:
    // doc-13 class 1 ("승격-warning 실패") — flip an otherwise-clean exit.
    if code == EXIT_OK && inner.had_error_or_fatal() {
        return EXIT_USER_ERROR;
    }
    code
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
    /// A staged-flow applet (`vcmp`/`velab`/`vrun`).
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
    // P2-4: `--help`/`--version` anywhere in the args short-circuits (before this,
    // `vita --help` tried to READ a file named `--help`). Applet-specific usage.
    let applet_name = match applet {
        Applet::Vita => "vita",
        Applet::Staged(s) => s,
    };
    if args.iter().any(|a| a == "--help" || a == "-h") {
        print_help(applet_name);
        return EXIT_OK;
    }
    if args.iter().any(|a| a == "--version" || a == "-V") {
        println!("{applet_name} {}", env!("CARGO_PKG_VERSION"));
        return EXIT_OK;
    }
    // Filelist expansion (doc-14 §3.1) happens at the ARGV level, before any
    // per-applet flag parsing — every applet accepts `-f`/`-F` uniformly and
    // a `.f` may carry any flag legal on the command line.
    let args = match filelist::expand_argv(&args, &StderrSink::new()) {
        Ok(a) => a,
        Err(code) => return code,
    };
    match applet {
        Applet::Vita => {
            // One-shot flag surface: `-o <vcd>` + `--threads N` (P4-T1), then
            // positional sources. (Before T1 the one-shot accepted NO flags —
            // `-o` was read as a source file.)
            let (pos, out, threads, time_limit, gate) = match parse_io_args(&args) {
                Ok(x) => x,
                Err(c) => return c,
            };
            let opts = VitaOpts {
                vcd_path_override: out,
                threads,
                time_limit,
                gate,
            };
            run_vita(&pos, &opts)
        }
        Applet::Staged("vcmp") => dispatch_vcmp(&args),
        Applet::Staged("velab") => dispatch_velab(&args),
        Applet::Staged("vrun") => dispatch_vrun(&args),
        Applet::Staged(other) => {
            eprintln!(
                "error[{}]: unknown staged applet '{other}'",
                MsgCode::CliBadFlag.code_num()
            );
            EXIT_CLI_ERROR
        }
    }
}

/// P2-4: applet-specific usage text (doc-13 exit table: help/version are clean
/// exits). Kept truthful to the IMPLEMENTED surface (`-o` only).
fn print_help(applet: &str) {
    let body = match applet {
        "vcmp" => {
            "Usage: vcmp [-o <out.vu>] <sources>...\n\n\
             Compile sources (preprocess + lex + parse) into a `.vu` snapshot."
        }
        "velab" => {
            "Usage: velab [-o <out.velab>] <in.vu>\n\n\
             Elaborate a `.vu` snapshot into a `.velab` (golden SimIr + side tables)."
        }
        "vrun" => {
            "Usage: vrun [-o <out.vcd>] <in.velab>\n\n\
             Simulate a `.velab`, writing the VCD and RTL stdout."
        }
        _ => {
            "Usage: vita [-o <out.vcd>] <sources>...\n\
             \x20      vita {vcmp|velab|vrun} [OPTIONS] ...\n\n\
             One-shot RTL simulation: preprocess -> lex -> parse -> elaborate ->\n\
             simulate -> VCD. The staged subcommands split the same pipeline."
        }
    };
    println!(
        "{applet} {} - vitamin RTL simulator",
        env!("CARGO_PKG_VERSION")
    );
    println!("{body}");
    println!(
        "\nOptions:\n  -o, --out <PATH>      output path override\n  \
         -f <FILE>             expand a filelist (paths relative to the CWD)\n  \
         -F <FILE>             expand a filelist (paths relative to the file's dir)\n  \
         --threads, -j <N>     worker threads (output byte-identical for any N)\n  \
         --timeout <TICKS>     stop cleanly after TICKS sim time (CI killswitch)\n  \
         -Wno-<CODE>           suppress a Warning/Info diagnostic (mnemonic, doc-15)\n  \
         -Werror[=<CODE>]      promote warnings (all, or one code) to errors\n  \
         -h, --help            print help\n  -V, --version         print version"
    );
}

/// P2-7: atomic artifact write — stage into `<out>.tmp.<pid>` then rename, so a
/// crash mid-write can never leave a partial `.vu`/`.velab` that the staleness
/// gate would misreport as a format mismatch. Same-directory rename is atomic on
/// POSIX and best-effort-replace on Windows.
fn write_artifact_atomic(out: &str, bytes: &[u8]) -> std::io::Result<()> {
    let tmp = format!("{out}.tmp.{}", std::process::id());
    std::fs::write(&tmp, bytes)?;
    std::fs::rename(&tmp, out).inspect_err(|_| {
        let _ = std::fs::remove_file(&tmp);
    })
}

// ───────────────────────── staged-flow applets ──────────────────────────────

/// Render an artifact-gate rejection through the sink as an Error diagnostic
/// (no source location — artifact-level), then return `EXIT_STALE` (doc-13
/// class 2: "rebuild upstream", distinct from class-1 design errors and
/// class-3 usage errors).
fn emit_artifact_error(sink: &dyn LogSink, e: &vita_artifact::ArtifactError) -> i32 {
    sink.emit(LogEvent::Diagnostic(Diagnostic {
        severity: Severity::Error,
        code: e.code,
        message: e.message.clone(),
        location: None,
        context: Vec::new(),
        sim_time: None,
    }));
    EXIT_STALE
}

/// Read a file as bytes; a read failure is a CLI/usage error (exit 3).
fn read_artifact_bytes(path: &str) -> Result<Vec<u8>, i32> {
    std::fs::read(path).map_err(|e| {
        eprintln!(
            "error[{}]: cannot read '{path}': {e}",
            MsgCode::FlistNotFound.code_num()
        );
        EXIT_CLI_ERROR
    })
}

/// Default output path: replace **only the final** extension component on the
/// input (std `Path::with_extension` semantics — never panics, replaces the last
/// `.ext` only). e.g. `default_out("a.sv","vu") -> "a.vu"`;
/// `default_out("a.b.sv","vu") -> "a.b.vu"`. Callers MUST run `out` through
/// `reject_out_clobbers_input` before writing.
fn default_out(input: &str, ext: &str) -> String {
    let p = std::path::Path::new(input);
    p.with_extension(ext).to_string_lossy().into_owned()
}

/// True iff two path strings denote the same file. Canonicalizes when BOTH paths
/// already exist (handles `./a.sv` vs `a.sv`, symlinks, `..`); otherwise falls
/// back to a raw string compare (the output usually does not exist yet). Never
/// panics.
fn same_path(a: &str, b: &str) -> bool {
    if a == b {
        return true;
    }
    match (std::fs::canonicalize(a), std::fs::canonicalize(b)) {
        (Ok(ca), Ok(cb)) => ca == cb,
        _ => false,
    }
}

/// Reject when the resolved output path would overwrite any positional input.
/// Guards both the `default_out` self-clobber (`vcmp foo.vu` -> default `foo.vu`)
/// and an explicit `-o a.sv` that names an input.
fn reject_out_clobbers_input(inputs: &[String], out: &str) -> Result<(), i32> {
    if inputs.iter().any(|p| same_path(p, out)) {
        eprintln!(
            "error[{}]: output '{out}' would overwrite an input file",
            MsgCode::CliBadFlag.code_num()
        );
        return Err(EXIT_CLI_ERROR);
    }
    Ok(())
}

/// Build the `.vu`/`.velab` header. `global_time_precision` carries the resolved
/// design-wide precision exponent (real now that timescale is wired). The RULE-V
/// upstream-staleness fields (`composite_input_hash`/`consumed`/`worklib_manifest_hash`)
/// remain zero: their live re-hash gate (`E-ART-STALE-UPSTREAM`) is the documented
/// Phase-2 piece (`vrun` holds no upstream to re-hash), and `verify_header` already
/// gates the primary staleness via `schema_hash` + `format_version`.
fn artifact_header(schema_hash: [u8; 32], global_prec_exp: i8) -> vita_artifact::VelabHeader {
    vita_artifact::VelabHeader {
        format_version: vita_artifact::CURRENT_FORMAT_VERSION,
        schema_hash,
        composite_input_hash: [0u8; 32],
        global_time_precision: global_prec_exp as i64,
        consumed: Vec::new(),
        worklib_manifest_hash: [0u8; 32],
        uses_dump: false,
        tool_semver_major: env!("CARGO_PKG_VERSION_MAJOR")
            .parse()
            .expect("CARGO_PKG_VERSION_MAJOR is a valid u32"),
        provenance: vita_artifact::Provenance::capture(),
    }
}

/// `vcmp`: read+preprocess+lex+parse the source(s) into a `SourceUnit`, then write
/// a `.vu` artifact. `out` is the resolved output path.
/// Exit: 0 ok / 1 lex|parse|empty-unit / 3 missing-file|write-error.
pub fn run_vcmp(sources: &[String], out: &str, opts: &VitaOpts) -> i32 {
    if sources.is_empty() {
        eprintln!(
            "error[{}]: no source files given",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    let inner = StderrSink::new();
    let sink = vita_log::GatedSink::new(&inner, opts.gate.clone());

    // read+concat (mirrors run_vita): read error → exit 3.
    let mut text = String::new();
    for path in sources {
        match std::fs::read_to_string(path) {
            Ok(s) => {
                text.push_str(&s);
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
    let file = sources[0].as_str();

    // preprocess → lex → parse through the SAME shared front-end the one-shot uses.
    let Some((unit, rt)) = frontend_text_to_unit(file, &text, &sink) else {
        return EXIT_USER_ERROR;
    };

    // ── write `.vu` body = postcard(SourceUnit) ++ postcard((unit_exp map, global
    //    precision)). The resolved timescale rides after the hashed SourceUnit frame
    //    (the gate covers the type, not these bytes) so `velab` can elaborate the
    //    staged path with the same scaling as the one-shot path. ──
    // `-Werror`: a promoted warning is an Error — the stage fails and writes
    // NO artifact (matching a real compile error).
    if inner.had_error_or_fatal() {
        return EXIT_USER_ERROR;
    }
    let mut body = postcard::to_stdvec(&unit).expect("SourceUnit postcard encode infallible");
    body.extend_from_slice(
        &postcard::to_stdvec(&(rt.unit_exp, rt.global_prec_exp))
            .expect("timescale env postcard encode infallible"),
    );
    let header = artifact_header(
        vita_schema::schema_hash::<hdl_ast::SourceUnit>(),
        rt.global_prec_exp,
    );
    let bytes = vita_artifact::write_vu(&header, &body);
    if let Err(e) = write_artifact_atomic(out, &bytes) {
        eprintln!(
            "error[{}]: cannot write '{out}': {e}",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    EXIT_OK
}

/// `velab`: read a `.vu`, gate the hdl-ast hash, decode the `SourceUnit`,
/// elaborate (with fork modes), then write a `.velab` = header(SimIr hash) +
/// body(`postcard(SimIr) ++ postcard(ForkModeTable)`).
/// Exit: 0 ok / 1 gate-reject|elab-fail|corrupt-body / 3 missing-file|write-error.
pub fn run_velab(vu_path: &str, out: &str, opts: &VitaOpts) -> i32 {
    let inner = StderrSink::new();
    let sink = vita_log::GatedSink::new(&inner, opts.gate.clone());

    let bytes = match read_artifact_bytes(vu_path) {
        Ok(b) => b,
        Err(code) => return code,
    };

    // header-only decode (bad magic/header → E-ART-FORMAT-MISMATCH)
    let (header, body) = match vita_artifact::read_vu(&bytes) {
        Ok(x) => x,
        Err(e) => return emit_artifact_error(&sink, &e),
    };
    // staleness gate: this `.vu` must match the hdl-ast shape THIS velab was built against.
    let tool = vita_artifact::ToolContext::new(vita_schema::schema_hash::<hdl_ast::SourceUnit>());
    if let Err(e) = vita_artifact::verify_header(&header, &tool) {
        return emit_artifact_error(&sink, &e); // E-ART-SCHEMA-MISMATCH etc.
    }
    // decode the SourceUnit frame, then the trailing timescale env (tolerant of an
    // older `.vu` with no env → the 1ns/1ns base).
    let (unit, vu_rest): (hdl_ast::SourceUnit, &[u8]) = match postcard::take_from_bytes(body) {
        Ok(x) => x,
        Err(e) => {
            return emit_artifact_error(
                &sink,
                &vita_artifact::ArtifactError::format(&format!("undecodable .vu body: {e}")),
            )
        }
    };
    let (unit_exp, global_prec_exp): (std::collections::BTreeMap<String, i8>, i8) =
        if vu_rest.is_empty() {
            (std::collections::BTreeMap::new(), -9)
        } else {
            match postcard::from_bytes(vu_rest) {
                Ok(x) => x,
                Err(e) => {
                    return emit_artifact_error(
                        &sink,
                        &vita_artifact::ArtifactError::format(&format!(
                            "undecodable .vu timescale trailer: {e}"
                        )),
                    )
                }
            }
        };

    // ── elaborate (with the staged timescale env) ──
    let (ir, sc) = elaborate::elaborate_with_timescale(&unit, &sink, &unit_exp, global_prec_exp);
    let Some(ir) = ir else {
        return EXIT_USER_ERROR; // elab error already emitted
    };

    // ── write `.velab` body = postcard(SimIr) ++ postcard(ForkModeTable) ++
    //    postcard(NetNameTable) ++ postcard((proc_multipliers, global_prec_exp)) ++
    //    postcard(SeverityTable). All trailers ride OUTSIDE the hashed SimIr frame
    //    (the schema gate covers the type, not these bytes), so the golden hash and
    //    staleness are unaffected; names give `vrun` hierarchical VCD, the multipliers
    //    give it `$time`/`$realtime` scaling, and the severities give it
    //    `$fatal`/`$error`/`$warning`/`$info` routing (P1-1). ──
    // `-Werror`: promoted warnings fail the stage before any artifact lands.
    if inner.had_error_or_fatal() {
        return EXIT_USER_ERROR;
    }
    let mut velab_body = postcard::to_stdvec(&ir).expect("SimIr postcard encode infallible");
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&sc.fork_modes).expect("ForkModeTable postcard encode infallible"),
    );
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&sc.net_names).expect("NetNameTable postcard encode infallible"),
    );
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&(sc.proc_multipliers, global_prec_exp))
            .expect("timescale trailer postcard encode infallible"),
    );
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&sc.severities).expect("severity trailer postcard encode infallible"),
    );
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&sc.radixes).expect("radix trailer postcard encode infallible"),
    );
    velab_body.extend_from_slice(
        &postcard::to_stdvec(&sc.proc_scopes).expect("scope trailer postcard encode infallible"),
    );
    let vheader = artifact_header(vita_schema::schema_hash::<sim_ir::SimIr>(), global_prec_exp);
    let out_bytes = vita_artifact::write_velab(&vheader, &velab_body);
    if let Err(e) = write_artifact_atomic(out, &out_bytes) {
        eprintln!(
            "error[{}]: cannot write '{out}': {e}",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    EXIT_OK
}

/// `vrun`: read a `.velab`, gate the SimIr hash, decode SimIr+ForkModeTable,
/// simulate (threading `fork_modes` into `SimOpts`), writing the VCD. Returns the
/// doc-13 sim exit code.
/// Exit: 0 clean / 1 gate-reject|corrupt-body|runtime-fatal / 3 missing-file.
pub fn run_vrun(velab_path: &str, opts: &VitaOpts) -> i32 {
    let inner = StderrSink::new();
    let sink = vita_log::GatedSink::new(&inner, opts.gate.clone());

    let bytes = match read_artifact_bytes(velab_path) {
        Ok(b) => b,
        Err(code) => return code,
    };

    let (header, body) = match vita_artifact::read_velab(&bytes) {
        Ok(x) => x,
        Err(e) => return emit_artifact_error(&sink, &e), // bad magic → E-ART-FORMAT-MISMATCH
    };
    let tool = vita_artifact::ToolContext::current(); // SimIr-flavored
    if let Err(e) = vita_artifact::verify_header(&header, &tool) {
        return emit_artifact_error(&sink, &e); // schema/version → E-ART-SCHEMA-MISMATCH / E-ART-VERSION-GATE
    }

    // split the golden SimIr frame from the fork trailer.
    let (ir, rest): (sim_ir::SimIr, &[u8]) = match postcard::take_from_bytes(body) {
        Ok(x) => x,
        Err(e) => {
            return emit_artifact_error(
                &sink,
                &vita_artifact::ArtifactError::format(&format!(
                    "undecodable .velab SimIr body: {e}"
                )),
            )
        }
    };
    let (fork_modes, rest2): (sim_engine::ForkModeTable, &[u8]) =
        match postcard::take_from_bytes(rest) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab fork trailer: {e}"
                    )),
                )
            }
        };
    // NetNameTable trailer (hierarchical VCD names). Tolerant of an older `.velab`
    // with no names trailer → empty ⇒ flat `n{i}` fallback (no decode error).
    let (net_names, rest3): (sim_engine::NetNameTable, &[u8]) = if rest2.is_empty() {
        (Vec::new(), rest2)
    } else {
        match postcard::take_from_bytes(rest2) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab name trailer: {e}"
                    )),
                )
            }
        }
    };
    // Timescale trailer (proc multipliers + global precision). Tolerant of an older
    // `.velab` with no trailer → 1ns/1ns base ($time unscaled, preamble 1ns).
    let ((proc_multipliers, global_prec_exp), rest4): ((Vec<u32>, i8), &[u8]) = if rest3.is_empty()
    {
        ((Vec::new(), -9), rest3)
    } else {
        match postcard::take_from_bytes(rest3) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab timescale trailer: {e}"
                    )),
                )
            }
        }
    };
    // Severity trailer ($fatal/$error/$warning/$info, P1-1). Tolerant of an older
    // `.velab` with no trailer → empty ⇒ severity tasks degrade to plain $display.
    let (severities, rest5): (sim_engine::SeverityTable, &[u8]) = if rest4.is_empty() {
        (sim_engine::SeverityTable::new(), rest4)
    } else {
        match postcard::take_from_bytes(rest4) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab severity trailer: {e}"
                    )),
                )
            }
        }
    };
    // Radix trailer (b/o/h print variants, P1-5). Tolerant → empty ⇒ decimal.
    let (radixes, rest6): (sim_engine::RadixTable, &[u8]) = if rest5.is_empty() {
        (sim_engine::RadixTable::new(), rest5)
    } else {
        match postcard::take_from_bytes(rest5) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab radix trailer: {e}"
                    )),
                )
            }
        }
    };
    // Scope trailer (`%m`, P2-11). Tolerant → empty ⇒ flat `top`.
    let proc_scopes: Vec<String> = if rest6.is_empty() {
        Vec::new()
    } else {
        match postcard::from_bytes(rest6) {
            Ok(x) => x,
            Err(e) => {
                return emit_artifact_error(
                    &sink,
                    &vita_artifact::ArtifactError::format(&format!(
                        "undecodable .velab scope trailer: {e}"
                    )),
                )
            }
        }
    };

    // ── simulate ──
    let sim_opts = SimOpts {
        fork_modes,
        net_names,
        proc_multipliers,
        severities,
        radixes,
        proc_scopes,
        timescale_unit: timescale_unit_string(global_prec_exp),
        ..opts.sim_opts()
    };
    let result = sim_engine::simulate(&ir, &sink, sim_opts);
    let code = sim_exit_code(&result);
    if code == EXIT_OK && inner.had_error_or_fatal() {
        return EXIT_USER_ERROR; // `-Werror`-promoted warning (doc-13 class 1)
    }
    code
}

/// Parse a flat arg list into (positional paths, `-o` value). `-o`/`--out`
/// consume the next arg. Unknown flags → `Err(EXIT_CLI_ERROR)`.
/// Parsed common applet flags: (positional args, `-o`, `--threads`, `--timeout`,
/// diagnostic gate policy from `-Wno-*`/`-Werror[=*]`).
type IoArgs = (
    Vec<String>,
    Option<String>,
    Option<u32>,
    Option<u64>,
    vita_log::GatePolicy,
);

fn parse_io_args(args: &[String]) -> Result<IoArgs, i32> {
    let mut pos = Vec::new();
    let mut out = None;
    let mut threads = None;
    let mut timeout = None;
    let mut gate = vita_log::GatePolicy::default();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "-o" | "--out" => {
                let Some(v) = args.get(i + 1) else {
                    eprintln!(
                        "error[{}]: '-o' needs an argument",
                        MsgCode::CliBadFlag.code_num()
                    );
                    return Err(EXIT_CLI_ERROR);
                };
                out = Some(v.clone());
                i += 2;
            }
            // P4-T1: worker-thread budget. Output is byte-identical for every N
            // (contract); the value only moves wall-clock.
            "--threads" | "-j" => {
                let parsed = args.get(i + 1).and_then(|v| v.parse::<u32>().ok());
                let Some(n) = parsed else {
                    eprintln!(
                        "error[{}]: '--threads' needs a positive integer",
                        MsgCode::CliBadFlag.code_num()
                    );
                    return Err(EXIT_CLI_ERROR);
                };
                threads = Some(n.max(1));
                i += 2;
            }
            // P2-9: CI killswitch — cap advanced sim time (ticks). Reaching the
            // cap ends the run cleanly (Quiescent), bounding `always #1;` hangs.
            "--timeout" => {
                let parsed = args.get(i + 1).and_then(|v| v.parse::<u64>().ok());
                let Some(n) = parsed else {
                    eprintln!(
                        "error[{}]: '--timeout' needs a tick count",
                        MsgCode::CliBadFlag.code_num()
                    );
                    return Err(EXIT_CLI_ERROR);
                };
                timeout = Some(n);
                i += 2;
            }
            s if s.starts_with('-') && s.len() > 1 => {
                // Diagnostic gate flags (`-Wno-<CODE>` / `-Werror[=<CODE>]`).
                match gate.parse_arg(s) {
                    Some(Ok(())) => {
                        i += 1;
                        continue;
                    }
                    Some(Err(msg)) => {
                        eprintln!("error[{}]: {msg}", MsgCode::CliBadFlag.code_num());
                        return Err(EXIT_CLI_ERROR);
                    }
                    None => {}
                }
                eprintln!(
                    "error[{}]: unknown flag '{s}'",
                    MsgCode::CliBadFlag.code_num()
                );
                return Err(EXIT_CLI_ERROR);
            }
            _ => {
                pos.push(args[i].clone());
                i += 1;
            }
        }
    }
    Ok((pos, out, threads, timeout, gate))
}

fn dispatch_vcmp(args: &[String]) -> i32 {
    let (pos, out, _threads, _timeout, gate) = match parse_io_args(args) {
        Ok(x) => x,
        Err(c) => return c,
    };
    if pos.is_empty() {
        eprintln!(
            "error[{}]: vcmp: no source files",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    let out = out.unwrap_or_else(|| default_out(&pos[0], "vu"));
    if let Err(c) = reject_out_clobbers_input(&pos, &out) {
        return c;
    }
    run_vcmp(
        &pos,
        &out,
        &VitaOpts {
            gate,
            ..VitaOpts::default()
        },
    )
}

fn dispatch_velab(args: &[String]) -> i32 {
    let (pos, out, _threads, _timeout, gate) = match parse_io_args(args) {
        Ok(x) => x,
        Err(c) => return c,
    };
    if pos.len() != 1 {
        eprintln!(
            "error[{}]: velab: expected exactly one .vu input",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    let out = out.unwrap_or_else(|| default_out(&pos[0], "velab"));
    if let Err(c) = reject_out_clobbers_input(&pos, &out) {
        return c;
    }
    run_velab(
        &pos[0],
        &out,
        &VitaOpts {
            gate,
            ..VitaOpts::default()
        },
    )
}

fn dispatch_vrun(args: &[String]) -> i32 {
    let (pos, out, threads, time_limit, gate) = match parse_io_args(args) {
        Ok(x) => x,
        Err(c) => return c,
    };
    if pos.len() != 1 {
        eprintln!(
            "error[{}]: vrun: expected exactly one .velab input",
            MsgCode::CliBadFlag.code_num()
        );
        return EXIT_CLI_ERROR;
    }
    // vrun accepts `-o` as a VCD path override (parity with one-shot vita -o).
    // Guard: a `-o` that names the input `.velab` would clobber the file being read.
    if let Some(ref o) = out {
        if let Err(c) = reject_out_clobbers_input(&pos, o) {
            return c;
        }
    }
    let opts = VitaOpts {
        vcd_path_override: out,
        threads,
        time_limit,
        gate,
    };
    run_vrun(&pos[0], &opts)
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
    fn vcmp_missing_source_via_run_exits_three() {
        // `vcmp` is now real: `vcmp <missing>.sv` routes to dispatch_vcmp, which
        // fails on the missing-file READ path → exit 3 (CLI/usage error, not a
        // stub). The path is deliberately one that cannot exist.
        let missing = "/nonexistent/path/unknown_applet_top.sv".to_string();
        let argv = vec!["/usr/local/bin/vcmp".to_string(), missing.clone()];
        assert_eq!(run(&argv), EXIT_CLI_ERROR);
        // explicit `vita vcmp …` form routes the same way.
        let argv = vec!["vita".to_string(), "vcmp".to_string(), missing];
        assert_eq!(run(&argv), EXIT_CLI_ERROR);
    }

    #[test]
    fn unknown_flag_to_staged_applet_exits_three() {
        // A genuinely-unknown flag to a staged applet is a CLI/usage error (exit 3)
        // — proves the arg parser rejects, not the stub.
        let argv = vec![
            "/usr/local/bin/vcmp".to_string(),
            "--bogus-flag".to_string(),
            "x.sv".to_string(),
        ];
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
            ..VitaOpts::default()
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
