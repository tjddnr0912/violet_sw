use crate::Severity;

/// Generates the exhaustive `MsgCode` enum + metadata accessors from a table.
macro_rules! msgcodes {
    ($( $variant:ident => ($mnemonic:literal, $num:literal, $sev:ident, $title:literal) ),* $(,)?) => {
        /// Stable, exhaustive diagnostic code. mnemonic is the primary stable key.
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
        pub enum MsgCode { $( $variant ),* }

        impl MsgCode {
            /// All body codes, declaration order.
            pub const ALL: &'static [MsgCode] = &[ $( MsgCode::$variant ),* ];

            /// Primary stable mnemonic, e.g. `E-ELAB-MULTIDRIVER`.
            pub const fn mnemonic(self) -> &'static str {
                match self { $( MsgCode::$variant => $mnemonic ),* }
            }
            /// grep-friendly number, e.g. `VITA-E3001`.
            pub const fn code_num(self) -> &'static str {
                match self { $( MsgCode::$variant => $num ),* }
            }
            /// Default severity for this code.
            pub const fn default_severity(self) -> Severity {
                match self { $( MsgCode::$variant => Severity::$sev ),* }
            }
            /// Short title (the `vita explain` headline).
            pub const fn title(self) -> &'static str {
                match self { $( MsgCode::$variant => $title ),* }
            }
        }
    };
}

