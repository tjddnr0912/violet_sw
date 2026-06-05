# vitamin — 잔여 작업 체크리스트 (Remaining Work)

> 살아있는 추적 문서. 미해결 = `- [ ]`, 해결 = `- [x]` + (해결: 커밋/날짜). 해결 시 이 파일에서 체크하고 넘어간다.
> 생성: 2026-06-05 · 기준 HEAD `32830d9` · 출처: 6축 병렬 감사(spec-coverage/stub/code-todo/limitations/test-gap/docs).

**범례** — 심각도: BLOCKER(Phase-1 기능 깨짐/측정기준 미달) · MAJOR(부분구현/실제 정확성 결함) · MINOR(작은 갭) · NICE_TO_HAVE(폴리시) · OBSERVATION(문서화된 한계, 결함 아님). `[P1]`=Phase-1 범위 안, `[--]`=Phase-2+/범위 밖.

## 총평

Phase-1 remaining work: 3 true BLOCKERS (timescale precision, `**` in const-eval, VCD naming/hierarchy) + ~7 MAJORs (casex scrutinee, array-index OOR/normalization/sensitivity, wide arithmetic, golden-VCD/corpus test infra, stale CLAUDE.md). The simulator's happy path is real and complete — full preprocess→...→VCD pipeline, one-shot `vita` + staged `vcmp/velab/vrun`, ~352 tests green, all freeze-table system tasks wired. But Phase-1 is NOT done: two of the spec's three measurable success criteria (precision-conversion test, normalized golden-VCD diff) are unmeetable today because (1) timescale unit/precision is consumed-and-discarded with no scaling anywhere, and (2) VCD has no real signal names or scope hierarchy. A handful of silent-wrong-value correctness warts (param `2**N`→0, unsigned wide-arith truncation, array-index clamp/non-normalization, stale always_comb sensitivity) sit squarely in scope. Estimate: the runtime is ~80% there; closing the 3 blockers + array-index correctness + a golden-VCD/corpus harness is the critical path to a defensible Phase-1 MVP.

## Phase-1 블로커/메이저 한눈에

| # | 심각도 | 항목 |
|---|---|---|
| 1 | BLOCKER | Implement timescale unit/precision conversion (currently discarded; no scaling anywhere) |
| 2 | BLOCKER | Add `**` (and AShl/AShr) to the compile-time constant evaluator — `parameter = 2**N` silently folds to 0 |
| 3 | BLOCKER | Emit real VCD signal names + hierarchical module scopes (currently flat `top` scope, synthetic `n0..nN`) |
| 4 | MAJOR | Fix casex/casez to treat SCRUTINEE x/z as don't-care (only label-side wildcard implemented) |
| 5 | MAJOR | Add the array word-index signal to always_comb/@* sensitivity (one-line fix; currently stale output) |
| 6 | MAJOR | Fix out-of-range array WORD index: return X on read / ignore on write (currently clamps to last word) and emit E-RUN-RANGE |
| 7 | MAJOR | Normalize non-zero/descending unpacked-array index (mem[4:7] silently aliased to mem[0:3]) |
| 8 | MAJOR | Stop silent truncation of unsigned >64-bit arithmetic (signed already poisons to X) |
| 9 | MAJOR | Add a byte-exact golden-VCD regression (zero .vcd fixtures today) |
| 10 | MAJOR | Stand up a real-design corpus harness (only micro-snippets + one hand-unrolled testbench today) |
| 11 | MAJOR | Add a test that $dumpvars a memory/array (no VCD-of-array test exists; only word0 dumped) |
| 12 | MAJOR | Add coverage for non-zero/descending UNPACKED array bounds (mem[1:4], mem[3:0]) |
| 13 | MAJOR | Add coverage for descending/non-zero-base PACKED element ranges (reg [0:7] m, reg [8:1] v) |
| 14 | MAJOR | Reconcile doc-08 timescale spec / goals.md:45 criterion with the unimplemented precision model |

---

## Phase-1 correctness — must fix (silent-wrong-value or success-criterion blockers)

- [ ] **[BLOCKER·P1]** Implement timescale unit/precision conversion (currently discarded; no scaling anywhere)
  - **근거:** hdl-preprocess/src/lib.rs:1219 consumes-and-discards `timescale` args; sim-engine/src/lib.rs:84 hardcodes timescale_unit="1ns" (VCD-preamble string only); sched.rs:230 `tick = now + d as u64` (no precision scaling); eval.rs:708-717 $time returns raw now, $realtime = now as f64 ('MVP without per-module unit ratio'); elaborate const_delay_ticks (lib.rs:4028) uses ratio=1. Repro: `#2.5` twice → t=3 then t=6. Spec docs/preview/08:157-161 requires $time=tick/(unit/precision), $realtime=tick*precision/unit; goals 01:45 makes 'precision 환산 정밀도 테스트' a measurable Phase-1 completion criterion.
  - **내용:** No unit/precision ratio exists anywhere, so any non-1:1 timescale (1ns/100ps, 10ns/1ns) gives wrong transition times, $time truncation, and $realtime — directly failing a stated Phase-1 success gate (1ns/1ns designs happen to work).
  - **조치:** Parse `timescale unit/precision in preprocess, thread per-module (unit,precision)+global precision into elaborate→sim-ir, lower #delay to precision ticks with doc-08 rounding (>=0.5→up), implement $time/$realtime scaling, emit W-PP-TIMESCALE-DEFAULT when absent, add a multi-timescale differential test vs iverilog. Or explicitly defer doc-08's model + goals.md:45 criterion to Phase-1.x.
- [x] **[BLOCKER·P1]** Add `**` (and AShl/AShr) to the compile-time constant evaluator — `parameter = 2**N` silently folds to 0 — ✅ 2026-06-05 (`const_eval_in_scope` folds Pow/AShl/AShr; overflow saturates→u32::MAX→loud width-cap; tests `const_eval_power_operator`, `const_eval_arith_shift_operators`). 남은 폴리시: u32→i64 폭 확대(음수/대형 파라미터)는 별도 MINOR.
  - **근거:** elaborate/src/lib.rs:1132 `_ => None, // Pow / AShl / AShr deferred` in const_eval_in_scope (confirmed verbatim); param binding lib.rs:522 `.unwrap_or(0)`; folder is u32-only (lib.rs:1082). Repro: `localparam W = 2**4; reg [W-1:0] r; r=16'hFFFF` → printed w=0, r clamped to 1 bit (value 1), only a Warning ElabWidthTrunc, never an error.
  - **내용:** `**` is IN-MVP and `parameter N = 2**K` / `localparam DEPTH = 2**ADDR_W` is ubiquitous; the param silently becomes 0, range underflows, net clamps to 1 bit, downstream values wrong — surfaced only as a Warning.
  - **조치:** Add Pow/AShl/AShr folding to const_eval_in_scope (and widen beyond u32). At minimum escalate const-eval failure on a width/parameter-defining expression from Warning to Error (ElabUnsupported) so wrong silent values become loud. Add a `parameter=2**N` golden test.
- [ ] **[BLOCKER·P1]** Emit real VCD signal names + hierarchical module scopes (currently flat `top` scope, synthetic `n0..nN`)
  - **근거:** sim-engine/src/builtins.rs:124-127 emits one `push_scope(Module,"top")` and `name=format!("n{i}")` per net (confirmed). Frozen sim_ir::NetVar (sim-ir/src/lib.rs:373-383) and SimIr (448-458) carry NO name field and no net-name side table (none exists in codebase). Repro: a `module sub` inside `m` yields flat `$scope module top` + `n0,n1,...` — no sub/u scope, no x/y/a/b names. Spec 07-vcd-format.md:45-63 requires hierarchical `$scope module dut` with real references; goals 01:43 requires a normalized golden-VCD diff (normalizer absorbs id-CODE diffs but cannot reconstruct missing NAMES/SCOPES).
  - **내용:** Makes a real golden-VCD normalized-diff against iverilog impossible for any non-trivial design — the single biggest Phase-1 differential-success blocker; also blocks $dumpvars scope-limited dumps.
  - **조치:** Add a non-golden net-name + scope-path side table produced by elaborate, kept OUTSIDE the frozen SimIr root (so SchemaHash/format_version unaffected), and thread it into $dumpvars so declare_var/push_scope emit real names and hierarchical scopes.