msgcodes! {
    // 0xxx GENERAL / SYSTEM
    CliBadFlag             => ("E-CLI-BAD-FLAG",            "VITA-E0001", Error,   "unknown or invalid command-line flag"),
    LimitErrors            => ("F-LIMIT-ERRORS",            "VITA-F0002", Fatal,   "error limit reached; aborting stage"),
    // 1xxx PREPROCESS
    PpIncludeNotFound      => ("E-PP-INCLUDE-NOT-FOUND",    "VITA-E1001", Error,   "`include file not found on search path"),
    PpMacroArity           => ("E-PP-MACRO-ARITY",         "VITA-E1002", Error,   "function-like macro called with wrong arity"),
    LintUnclosed           => ("W-LINT-UNCLOSED",          "VITA-W1003", Warning, "inline lint_off never closed before EOF"),
    PpRecursiveMacro       => ("E-PP-RECURSIVE-MACRO",     "VITA-E1004", Error,   "recursive text-macro expansion"),
    PpRecursiveInclude     => ("E-PP-RECURSIVE-INCLUDE",   "VITA-E1005", Error,   "cyclic `include (file includes itself)"),
    PpBadDirective         => ("E-PP-BAD-DIRECTIVE",       "VITA-E1013", Error,   "unknown compiler directive"),
    PpMacroRedefined       => ("W-PP-MACRO-REDEFINED",     "VITA-W1007", Warning, "`define redefines a macro with different text"),
    PpUndefUndefined       => ("W-PP-UNDEF-UNDEFINED",     "VITA-W1008", Warning, "`undef of a macro that was never defined"),
    // 2xxx PARSE
    DupUnit                => ("E-DUP-UNIT",                "VITA-E2001", Error,   "design unit redefined"),
    ParseUnexpectedToken   => ("E-PARSE-UNEXPECTED-TOKEN",  "VITA-E2002", Error,   "unexpected token"),
    ParseImplicitNet       => ("W-PARSE-IMPLICIT-NET",      "VITA-W2003", Warning, "implicit net inferred (default_nettype wire)"),
    // 3xxx ELABORATE
    ElabMultidriver        => ("E-ELAB-MULTIDRIVER",        "VITA-E3001", Error,   "net driven by multiple structural drivers"),
    ElabPortMismatch       => ("E-ELAB-PORT-MISMATCH",      "VITA-E3002", Error,   "instance port binding incompatible with module"),
    ElabUnresolvedInstance => ("E-ELAB-UNRESOLVED-INSTANCE","VITA-E3003", Error,   "cannot resolve instantiated module"),
    ElabUserError          => ("E-ELAB-USER-ERROR",         "VITA-E3004", Error,   "elaboration-time $error"),
    ElabUserFatal          => ("F-ELAB-USER-FATAL",         "VITA-F3005", Fatal,   "elaboration-time $fatal"),
    ElabUserInfo           => ("I-ELAB-USER-INFO",          "VITA-I3006", Info,    "elaboration-time $info"),
    ElabUserWarning        => ("W-ELAB-USER-WARNING",       "VITA-W3007", Warning, "elaboration-time $warning"),
    ElabWidthTrunc         => ("W-ELAB-WIDTH-TRUNC",        "VITA-W3008", Warning, "width mismatch truncated/extended"),
    ElabUnsupported        => ("E-ELAB-UNSUPPORTED",        "VITA-E3009", Error,   "construct not yet supported by elaborate"),
    ElabUnresolvedName     => ("E-ELAB-UNRESOLVED-NAME",    "VITA-E3010", Error,   "reference to undeclared net/variable"),
    // 4xxx RUNTIME
    RunAssertFail          => ("E-RUN-ASSERT-FAIL",         "VITA-E4001", Error,   "assertion failed (no action block)"),
    RunRange               => ("E-RUN-RANGE",               "VITA-E4002", Error,   "runtime index/select out of range"),
    RunUserError           => ("E-RUN-USER-ERROR",          "VITA-E4003", Error,   "runtime $error"),
    RunFatal               => ("F-RUN-FATAL",               "VITA-F4004", Fatal,   "runtime $fatal (implicit $finish)"),
    RunUserInfo            => ("I-RUN-USER-INFO",           "VITA-I4005", Info,    "runtime $info"),
    RunNoLocations         => ("W-RUN-NO-LOCATIONS",        "VITA-W4006", Warning, "snapshot has no location side-table"),
    RunUserWarning         => ("W-RUN-USER-WARNING",        "VITA-W4007", Warning, "runtime $warning"),
    // 8xxx FILELIST
    FlistCycle             => ("E-FLIST-CYCLE",             "VITA-E8001", Error,   "filelist cycle"),
    FlistDepth             => ("E-FLIST-DEPTH",             "VITA-E8002", Error,   "filelist nesting exceeded depth cap"),
    FlistDupCtxConflict    => ("E-FLIST-DUP-CTX-CONFLICT",  "VITA-E8003", Error,   "same source twice under differing sticky context"),
    FlistGlob              => ("E-FLIST-GLOB",              "VITA-E8004", Error,   "wildcard not allowed in filelist"),
    FlistNotFound          => ("E-FLIST-NOT-FOUND",         "VITA-E8005", Error,   "filelist or referenced path not found"),
    FlistUndefEnv          => ("E-FLIST-UNDEF-ENV",         "VITA-E8006", Error,   "undefined environment variable in filelist"),
    FlistWrongStage        => ("E-FLIST-WRONG-STAGE",       "VITA-E8007", Error,   "filelist directive wrong for invoking stage"),
    FlistMixedBase         => ("W-FLIST-MIXED-BASE",        "VITA-W8008", Warning, "-f inside -F frame re-anchors to CWD"),
    FlistOverride          => ("W-FLIST-OVERRIDE",          "VITA-W8009", Warning, "single-value knob overridden (last-wins)"),
    // 9xxx ARTIFACT
    ArtFormatMismatch      => ("E-ART-FORMAT-MISMATCH",     "VITA-E9001", Error,   "artifact magic/format_version mismatch"),
    ArtSchemaMismatch      => ("E-ART-SCHEMA-MISMATCH",     "VITA-E9002", Error,   "artifact schema_hash mismatch"),
    ArtStaleUpstream       => ("E-ART-STALE-UPSTREAM",      "VITA-E9003", Error,   "stale upstream snapshot (RULE V)"),
    ArtVersionGate         => ("E-ART-VERSION-GATE",        "VITA-E9004", Error,   "producer tool semver-major incompatible"),
}