- [x] **[MAJOR·P1]** Fix casex/casez to treat SCRUTINEE x/z as don't-care (only label-side wildcard implemented) — ✅ 2026-06-05 (`case_label_eq` now lowers casez/casex to `reduction_or(scrut ^ label) !== 1'b1` — handles label AND runtime scrutinee wildcards with existing ops, **no frozen-IR change**; tests `casex_scrutinee_xz_is_wildcard`, `casez_scrutinee_z_is_wildcard`). 잔여 MINOR: casez가 scrut x도 와일드카드로 보는 over-lenient(문서화된 v1 단순화) + 근사 warning 미발행(별도 항목).
  - **근거:** elaborate/src/lib.rs:3640-3684 case_label_eq builds the care-mask only from the LABEL const's unk bits and only when label is Const; scrutinee compared with CaseEq against (label & mask), no scrutinee masking. Repro: `x=4'b1x10; casex(x) 4'b1010:r=1; default:r=0;` → r=0, but IEEE/iverilog casex → r=1. casex/casez are IN-MVP (01:79).
  - **내용:** casex must wildcard scrutinee x/z (casez: z); missing scrutinee-side wildcard produces wrong sim results vs iverilog golden. Also no warning is emitted for the documented approximation (no self.warn in lower_case).
  - **조치:** For casex mask scrutinee x|z, for casez mask scrutinee z (lower to a runtime wildcard-match primitive or dedicated compare op), emit the documented approximation warning with a stable MsgCode, and add tests for x/z in the SCRUTINEE (not just the label).
- [x] **[MAJOR·P1]** Add the array word-index signal to always_comb/@* sensitivity (one-line fix; currently stale output) — ✅ 2026-06-05 (`collect_expr_reads` Signal arm now recurses into `word`; regression test `always_comb_tracks_array_index_signal`)
  - **근거:** elaborate/src/lib.rs:3162 (confirmed) `Expr::Signal { net, .. }` inserts only *net and ignores the `word` field; contrast `Expr::Select` (3165-3173) which DOES recurse into offset. Repro: `always_comb outp = mem[sel];` change only sel 0→2 → out stays 11 (stale; should be 33).
  - **내용:** For `always_comb y = mem[i]`, read-set has mem but not i, so changing i alone never re-fires the block → stale combinational output. Internally inconsistent (bit-select form y=vec[i] correctly tracks i via Select.offset). always_comb is IN-MVP.
  - **조치:** In collect_expr_reads, for `Expr::Signal { net, word }` insert net AND recurse into word (Some(eid)) so the index signal joins the comb read-set.
- [x] **[MAJOR·P1]** Fix out-of-range array WORD index: return X on read / ignore on write (currently clamps to last word) and emit E-RUN-RANGE — ✅ 2026-06-05 정확성 부분 (`net_word_packed` OOR→all-X, `write_chunk` OOR→skip; 이웃 무손상; 다차원 OOR도 같이 X/skip로 통일). 테스트 `array_oob_word_read_is_x_write_ignored`. **남은 부분:** VITA-E4002 진단 발행은 엔진에 런타임 LogSink 미배선(별도 인프라 항목 ‘engine diag hookup’) + 루프 내 OOR 스팸 rate-limit 필요 → 미발행 상태.
  - **근거:** state.rs:156 read `word.unwrap_or(0).min(array_len-1)` clamps; state.rs:278 write `raw_word.min(array_len-1)` clamps. Repro: `reg [7:0] mem[0:3]; i=9; mem[i]` → 44 (last word) not x. MsgCode RunRange/VITA-E4002 EXISTS (diag/src/code.rs:64) but is NEVER emitted (engine has no LogSink/diag hookup at runtime). Spec 15:342-351 defines E-RUN-RANGE: reads x, ignores write, emits diagnostic.
  - **내용:** Bit/part-select OOR already obeys spec (read→X, write→drop bit) but the ARRAY-WORD path clamps to last element on read AND write — silently corrupts a neighboring valid element on OOR write; inconsistent with the bit-select path.
  - **조치:** In state.rs net_word_packed/write_chunk, when word>=array_len return all-X on read and skip the write (no clamp); wire a LogSink handle into the engine and emit VITA-E4002.
- [ ] **[MAJOR·P1]** Normalize non-zero/descending unpacked-array index (mem[4:7] silently aliased to mem[0:3])
  - **근거:** elaborate flatten_word (lib.rs:2489-2519) uses lower_expr(idx) raw with NO subtraction of the dim's index-lsb; array_dim_sizes (1332-1343) keeps only size (abs_diff+1), discards base. No warn emitted. Repro: `reg [7:0] mem[4:7]; mem[4]=AA; mem[5]=BB; $display(mem[4],mem[5])` → both BB (raw 4,5 clamp to word 3, last write wins). IEEE: AA, BB.
  - **내용:** `mem[4:7]` treated as `mem[0:3]`; valid in-source indices become OOR raw words that clamp → wrong reads AND aliased writes, fully silent (no E-RUN-RANGE, no elaborate warning). Worse than a documented limitation.
  - **조치:** Record each unpacked dim's (msb,lsb) in array_dims and have flatten_word emit idx-lsb (or lsb-idx for descending). At minimum warn when any unpacked dim has a non-zero lsb so the corruption isn't silent.
- [ ] **[MAJOR·P1]** Stop silent truncation of unsigned >64-bit arithmetic (signed already poisons to X)
  - **근거:** eval.rs:6-9 documents the 64-bit lane; eval.rs:413 `l.to_u64().unwrap()` drops bits≥64; eval.rs:436 (confirmed) `out.val[0] = (res as u64) & low_mask(w)` stores only word 0; signed >64 → Value::xs (379-381). Repro: `reg[127:0] a,b,c; a=b=1<<64; c=a+b; %h` → all-zeros (expected 0x2_0000…). No >64-bit arith test exists.
  - **내용:** Packed vectors are IN-MVP; unsigned add/sub/mul/div >64 bits silently truncates to low 64 (definite wrong number, no diagnostic) while signed fails safe to X. Bitwise/concat/select/shift remain full-width — only the arithmetic lane is affected.
  - **조치:** Either widen the arithmetic lane to full BitPacked (multi-word add/mul) or, mirroring the signed guard, poison unsigned w>64 results that overflow 64 bits to X. Add a wide-arith golden test diffed vs iverilog.
- [ ] **[MINOR·P1]** Unify X/Z array-index semantics: read→X / write→no-op (currently read=word0, write=last-word)
  - **근거:** Read eval.rs:69 X/Z index → None → net_word_packed unwrap_or(0) → WORD 0. Write sched.rs:708-714 maps X/Z index to u32::MAX sentinel → write_chunk state.rs:278 `u32::MAX.min(array_len-1)` → LAST word. Repro: idx=8'hxx; write mem[idx]=99 lands in m3, read mem[idx] returns m0. IEEE 1364 §11.5.1: read→x, write→no-op.
  - **내용:** Asymmetric and wrong for an unknown array index; a `mem[x]=mem[x]` round-trip is non-identity. Lower severity (X index is rarer) but a genuine correctness wart.
  - **조치:** Make an X/Z word index return all-X on read and a no-op on write (and emit E-RUN-RANGE), unifying with the bit-select X-index policy.

## Phase-1 completeness — partial/missing IN-MVP features

- [ ] **[MINOR·P1]** Implement (or escalate) instance arrays `dff u[3:0](...)` — currently one instance lowered, range dropped
  - **근거:** elaborate/src/lib.rs:751-754 `if !item.unpacked.is_empty() { self.warn("instance-array range ignored (v3: single instance)"); }` — range dropped, one instance elaborated. No instance-array test.
  - **내용:** Module-instance arrays pair with generate/genvar (IN-MVP); array dim silently ignored → missing-replication correctness gap (most idioms expressible via supported generate-for, so bounded).
  - **조치:** Implement N-instance replication with indexed connections, OR escalate to ElabUnsupported so it isn't silently mis-elaborated. Add a test.
- [ ] **[MINOR·P1]** Parse/flatten multi-dimensional PACKED arrays `logic [3:0][7:0] m` (second packed dim fails to parse)
  - **근거:** hdl-ast/src/lib.rs:197 `range: Option<Range>` holds one packed dim; parser calls opt_range() once (hdl-parser/src/lib.rs:1270) then expects an ident. Repro: `logic [3:0][7:0] mat` → PARSE error 'expected identifier, found LBracket' at the 2nd `[`. Synthesizability doc 02-arrays.md:12,25 / 09:27,106 present 2-D packed as synthesizable.
  - **내용:** Single packed dim (vectors) works; multi-dim packed (a contiguous bit-vector = product of dims) does not parse, over-promising the synthesizability doc.
  - **조치:** Accept and flatten multiple packed [hi:lo] ranges into one vector width=product of dims (no IR change, analogous to the unpacked flattening just added), OR explicitly document multi-dim packed as deferred.
- [ ] **[MINOR·P1]** Implement IEEE default field-width right-justification for `%d` (and `%t`)
  - **근거:** builtins.rs:327-335 `%d`/`%D` call fmt_dec (minimal, like %0d) with an inline NOTE that padding is deliberately omitted; `%t` (323-326) also just fmt_dec. Repro: `%d` on 8'd5 → [5] (IEEE [  5]); 8'hxx → [x] (IEEE [  x]); `#12 $display("[%t]",$time)` → [12] (iverilog right-justifies width-20).
  - **내용:** $display is IN-MVP; values exact but missing column-alignment/timeformat scaling diverges from any iverilog golden text/transcript — a stated Phase-1 diff gate.
  - **조치:** Implement default field width for %d (and default-width %h/%o/%b without 0) padding spaces (and X), apply IEEE default %t (right-justify width-20, scale by timescale unit), OR list these in §9 known_quirks so the differential harness carves them out.
- [ ] **[MINOR·P1]** Emit a warning (stable MsgCode) for casez/casex wildcard-label approximation
  - **근거:** elaborate-v2 plan 2026-06-04:23,72-78 requires a warning that wildcard ?/x/z semantics are approximated; actual lowering elaborate/src/lib.rs:3574-3684 has NO self.warn; the only casez test (tests.rs:1176-1207) is wildcard-FREE and asserts warns==0. Comment 3637-3639 admits masking every unknown bit is over-lenient on an explicit-x casez label.
  - **내용:** casez treats an explicit-x label bit as a wildcard and casex scrutinee wildcards are missing — user gets silently-approximate case semantics with no diagnostic.
  - **조치:** Emit a non-fatal warning with a stable MsgCode when a casez label has x bits (or whenever casex is used); add a test asserting it fires for a wildcard-bearing label.
- [ ] **[MINOR·P1]** Track instance-aware $dumpvars depth/scope args (currently accepted but ignored → full dump)
  - **근거:** builtins.rs:76-79 `DumpVars => dumpvars(st)` ignores args; dumpvars (105-157) declares/dumps EVERY net under flat top. Repro: `$dumpvars(0,m)` dumps all 257 nets identically to bare $dumpvars; `$dumpvars(1, tb.dut)` cannot work (no scope table). Spec 07:18 defines depth + scope args.
  - **내용:** Harmless for (0,top) but wrong for selective dumps; blocked entirely until the VCD name/scope side-table exists.
  - **조치:** Honor depth/scope args once the name/scope side table lands (see VCD-naming blocker); until then document that $dumpvars always performs a full dump.
- [ ] **[MINOR·P1]** Resolve E-ART-STALE-UPSTREAM staleness gate (RULE-V header fields stamped zero in CLI)
  - **근거:** cli/src/lib.rs:496 worklib_manifest_hash 'stamped zero (deferred gate)'; :515 'RULE-V fields stay zeroed (deferred)'; :790 'flag surface is DEFERRED'; vita-artifact/src/header.rs:47 'deferred to a later PR'. Goals 01:47 REQUIRES a working hash-based staleness rejection (E-ART-STALE-UPSTREAM) test.
  - **내용:** schema_hash staleness gating works between stages, but the RULE-V upstream-hash gate fields are zeroed placeholders, so the documented Phase-1 staleness-rejection criterion is not yet met by the CLI path.
  - **조치:** Populate the vcmp/velab/vrun trailer + RULE-V hash gate and wire an E-ART-STALE-UPSTREAM staleness test before claiming Phase-1 done.
- [ ] **[MINOR·P1]** Document partial/row-slice of multi-dim UNPACKED array lvalue as a known limit (loud E3009 today)
  - **근거:** elaborate/src/lib.rs:1900-1908: indexing fewer dims → ElabUnsupported 'partial unpacked-array slice (v1: index every dimension)'; bit-then-part on multi-dim lvalue → ElabUnsupported. Test marker end_to_end.rs:1649.
  - **내용:** Whole-element `mem[i][j]` works (HEAD flattening); partial-dim `mem2d[i]` (row) and bit-of-element LHS are rejected loudly (no silent wrong result) — an edge of the freshly added feature.
  - **조치:** Document as a known limitation of the flattening approach; optionally support row-slicing later. Loud error is acceptable for Phase-1.

## Stub crates / pipeline completion

- [ ] **[MINOR·—]** Implement vita-log (log-file tee, transcript file, bucket-C flag surface) — only an inline StderrSink exists
  - **근거:** vita-log/src/lib.rs:1 is a 1-line stub; no crate depends on it (diag/event.rs:59, cli/lib.rs:33,122,334 are doc comments). cli uses inline StderrSink (cli/src/lib.rs:57-118): Diagnostic→stderr, Progress/RtlOutput→stdout, no log-file tee/transcript/--log flag. Spec 04:100, 05:37 assign vita-log transcript/log-tee/severity-routing/exit-code/$error-$fatal.
  - **내용:** Exit codes (0/1/3) and stdout transcript work inline, so core behavior is present; missing is the dedicated file-logging surface. vita-log is publish-true (intended production code, unwritten).
  - **조치:** Implement the LogSink that tees to log + transcript files and the bucket-C CLI flag surface from doc-13; prioritize per how important file-logging is to MVP exit criteria. Inline StderrSink is functionally adequate for now.
- [ ] **[MINOR·—]** Implement vcd-diff (dev/test differential-verification binary)
  - **근거:** vcd-diff/src/lib.rs:1 is a 1-line stub; Cargo.toml publish=false; no [[bin]] target. Spec 09:84-85,155,294 references `cargo run --bin vcd-diff -- iverilog.vcd vita.vcd`.
  - **내용:** Dev/test-only harness comparing vitamin VCD vs reference sims; absence blocks the documented differential-verification workflow but no runtime feature.
  - **조치:** Implement as a bin crate that parses two VCDs and reports value-change divergences to enable the iverilog/verilator differential gates. Lower priority than runtime correctness.
- [ ] **[MINOR·—]** Implement corpus-runner (PASS/FAIL aggregation by exit code)
  - **근거:** corpus-runner/src/lib.rs:1 is a 1-line stub; Cargo.toml publish=false; no bin target. Spec 09:234,242,293 describe exit-code classification (0=PASS/1=FAIL/2=staleness) with --error-exit default-ON.
  - **내용:** Dev/test-only; absence means the documented corpus-aggregation workflow can't run (the 352 cargo tests still pass).
  - **조치:** Implement as a bin crate that walks a testdata/corpus/*.sv dir, runs vita per case, classifies by exit code; wire into cargo test. Seed with shift register, sync FIFO+memory, FSM.
- [ ] **[OBSERVATION·—]** (Optional) extract sim-engine builtins into hdl-builtins crate to match documented architecture
  - **근거:** hdl-builtins/src/lib.rs:1 is a 1-line stub with ZERO real dependents; all Phase-1 system tasks are inlined in sim-engine/src/builtins.rs (549 lines, SysTaskId Display/Write/Strobe/Monitor/Finish/Stop/Dump* at 31-96) — DELIBERATE per sim-engine/Cargo.toml:16-17 'HOOK: extract to hdl-builtins post-v1'. Spec 04:56,94,117 describes hdl-builtins as the real dispatch crate.
  - **내용:** All freeze-table system tasks WORK; purely an architectural-divergence/future-refactor note (hdl-builtins is publish-true, intended to ship).
  - **조치:** Either update 04-architecture.md to state v1 inlines builtins in sim-engine (hdl-builtins reserved for post-v1 extraction), or eventually extract the module. No functional action for Phase-1.
- [ ] **[OBSERVATION·—]** (Optional) move staged-body postcard framing from cli into typed vita-artifact codecs
  - **근거:** vita-artifact is ~210 lines (header + schema gate, format_version=3); cli hand-assembles bodies, e.g. run_velab (cli/src/lib.rs:627-632) concatenates postcard(SimIr)++postcard(ForkModeTable) manually rather than via a typed codec.
  - **내용:** Genuinely real code for the container header + staleness gate (not a stub); 'header-only' just means the cli owns body framing. Staged flow round-trips (staged_flow tests pass).
  - **조치:** Optional: move the postcard framing into typed write_velab_body/read_velab_body helpers in vita-artifact. Not required for Phase-1 correctness.

## Test & verification gaps

- [ ] **[MAJOR·P1]** Add a byte-exact golden-VCD regression (zero .vcd fixtures today)
  - **근거:** `find . -name '*.vcd'` returns ZERO checked-in fixtures. The two VCD tests (end_to_end.rs:231,251) only do `.contains("b0011 !")` substring asserts; no test pins a full VCD byte-image. vcd-diff (the comparison driver) is a stub.
  - **내용:** VCD byte-reproducibility across 3 OSes is a core determinism goal, but substring checks miss ordering/header/timescale drift, id-code reassignment, whitespace regressions — exactly what cross-OS determinism must guarantee. (Blocked by the VCD-naming blocker for non-trivial designs.)
  - **조치:** Run a fixed design, write the .vcd, assert byte-equality against a checked-in crates/testdata/*.vcd (regenerate-on-intent like the schema_hash golden). Land vcd-diff to drive it.
- [ ] **[MAJOR·P1]** Stand up a real-design corpus harness (only micro-snippets + one hand-unrolled testbench today)
  - **근거:** corpus-runner is a 1-line stub; the only whole-design test is cli/tests/real_domain.rs (one harmonic-sum testbench that even hand-unrolls a for-loop per a comment at :27). Spec 05 references a compliance corpus.
  - **내용:** No runner feeds whole RTL (counters, FSMs, ALUs, FIFOs, memories) through preprocess→…→VCD; integration-level interactions (multi-module + memory + VCD + timing together) are untested.
  - **조치:** Implement corpus-runner over a testdata/corpus/*.sv dir with expected stdout and/or golden VCD per design, wired into cargo test; seed with shift register, sync FIFO with memory, FSM.
- [ ] **[MAJOR·P1]** Add a test that $dumpvars a memory/array (no VCD-of-array test exists; only word0 dumped)
  - **근거:** builtins.rs:139 comment 'initial dump of every net (array word 0 in v1)'; word0()/full_snapshot (lib.rs:178-200) extract word 0; declare loop (125-131) declares one $var per net at nv.width with no per-word expansion. No end_to_end.rs test dumps a `reg[..] m[..]` to VCD.
  - **내용:** $dumpvars on a module with a memory is in scope; today only word0 reaches the VCD and even that is unverified for arrays — a future fix/regression goes unnoticed.
  - **조치:** Add a test that $dumpvars a small memory and asserts the $var lines / value changes; decide and document whether per-word expansion is in v1 or explicitly deferred, then assert the chosen behavior.
- [ ] **[MAJOR·P1]** Add coverage for non-zero/descending UNPACKED array bounds (mem[1:4], mem[3:0])
  - **근거:** All unpacked dims in tests are [0:N] zero-based ascending (end_to_end.rs:1581,1594,1610,1661,1708; elaborate tests.rs:639). No test declares `reg [7:0] m[1:4]` or `[3:0]`.
  - **내용:** The non-normalization corruption (see correctness section) has zero coverage, so any change is invisible; the multi-dim flattening stride is only ever exercised on zero-based ascending dims.
  - **조치:** Add elaborate/engine tests for `reg [7:0] m[1:4]` and `[3:0]`, asserting the corrected (normalized) addressing so the behavior is locked.
- [ ] **[MAJOR·P1]** Add coverage for descending/non-zero-base PACKED element ranges (reg [0:7] m, reg [8:1] v)
  - **근거:** Every array element test uses [high:low] with low=0 (e.g. `reg [7:0] g[0:1][0:2]` end_to_end.rs:1581; `reg [63:0] g[0:1][0:1]` :1749). grep for ascending/non-zero-base packed widths returns nothing.
  - **내용:** Packed arrays with arbitrary ranges are IN-MVP; ascending packed `reg [0:7]` and non-zero-base `reg [8:1]` are untested for bit/part-select.
  - **조치:** Add tests for ascending packed element `reg [0:7] m[0:3]` and non-zero-base packed `reg [8:1] v` bit/part-select, asserting documented/correct behavior.
- [ ] **[MINOR·P1]** Add a cross-OS byte-identical output golden (only structural schema-hash + same-process repeat today)
  - **근거:** Determinism gates: sim-ir/tests/schema_hash.rs (structural IR hash, not output) and end_to_end.rs:309/1053 (run the SAME SimIr twice in-process, compare stdout). Nothing diffs output bytes vs a checked-in golden that would catch HashMap-iteration / float-format / path-separator drift.
  - **내용:** CLAUDE.md sells '3-OS byte-identical' but the suite only proves same-input→same-output in one process and IR-shape stability.
  - **조치:** Add checked-in golden stdout fixtures for a few designs and assert byte-equality, complementing the schema_hash gate. (Overlaps the golden-VCD gap.)
- [ ] **[MINOR·—]** (Optional) add multi-packed-dim element and hierarchical-array-access tests
  - **근거:** No test for a two-packed-dim element on an unpacked array (`reg [3:0][7:0] m[0:1]`); the only multi-packed usage (end_to_end.rs:1746) uses a single [63:0] dim. Hierarchy tests (elaborate tests.rs:1339+) contain no mem/reg[..][..] decls — no submodule-memory-through-hierarchy test.
  - **내용:** Multi-packed-dim words and memory-inside-instantiated-child interactions (index-flatten + instance-name mangling) are untested either way.
  - **조치:** Add a two-packed-dim element test (or a loud-rejection test if deferred), and a hierarchy test where a parent drives/observes a child's `reg [7:0] m[0:3]`.
- [ ] **[OBSERVATION·—]** (Optional) pin $readmemh/$readmemb graceful-ignore diagnostic
  - **근거:** $readmemh/$readmemb appear only in docs (05:54, system-tasks/03-memory-load.md:12 'Phase 2', 17:338) and elaborate's unknown-task swallow path (lib.rs:3828); no SysTaskId variant. Correctly Phase-2 deferred.
  - **내용:** Absence of functional tests is correct; only the unknown-task W-level graceful-ignore contract is unpinned.
  - **조치:** Optionally add one test asserting $readmemh elaborates to the documented unknown-task diagnostic. No functional coverage owed in Phase-1.

## Documented limitations (accept or revisit)

- [ ] **[OBSERVATION·P1]** casez over-masks explicit-x label bits (casez should wildcard only z/?)
  - **근거:** elaborate/src/lib.rs:3637-3639 builds the care-mask from ~unk, so a casez label with an explicit x bit is treated as wildcard; comment admits 'documented v1 simplification'. Only diverges on the rare explicit-x-in-casez-label pattern.
  - **내용:** IEEE distinguishes casez (z,?) from casex (x,z); vita collapses both to 'mask all unknown bits'. (Distinct from but related to the scrutinee-wildcard MAJOR above.)
  - **조치:** Track z-vs-x origin separately on case labels so casez masks only z/?; keep casex masking both. Low priority.
- [ ] **[OBSERVATION·—]** Accept `assign #d` as transport-delay only (no inertial pulse rejection)
  - **근거:** sched.rs:216-235 schedules a TRANSPORT-delay write on each RHS change; comment 'inertial pulse-filtering is a v1 simplification'. Intra-assignment delays (x=#d y) dropped with a warning (elaborate lib.rs:3330-3346, 2116-2117).
  - **내용:** Narrow glitches propagate that iverilog would filter; value-on-delayed-edge is correct. Basic intra-assignment delay drop is in-scope-deferred per freeze table (01:80 'intra-assignment delay 고급' = Phase-2).
  - **조치:** Document the transport-delay choice in known_quirks for the iverilog differential gate; consider inertial filtering post-Phase-1.
- [ ] **[OBSERVATION·P1]** Accept $stop = batch-terminate (distinct exit class from $finish, not interactive breakpoint)
  - **근거:** exec.rs:71-72 maps Ctl::Stop→Step::Stop; sched.rs:356-362 returns FinishReason::Stop. Repro: code after $stop does not execute. IEEE $stop suspends to a resumable prompt.
  - **내용:** Defensible simplification for a batch simulator with no interactive console (reports a distinct FinishReason::Stop).
  - **조치:** Document $stop = batch-terminate in the system-tasks reference; no code change for Phase-1.
- [ ] **[OBSERVATION·P1]** Accept $dump* snapshot of array word 0 only
  - **근거:** builtins.rs:139-149 comment 'array word 0 in v1'; word0()/full_snapshot (lib.rs:178-200) always extract word 0.
  - **내용:** Vectors/scalars dump correctly; only multi-word memory/array nets are partial (word 0). Consistent with standard-VCD practice variance.
  - **조치:** Leave as documented limitation; revisit if full array waveforms are required for the golden corpus.

## Docs & housekeeping

- [ ] **[MAJOR·—]** Rewrite CLAUDE.md crate table — it marks the entire working pipeline as 'stub'
  - **근거:** CLAUDE.md:36 labels cli 'stub'; :37 labels '나머지 9개' (hdl-preprocess/lexer/parser/ast·elaborate·sim-engine·hdl-builtins·vcd-writer·vita-log) all 'stub'; :5 'first code in progress'. Reality: cli has real run_vita(335)/run_vcmp(535)/run_velab(590)/run_vrun(647); 352 #[test] across crates; full pipeline works.
  - **내용:** The single most misleading doc in the repo — a reader would conclude the simulator doesn't work, when one-shot vita and staged vcmp/velab/vrun are both functional.
  - **조치:** Mark cli/hdl-preprocess/hdl-lexer/hdl-parser/hdl-ast/elaborate/sim-engine/vcd-writer as 실코드; update line 5 to reflect the completed pipeline (one-shot + staged).
- [ ] **[MAJOR·—]** Document the shipped multi-dim unpacked-array flattening (undocumented in docs/preview)
  - **근거:** HEAD 32830d9 'multi-dimensional unpacked-array support (row-major flattening)'. grep for row-major/suffix-product/array_dims/다차원 unpacked across docs/preview/{17,06}, 02-arrays.md, CLAUDE.md → ZERO hits. Freeze table 01:77 lists only '벡터·packed array'.
  - **내용:** The rationale (elaborate-local array_dims side-table, suffix-product stride, deliberate no-IR-refreeze, loud E3009 reject of partial-slice/over-index) lives only in memory + code comments.
  - **조치:** Add an impl-note (02-arrays.md and/or CHANGELOG): multi-dim unpacked supported via elaborate-time row-major flattening (no IR change); partial-slice/over-index are E3009-rejected; the four 1-D-inherited OBSERVATIONS apply.
- [ ] **[MAJOR·P1]** Reconcile doc-08 timescale spec / goals.md:45 criterion with the unimplemented precision model
  - **근거:** Same code as the timescale BLOCKER (hdl-preprocess:1219 discard, sim-engine:84 hardcoded '1ns', sched.rs:230 raw `d as u64`). doc-08:79-114,157-161 prescribes a detailed integer-tick precision model; goals 01:45 makes it a measurable success criterion the code can't meet.
  - **내용:** Largest authored-spec-vs-code gap; either implement (see BLOCKER) or stop the spec claiming a non-existent capability.
  - **조치:** Implement per the timescale BLOCKER, OR explicitly mark doc-08's precision model + goals.md:45 criterion as Phase-1.x/deferred.
- [ ] **[MINOR·P1]** Fix stale doc comments claiming deferral for already-implemented IN-MVP features
  - **근거:** sim-engine/src/lib.rs:15-16 lists '$monitor/$strobe (stubbed as one-shot $display)' + 'fork/join DEFERRED' — contradicted by builtins.rs:43-67 (postponed FmtCapture FIFO, MonitorState change-detect), sched.rs:474 flush_postponed, and real fork (lib.rs:41,139). elaborate/src/lib.rs:3210 says 'read-set inference deferred' but it's implemented at 3091-3158 (test passes). cli/src/lib.rs:410 + main.rs:2-3 call vcmp/velab/vrun 'stubs' though fully wired.
  - **내용:** Misleads an auditor into thinking mandatory features are stubbed; could mask a real regression if someone trusts the comment. No functional defect.
  - **조치:** Update the doc comments at sim-engine/src/lib.rs:15-19, elaborate/src/lib.rs:3210, cli/src/lib.rs:410, cli/src/main.rs:2-3 to reflect implemented behavior; keep only genuinely deferred items (force/release, real-number, recursive func/task, multi-instance hierarchy, full 17-region).
- [ ] **[MINOR·—]** Update CLAUDE.md format_version (says 2; code is 3) and drop the '본문 M3+' caveat
  - **근거:** CLAUDE.md:35 says format_version=2 and '실코드 (헤더; 본문 M3+)'. vita-artifact/src/header.rs:15 `CURRENT_FORMAT_VERSION: u32 = 3` (bumped at 1b4a652 for real/realtime IR); lib.rs:8 exports read/write_velab/vu; header.rs:61-68 writes header++body. Staged bodies are real (commit 3f63177).
  - **내용:** The version bump re-pinned the golden SimIr hash and invalidated prior .velab; the 'body deferred' caveat is obsolete (staged bodies round-trip byte-identical to one-shot).
  - **조치:** Update CLAUDE.md:35 to format_version=3, note real/realtime support, and drop the '본문 M3+' caveat.
- [ ] **[MINOR·—]** Amend doc-17: multi-dim unpacked handled by flattening, not the Phase-2 dims:Vec<u32> re-freeze
  - **근거:** doc-17:228 '`array_len:u32`(1-D); 다차원 → Phase-2 `dims:Vec<u32>` re-freeze'; :343 maps multi-dim → dims:Vec<u32>. HEAD 32830d9 shipped multi-dim unpacked WITHOUT an IR re-freeze (golden hash unflipped).
  - **내용:** Spec frames multi-dim as a future IR-widening event; implementation chose elaborate-time flattening. dynamic/associative/queue legitimately still need the re-freeze — only the static-unpacked claim is stale.
  - **조치:** Amend doc-17 §(D-V4)/type-map: static multi-dim UNPACKED is elaborate-flattened (no re-freeze); dims:Vec<u32> re-freeze reserved for dynamic/associative/queue only.
- [ ] **[MINOR·—]** Surface the four 1-D-inherited array OBSERVATIONS in docs/preview (currently only in memory/comments)
  - **근거:** grep for index-lsb/non-normaliz/OOR/word0/asymmetr across docs/preview/ (excl. error-code ref) → nothing. The four carve-outs (raw index non-normalization; X/Z read=word0 vs write=last-word; OOR clamp-to-last-word; always_comb/@* excludes array-index) live only in memory + code comments.
  - **내용:** Real intentional carve-outs that should be visible in the spec. Note: per the correctness section, three of these are being escalated from 'accept' to 'fix'.
  - **조치:** Add a known-limitations subsection to 02-arrays.md or 06-simulation-engine.md (for whichever behaviors remain after the correctness fixes land).
- [ ] **[MINOR·—]** Harden the SchemaHash derive integer/repr/path normalization before extending frozen types (F2/F3/F4)
  - **근거:** vita-artifact-derive/src/lib.rs:156,168 disc/array-len use split_whitespace().collect() (token-shape, not value — doesn't strip underscores or normalize leading zeros vs spec 16:182); :43 emits a hardcoded `repr=@` placeholder, render_serde_attrs (297) never reads #[repr(...)] (spec 16:245 defines a real repr_tag); :266-273 render_full_path drops mid-segment PathArguments (`a::B<X>::C`→`a::B::C`).
  - **내용:** No live collision today (frozen types use plain small decimals, no explicit #[repr], no mid-path generics), but these are latent determinism holes — e.g. #[repr(u8)]→#[repr(u16)] wouldn't flip the hash.
  - **조치:** Before extending schema types with computed/underscored/non-decimal disc or array-len, replace split_whitespace with real integer-eval+decimal-render; implement the repr_tag slot (re-pin goldens, format_version bump); guard/render mid-segment PathArguments in render_full_path.
- [ ] **[NICE_TO_HAVE·—]** Delete the redundant `msrv` CI job (duplicates build-native's ubuntu 1.82 leg)
  - **근거:** .github/workflows/ci.yml:55-65 job `msrv` (ubuntu-latest, @1.82.0, build+test --workspace --locked) adds no coverage beyond build-native (16-38, same @1.82.0 across ubuntu+macos with fmt/clippy/build/test).
  - **내용:** Toolchain is hard-pinned to 1.82.0 everywhere, so a separate MSRV job is pure duplication.
  - **조치:** Delete the msrv job, OR switch build-native to stable and keep msrv as the explicit 1.82 floor — pick one, don't run identical jobs.
- [ ] **[OBSERVATION·—]** (Nit) move crates/testdata/ out from under crates/ so member count matches dir count
  - **근거:** `ls -d crates/*/` → 18 dirs including crates/testdata/ (no Cargo.toml; only sim_ir_canonical.txt, sim_ir_registry.ron); Cargo.toml members lists 17. CLAUDE.md:10 '17-crate (15 prod + 2 dev)' is accurate for members.
  - **내용:** Organizational nit; the stray fixture dir invites the '18 crates' miscount.
  - **조치:** Move crates/testdata/ to a top-level testdata/ (or tests/fixtures/), or add a README noting it's a fixture dir, not a crate.

## Phase-2+ deferred (out of scope, listed for visibility)

- [ ] **[MINOR·—]** inout bidirectional ports (currently one-directional parent→child + warn)
  - **근거:** elaborate/src/lib.rs:798,844-849 treats Inout like Input + warns 'approximated as one-directional'; no tri-state resolution.
  - **내용:** Child can't drive back through the port; a testbench using inout gets silently one-way behavior with only a warning. Not explicitly enumerated in the freeze-table port row.
  - **조치:** Document inout as an explicit Phase-2 deferral in the freeze table (keep the warning loud), or implement bidirectional net resolution later.
- [ ] **[MINOR·—]** Intra-assignment timing control `a = #5 b` / `a <= @(posedge clk) b` (parsed-and-discarded with error)
  - **근거:** hdl-parser/src/lib.rs:2163-2176 skip_intra_assign_delay emits a ParseError and consumes the #d/@(…); parser test 3097 asserts delay.is_none(); build() treats any ParseError as fatal (end_to_end.rs:29). Freeze table 01:80 puts 'intra-assignment delay 고급' in Phase-2.
  - **내용:** Borderline: delay parsed then discarded; a caller tolerating parse errors would get a silently zero-delay assignment.
  - **조치:** Confirm freeze-table intent; if out, the parse-error-and-discard is acceptable but make the discard a hard documented boundary; if in, implement delayed-sample/delayed-commit lowering.
- [ ] **[MINOR·—]** `disable` statement (no-op: Scope/0 lowered, engine executes nothing)
  - **근거:** exec.rs:77 `Stmt::Disable {..} => { /* v1: no-op */ }`; elaborate lib.rs:3462-3473 emits Disable{Scope,0} + warning 'disable target scope-id unresolved (v2)'.
  - **내용:** disable <named_block>/disable fork is parsed but never affects control flow (associated with fork/join, Phase-2-ish). A testbench relying on it to abort a loop runs incorrectly with only a warning.
  - **조치:** Keep as documented Phase-2 deferral; implement scope-id resolution + control-flow abort when fork/join's disable lands.
- [ ] **[NICE_TO_HAVE·—]** `defparam` (hard ElabUnsupported)
  - **근거:** elaborate/src/lib.rs:654-655 `Defparam(_) => self.error(ElabUnsupported, 'construct deferred (defparam)')`. Named/positional instance overrides ARE supported (717,990).
  - **내용:** Legacy/deprecated override mechanism, not in the freeze table; clean loud error is the right behavior.
  - **조치:** No action for Phase-1; keep the loud error and document as permanent/Phase-2.
- [ ] **[OBSERVATION·—]** Recursive/automatic functions & tasks (ElabUnsupported; non-recursive inlined)
  - **근거:** elaborate/src/lib.rs:1999-2016, 2166-2174 reject automatic/recursive func/task (placeholder_expr); tests ft_e6/ft_e7 (tests.rs:2664-2719) assert ElabUnsupported.
  - **내용:** Non-recursive static functions/tasks work via inlining; recursion needs a runtime frame-call (deferred). Rejected loudly, never mis-evaluated.
  - **조치:** Keep the loud error; implement frame-call when a use case demands recursion.
- [ ] **[OBSERVATION·—]** SV implicit port connections `.*` / `.name` (parser stub → ignored with error)
  - **근거:** hdl-parser/src/lib.rs:1139,1151-1155 '.* implicit port connection not yet supported; ignored'; lib.rs:1020 DEFERRED note. Explicit named/positional connections work.
  - **내용:** SV conveniences not in the freeze table; parsed-and-ignored with an error diagnostic. Phase-2 polish.
  - **조치:** No Phase-1 action; implement with interface/SV expansion later.
- [ ] **[OBSERVATION·—]** Introspection $bits (ElabUnsupported)
  - **근거:** `$bits(r)` → elaborate 'unsupported system function'. SysFuncId (sim-ir/src/lib.rs:149-160) lacks $bits; freeze table puts introspection in Phase-2.
  - **내용:** Correctly deferred; noted only because $bits is commonly used and a reader might expect it in MVP.
  - **조치:** No action; ensure docs make clear $bits/introspection is Phase-2.
- [ ] **[OBSERVATION·—]** $dumpflush/$dumplimit (vcd-writer API exists but no SysTaskId — correctly outside Phase-1)
  - **근거:** vcd-writer/src/lib.rs:3-7,221,227 provide set_limit/is_limit_reached, but sim_ir::SysTaskId (sim-ir/src/lib.rs:211-223) has only DumpFile/Vars/On/Off/All; no DumpFlush/DumpLimit in builtins.rs. Freeze table lists exactly the 5 dump tasks.
  - **내용:** Missing IR wiring is correct; the vcd-writer API surface is simply ahead of the IR. SysTaskId is in the FROZEN sim-ir root.
  - **조치:** No action for Phase-1. If added later, remember the SysTaskId change flips the golden root hash (format_version bump + .velab regeneration).
- [ ] **[OBSERVATION·—]** Reconcile reserved W3048 (whole-array-into-sens) intent vs shipped array-index-excluded behavior when auto-sens lands
  - **근거:** docs/preview/15:697 reserves W3048 W-ELAB-SENS-ENTIRE-ARRAY (MVP-SIM, must-implement) 'pulls whole array into sens'; not in the diag enum (Appendix-A reserved, correctly bijection-excluded). Current runtime does the OPPOSITE (array-index excluded — see the always_comb MAJOR).
  - **내용:** Latent design contradiction, not a live defect; needs a decision when auto-sensitivity for array word-selects is implemented.
  - **조치:** When implementing the array-index sensitivity fix, reconcile with W3048's stated whole-array-into-sens intent and document whichever is chosen.

---

## 진행 로그

해결 시 한 줄씩 추가 (날짜 · 커밋 · 항목).

- 2026-06-05 · always_comb/@* 배열 word-인덱스 민감도 누락 수정 (MAJOR). `collect_expr_reads`가 `Signal.word`를 재귀 → `always_comb y=mem[sel]`이 sel 변경 시 재발화. 회귀테스트 추가, 워크스페이스 353 green, 골든 unflipped.
- 2026-06-05 · const-eval `**`/`<<<`/`>>>` 폴딩 추가 (BLOCKER). `parameter W=2**N`이 silent 0→정상 폴드, overflow는 u32::MAX 포화로 width-cap loud. 테스트 2종, 워크스페이스 355 green, 골든 unflipped.
- 2026-06-05 · casex/casez SCRUTINEE x/z 와일드카드 수정 (MAJOR). `case_label_eq`를 `reduction_or(scrut ^ label) !== 1`로 — 라벨+런타임 scrutinee 와일드카드를 기존 op만으로 처리(frozen IR 무변경). v2_7 단위테스트 새 lowering 반영. 신규 2테스트, 워크스페이스 357 green, 골든 unflipped.
- 2026-06-05 · OOR array word 정확성 수정 (MAJOR). `net_word_packed` OOR→all-X 읽기, `write_chunk` OOR→쓰기 무시(이웃 무손상), 클램프 제거. 다차원 OOR도 X/skip로 통일. 테스트 1종, 워크스페이스 358 green, 골든 unflipped. (E4002 진단 발행은 엔진 diag-sink 인프라 필요 → 보류)

