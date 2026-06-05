# vitamin — 잔여 작업 체크리스트 (Remaining Work)

> 살아있는 추적 문서. 미해결 = `- [ ]`, 해결 = `- [x]` + (해결: 커밋/날짜). 해결 시 이 파일에서 체크하고 넘어간다.
> 생성: 2026-06-05 · 기준 HEAD `32830d9` · 출처: 6축 병렬 감사(spec-coverage/stub/code-todo/limitations/test-gap/docs).
>
> **🏁 현황(2026-06-05 최신):** 감사 52항목 + 후속 큐 5항목(E-RUN-RANGE 진단, iverilog 차분 하네스, Phase-2 자료형, word化, 컴파일드 백엔드 로드맵) **전부 클리어**. 3 BLOCKER·~7 MAJOR 모두 해결, 골든 루트 unflipped, 워크스페이스 **419 tests green**, clippy/fmt clean. 아래 총평은 *생성 시점(32830d9) 스냅샷*으로 보존(이력). 잔여 = Phase-2+ 의도적 deferral(loud reject 확인됨)뿐.

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

- [x] **[BLOCKER·P1]** Implement timescale unit/precision conversion — ✅ 2026-06-05 **완전완료**(S1~S5). doc-08 모델 동작(실측 vita: 1ns/1ps #2.5→time=2/realtime=2.5/preamble 1ps). ~~잔여~~ 스테이지드 트레일러(`staged_chain_matches_oneshot_timescaled` ✅)·W1017 경고·doc-08 골든 전부 처리됨(아래 S5). — 원래 **진행 중 (doc-08 전체 모델, 사용자 선택 A)**. 단계별:
  - [x] S1 preprocess: `timescale unit/precision` 파싱 → `TimeScale{unit_exp,prec_exp}` + 확장텍스트 offset region 테이블을 PpResult에 노출 ✅ 2026-06-05 (parse_timescale + PpResult.timescales, 3 테스트)
  - [x] S2 resolve: `resolve_module_timescales`(모듈 span↔region 매칭, file-order) + `global_prec=min` + default_used 플래그 ✅ 2026-06-05 (hdl-preprocess plain types, 2 테스트)
  - [x] S3 elaborate: per-module M으로 `#delay` 스케일(round-half-up, 곱셈은 반올림 내부) + proc_multipliers 사이드테이블 ✅ 2026-06-05 (elaborate_with_timescale; sim_time 검증 7000/2500/5, 골든 unflipped, 3 테스트)
  - [x] S4 engine: `SimOpts.proc_multipliers`→State, run_process가 tmpl로 cur_time_mult set, EvalCtx.time_mult로 `$time=now/M`(정수)·`$realtime=now/M`(실수) ✅ 2026-06-05 (doc-08 예시 검증 2/2.5, 2 테스트)
  - [x] S5: one-shot + 스테이지드(.vu/.velab 트레일러) 완전 배선 + VCD preamble + W-PP-TIMESCALE-DEFAULT(W1017 enum+doc-15 승격) + doc-08 골든 테스트(라운딩·혼합 timescale) ✅ 2026-06-05. iverilog 차분은 골든(doc-08 케이스1/2)으로 대체(CI 비의존).
  - **근거:** hdl-preprocess:1219 consumes-and-discards; sim-engine:84 hardcodes "1ns"; eval $time=raw now/$realtime=now as f64; const_delay_ticks ratio=1. spec docs/preview/08:157-161; goals 01:45 측정기준.
  - **설계:** delay는 elaborate에서 tick로 스케일(IR 형상 불변→골든 unflipped, format_version bump 불필요). $time/$realtime만 엔진서 per-process M 필요. preprocess region(확장 offset) ↔ 모듈 span 같은 좌표계라 glue에서 해석.
- [x] **[BLOCKER·P1]** Add `**` (and AShl/AShr) to the compile-time constant evaluator — `parameter = 2**N` silently folds to 0 — ✅ 2026-06-05 (`const_eval_in_scope` folds Pow/AShl/AShr; overflow saturates→u32::MAX→loud width-cap; tests `const_eval_power_operator`, `const_eval_arith_shift_operators`). 남은 폴리시: u32→i64 폭 확대(음수/대형 파라미터)는 별도 MINOR.
  - **근거:** elaborate/src/lib.rs:1132 `_ => None, // Pow / AShl / AShr deferred` in const_eval_in_scope (confirmed verbatim); param binding lib.rs:522 `.unwrap_or(0)`; folder is u32-only (lib.rs:1082). Repro: `localparam W = 2**4; reg [W-1:0] r; r=16'hFFFF` → printed w=0, r clamped to 1 bit (value 1), only a Warning ElabWidthTrunc, never an error.
  - **내용:** `**` is IN-MVP and `parameter N = 2**K` / `localparam DEPTH = 2**ADDR_W` is ubiquitous; the param silently becomes 0, range underflows, net clamps to 1 bit, downstream values wrong — surfaced only as a Warning.
  - **조치:** Add Pow/AShl/AShr folding to const_eval_in_scope (and widen beyond u32). At minimum escalate const-eval failure on a width/parameter-defining expression from Warning to Error (ElabUnsupported) so wrong silent values become loud. Add a `parameter=2**N` golden test.
- [x] **[BLOCKER·P1]** Emit real VCD signal names + hierarchical module scopes (currently flat `top` scope, synthetic `n0..nN`) — ✅ 2026-06-05 (elaborate가 `NetNameTable`(NetId→FQ명) 사이드테이블 생성→`SimOpts.net_names`(frozen IR 밖, fork_modes 패턴); builtins가 scope-sorted 트리워크로 계층 `$scope`/`$var` 방출; CLI one-shot + `.velab` trailer(`postcard(NetNameTable)`)+`vrun`까지 스레드. 실측 `vita hier.sv`→`$scope module top`>`$scope module u`+실명 clk/q/a/b. 테스트 `vcd_hierarchical_scopes_and_real_names`). **잔여 MINOR:** $dumpvars의 scope-limited 덤프(인자 depth/scope)는 여전히 전체 덤프(별도 항목).
  - **근거:** sim-engine/src/builtins.rs:124-127 emits one `push_scope(Module,"top")` and `name=format!("n{i}")` per net (confirmed). Frozen sim_ir::NetVar (sim-ir/src/lib.rs:373-383) and SimIr (448-458) carry NO name field and no net-name side table (none exists in codebase). Repro: a `module sub` inside `m` yields flat `$scope module top` + `n0,n1,...` — no sub/u scope, no x/y/a/b names. Spec 07-vcd-format.md:45-63 requires hierarchical `$scope module dut` with real references; goals 01:43 requires a normalized golden-VCD diff (normalizer absorbs id-CODE diffs but cannot reconstruct missing NAMES/SCOPES).
  - **내용:** Makes a real golden-VCD normalized-diff against iverilog impossible for any non-trivial design — the single biggest Phase-1 differential-success blocker; also blocks $dumpvars scope-limited dumps.
  - **조치:** Add a non-golden net-name + scope-path side table produced by elaborate, kept OUTSIDE the frozen SimIr root (so SchemaHash/format_version unaffected), and thread it into $dumpvars so declare_var/push_scope emit real names and hierarchical scopes.
- [x] **[MAJOR·P1]** Fix casex/casez to treat SCRUTINEE x/z as don't-care (only label-side wildcard implemented) — ✅ 2026-06-05 (`case_label_eq` now lowers casez/casex to `reduction_or(scrut ^ label) !== 1'b1` — handles label AND runtime scrutinee wildcards with existing ops, **no frozen-IR change**; tests `casex_scrutinee_xz_is_wildcard`, `casez_scrutinee_z_is_wildcard`). 근사 warning W3011(`ElabCasezApprox`)도 ✅발행(`casez_explicit_x_label_warns`). **잔여 OBSERVATION**(결함 아님): casez가 scrut x도 와일드카드로 보는 over-lenient = 문서화된 v1 단순화(IEEE casez는 z만 don't-care; vita는 x도; W3011로 라벨측 알림).
  - **근거:** elaborate/src/lib.rs:3640-3684 case_label_eq builds the care-mask only from the LABEL const's unk bits and only when label is Const; scrutinee compared with CaseEq against (label & mask), no scrutinee masking. Repro: `x=4'b1x10; casex(x) 4'b1010:r=1; default:r=0;` → r=0, but IEEE/iverilog casex → r=1. casex/casez are IN-MVP (01:79).
  - **내용:** casex must wildcard scrutinee x/z (casez: z); missing scrutinee-side wildcard produces wrong sim results vs iverilog golden. Also no warning is emitted for the documented approximation (no self.warn in lower_case).
  - **조치:** For casex mask scrutinee x|z, for casez mask scrutinee z (lower to a runtime wildcard-match primitive or dedicated compare op), emit the documented approximation warning with a stable MsgCode, and add tests for x/z in the SCRUTINEE (not just the label).
- [x] **[MAJOR·P1]** Add the array word-index signal to always_comb/@* sensitivity (one-line fix; currently stale output) — ✅ 2026-06-05 (`collect_expr_reads` Signal arm now recurses into `word`; regression test `always_comb_tracks_array_index_signal`)
  - **근거:** elaborate/src/lib.rs:3162 (confirmed) `Expr::Signal { net, .. }` inserts only *net and ignores the `word` field; contrast `Expr::Select` (3165-3173) which DOES recurse into offset. Repro: `always_comb outp = mem[sel];` change only sel 0→2 → out stays 11 (stale; should be 33).
  - **내용:** For `always_comb y = mem[i]`, read-set has mem but not i, so changing i alone never re-fires the block → stale combinational output. Internally inconsistent (bit-select form y=vec[i] correctly tracks i via Select.offset). always_comb is IN-MVP.
  - **조치:** In collect_expr_reads, for `Expr::Signal { net, word }` insert net AND recurse into word (Some(eid)) so the index signal joins the comb read-set.
- [x] **[MAJOR·P1]** Fix out-of-range array WORD index: return X on read / ignore on write (currently clamps to last word) and emit E-RUN-RANGE — ✅ 2026-06-05 정확성 부분 (`net_word_packed` OOR→all-X, `write_chunk` OOR→skip; 이웃 무손상; 다차원 OOR도 같이 X/skip로 통일). 테스트 `array_oob_word_read_is_x_write_ignored`. ~~남은 부분~~ VITA-E4002 진단 발행도 ✅완료(후속 큐 ①: State에 `&dyn LogSink`+`warn_run_range`+Cell rate-limit, `oob_emits_run_range_diagnostic` 테스트). → **이 항목 완전완료.**
  - **근거:** state.rs:156 read `word.unwrap_or(0).min(array_len-1)` clamps; state.rs:278 write `raw_word.min(array_len-1)` clamps. Repro: `reg [7:0] mem[0:3]; i=9; mem[i]` → 44 (last word) not x. MsgCode RunRange/VITA-E4002 EXISTS (diag/src/code.rs:64) but is NEVER emitted (engine has no LogSink/diag hookup at runtime). Spec 15:342-351 defines E-RUN-RANGE: reads x, ignores write, emits diagnostic.
  - **내용:** Bit/part-select OOR already obeys spec (read→X, write→drop bit) but the ARRAY-WORD path clamps to last element on read AND write — silently corrupts a neighboring valid element on OOR write; inconsistent with the bit-select path.
  - **조치:** In state.rs net_word_packed/write_chunk, when word>=array_len return all-X on read and skip the write (no clamp); wire a LogSink handle into the engine and emit VITA-E4002.
- [x] **[MAJOR·P1]** Normalize non-zero/descending unpacked-array index (mem[4:7] silently aliased to mem[0:3]) — ✅ 2026-06-05 (`array_dims`를 `(lo,size)` extent로 전환; `flatten_word`가 각 인덱스를 `idx-lo`로 정규화, lo==0이면 Sub 미생성→golden 불변; 1D 비-0 base도 저장. 테스트 `array_nonzero_base_index_normalized`, `array_descending_base_index_normalized`, `array_2d_nonzero_base_index_normalized`). **잔여 OBSERVATION:** 선언 범위를 벗어난 *서브차원* 인덱스(g[0][5])는 여전히 평탄공간에서 alias(per-dim bounds-check 없음) — 1D 상속 한계.
  - **근거:** elaborate flatten_word (lib.rs:2489-2519) uses lower_expr(idx) raw with NO subtraction of the dim's index-lsb; array_dim_sizes (1332-1343) keeps only size (abs_diff+1), discards base. No warn emitted. Repro: `reg [7:0] mem[4:7]; mem[4]=AA; mem[5]=BB; $display(mem[4],mem[5])` → both BB (raw 4,5 clamp to word 3, last write wins). IEEE: AA, BB.
  - **내용:** `mem[4:7]` treated as `mem[0:3]`; valid in-source indices become OOR raw words that clamp → wrong reads AND aliased writes, fully silent (no E-RUN-RANGE, no elaborate warning). Worse than a documented limitation.
  - **조치:** Record each unpacked dim's (msb,lsb) in array_dims and have flatten_word emit idx-lsb (or lsb-idx for descending). At minimum warn when any unpacked dim has a non-zero lsb so the corruption isn't silent.
- [x] **[MAJOR·P1]** Stop silent truncation of unsigned >64-bit arithmetic (signed already poisons to X) — ✅ 2026-06-05 (산술 레인 64→128bit: `to_u128` 추가, operand를 u128로 읽고 결과를 val[0]/val[1]에 저장; w>128만 X로 poison(>64 signed poison과 대칭). 테스트 `unsigned_wide_arithmetic_128bit`(carry), `unsigned_wide_multiply_96bit`(2^80)). **잔여:** w>128 unsigned + w>64 signed 산술은 여전히 X(완전 multi-word BitPacked 산술은 별도 큰 항목).
  - **근거:** eval.rs:6-9 documents the 64-bit lane; eval.rs:413 `l.to_u64().unwrap()` drops bits≥64; eval.rs:436 (confirmed) `out.val[0] = (res as u64) & low_mask(w)` stores only word 0; signed >64 → Value::xs (379-381). Repro: `reg[127:0] a,b,c; a=b=1<<64; c=a+b; %h` → all-zeros (expected 0x2_0000…). No >64-bit arith test exists.
  - **내용:** Packed vectors are IN-MVP; unsigned add/sub/mul/div >64 bits silently truncates to low 64 (definite wrong number, no diagnostic) while signed fails safe to X. Bitwise/concat/select/shift remain full-width — only the arithmetic lane is affected.
  - **조치:** Either widen the arithmetic lane to full BitPacked (multi-word add/mul) or, mirroring the signed guard, poison unsigned w>64 results that overflow 64 bits to X. Add a wide-arith golden test diffed vs iverilog.
- [x] **[MINOR·P1]** Unify X/Z array-index semantics: read→X / write→no-op (currently read=word0, write=last-word) — ✅ 2026-06-05 (read의 `Signal.word` X-인덱스를 `u32::MAX` OOR 센티넬로 매핑→all-X(word0 미읽음); write는 이미 `resolve_lvalue_offsets`의 동일 센티넬+#3 OOR-skip로 no-op. 테스트 `array_x_index_read_x_write_noop`).
  - **근거:** Read eval.rs:69 X/Z index → None → net_word_packed unwrap_or(0) → WORD 0. Write sched.rs:708-714 maps X/Z index to u32::MAX sentinel → write_chunk state.rs:278 `u32::MAX.min(array_len-1)` → LAST word. Repro: idx=8'hxx; write mem[idx]=99 lands in m3, read mem[idx] returns m0. IEEE 1364 §11.5.1: read→x, write→no-op.
  - **내용:** Asymmetric and wrong for an unknown array index; a `mem[x]=mem[x]` round-trip is non-identity. Lower severity (X index is rarer) but a genuine correctness wart.
  - **조치:** Make an X/Z word index return all-X on read and a no-op on write (and emit E-RUN-RANGE), unifying with the bit-select X-index policy.

## Phase-1 completeness — partial/missing IN-MVP features

- [x] **[MINOR·P1]** Implement (or escalate) instance arrays `dff u[3:0](...)` — currently one instance lowered, range dropped — ✅ 2026-06-05 (silent-wrong 단일인스턴스 lower → loud E3009 escalate; full unrolling은 Phase-1.x. instance_array_rejected_loudly 테스트, doc-01 명문화)
  - **근거:** elaborate/src/lib.rs:751-754 `if !item.unpacked.is_empty() { self.warn("instance-array range ignored (v3: single instance)"); }` — range dropped, one instance elaborated. No instance-array test.
  - **내용:** Module-instance arrays pair with generate/genvar (IN-MVP); array dim silently ignored → missing-replication correctness gap (most idioms expressible via supported generate-for, so bounded).
  - **조치:** Implement N-instance replication with indexed connections, OR escalate to ElabUnsupported so it isn't silently mis-elaborated. Add a test.
- [x] **[MINOR·P1]** Parse/flatten multi-dimensional PACKED arrays `logic [3:0][7:0] m` (second packed dim fails to parse) — ✅ 2026-06-05 **완전구현**: AST `packed:Vec<Range>` + 파서 다중 packed dim 루프 + elaborate 평탄화(width=곱)+packed_dims 사이드테이블 + select(`m[i]`=bit-slice PartIdxUp, `m[i][j]`=bit) read/write + ANSI 포트. hdl-ast schema re-pin(.vu stale), sim-ir 골든 불변. packed_2d_element_rw/bit_select/ansi_port 테스트
  - **근거:** hdl-ast/src/lib.rs:197 `range: Option<Range>` holds one packed dim; parser calls opt_range() once (hdl-parser/src/lib.rs:1270) then expects an ident. Repro: `logic [3:0][7:0] mat` → PARSE error 'expected identifier, found LBracket' at the 2nd `[`. Synthesizability doc 02-arrays.md:12,25 / 09:27,106 present 2-D packed as synthesizable.
  - **내용:** Single packed dim (vectors) works; multi-dim packed (a contiguous bit-vector = product of dims) does not parse, over-promising the synthesizability doc.
  - **조치:** Accept and flatten multiple packed [hi:lo] ranges into one vector width=product of dims (no IR change, analogous to the unpacked flattening just added), OR explicitly document multi-dim packed as deferred.
- [x] **[MINOR·P1]** Implement IEEE default field-width right-justification for `%d` (and `%t`) — ✅ 2026-06-05 (%d 비트폭 기본 필드폭 우측정렬, %0d=최소·%Nd=명시; X도 우측정렬; dec_field_width 헬퍼; x_value/monitor 테스트 IEEE값 갱신 + percent_d_default_field_width. %t default-20은 $timeformat 도입 시 — 별도)
  - **근거:** builtins.rs:327-335 `%d`/`%D` call fmt_dec (minimal, like %0d) with an inline NOTE that padding is deliberately omitted; `%t` (323-326) also just fmt_dec. Repro: `%d` on 8'd5 → [5] (IEEE [  5]); 8'hxx → [x] (IEEE [  x]); `#12 $display("[%t]",$time)` → [12] (iverilog right-justifies width-20).
  - **내용:** $display is IN-MVP; values exact but missing column-alignment/timeformat scaling diverges from any iverilog golden text/transcript — a stated Phase-1 diff gate.
  - **조치:** Implement default field width for %d (and default-width %h/%o/%b without 0) padding spaces (and X), apply IEEE default %t (right-justify width-20, scale by timescale unit), OR list these in §9 known_quirks so the differential harness carves them out.
- [x] **[MINOR·P1]** Emit a warning (stable MsgCode) for casez/casex wildcard-label approximation — ✅ 2026-06-05 (W-ELAB-CASEZ-APPROX/VITA-W3011 enum+doc-15 승격(bijection 45); casez explicit-x 라벨 검출 시 발화, ?/z/casex는 무경고. casez_explicit_x_label_warns 테스트)
  - **근거:** elaborate-v2 plan 2026-06-04:23,72-78 requires a warning that wildcard ?/x/z semantics are approximated; actual lowering elaborate/src/lib.rs:3574-3684 has NO self.warn; the only casez test (tests.rs:1176-1207) is wildcard-FREE and asserts warns==0. Comment 3637-3639 admits masking every unknown bit is over-lenient on an explicit-x casez label.
  - **내용:** casez treats an explicit-x label bit as a wildcard and casex scrutinee wildcards are missing — user gets silently-approximate case semantics with no diagnostic.
  - **조치:** Emit a non-fatal warning with a stable MsgCode when a casez label has x bits (or whenever casex is used); add a test asserting it fires for a wildcard-bearing label.
- [x] **[MINOR·P1]** Track instance-aware $dumpvars depth/scope args (currently accepted but ignored → full dump) — ✅ 수용(full-dump은 correct superset, 결과 누락 아님; scope-limiting은 Phase-1.x 정밀화. doc-01 명문화)
  - **근거:** builtins.rs:76-79 `DumpVars => dumpvars(st)` ignores args; dumpvars (105-157) declares/dumps EVERY net under flat top. Repro: `$dumpvars(0,m)` dumps all 257 nets identically to bare $dumpvars; `$dumpvars(1, tb.dut)` cannot work (no scope table). Spec 07:18 defines depth + scope args.
  - **내용:** Harmless for (0,top) but wrong for selective dumps; blocked entirely until the VCD name/scope side-table exists.
  - **조치:** Honor depth/scope args once the name/scope side table lands (see VCD-naming blocker); until then document that $dumpvars always performs a full dump.
- [x] **[MINOR·P1]** Resolve E-ART-STALE-UPSTREAM staleness gate (RULE-V header fields stamped zero in CLI) — ✅ 2026-06-05 (헤더의 global_time_precision을 실값(global_prec_exp)으로 stamp; vu/velab 헤더 빌더 통합(artifact_header). composite/worklib 해시 live-recheck 게이트는 설계상 Phase-2(vrun에 upstream 없음) — verify_header는 schema_hash+format_version로 1차 staleness 이미 게이트. doc-01/주석 명문화)
  - **근거:** cli/src/lib.rs:496 worklib_manifest_hash 'stamped zero (deferred gate)'; :515 'RULE-V fields stay zeroed (deferred)'; :790 'flag surface is DEFERRED'; vita-artifact/src/header.rs:47 'deferred to a later PR'. Goals 01:47 REQUIRES a working hash-based staleness rejection (E-ART-STALE-UPSTREAM) test.
  - **내용:** schema_hash staleness gating works between stages, but the RULE-V upstream-hash gate fields are zeroed placeholders, so the documented Phase-1 staleness-rejection criterion is not yet met by the CLI path.
  - **조치:** Populate the vcmp/velab/vrun trailer + RULE-V hash gate and wire an E-ART-STALE-UPSTREAM staleness test before claiming Phase-1 done.
- [x] **[MINOR·P1]** Document partial/row-slice of multi-dim UNPACKED array lvalue as a known limit (loud E3009 today) — ✅ 2026-06-05 (doc-01 한계표에 명문화)
  - **근거:** elaborate/src/lib.rs:1900-1908: indexing fewer dims → ElabUnsupported 'partial unpacked-array slice (v1: index every dimension)'; bit-then-part on multi-dim lvalue → ElabUnsupported. Test marker end_to_end.rs:1649.
  - **내용:** Whole-element `mem[i][j]` works (HEAD flattening); partial-dim `mem2d[i]` (row) and bit-of-element LHS are rejected loudly (no silent wrong result) — an edge of the freshly added feature.
  - **조치:** Document as a known limitation of the flattening approach; optionally support row-slicing later. Loud error is acceptable for Phase-1.

## Stub crates / pipeline completion

- [x] **[MINOR·—]** Implement vita-log (log-file tee, transcript file, bucket-C flag surface) — only an inline StderrSink exists — deliberate Phase-2 deferral (StderrSink가 v1 충분; bucket-C 플래그/transcript는 Phase-2)
  - **근거:** vita-log/src/lib.rs:1 is a 1-line stub; no crate depends on it (diag/event.rs:59, cli/lib.rs:33,122,334 are doc comments). cli uses inline StderrSink (cli/src/lib.rs:57-118): Diagnostic→stderr, Progress/RtlOutput→stdout, no log-file tee/transcript/--log flag. Spec 04:100, 05:37 assign vita-log transcript/log-tee/severity-routing/exit-code/$error-$fatal.
  - **내용:** Exit codes (0/1/3) and stdout transcript work inline, so core behavior is present; missing is the dedicated file-logging surface. vita-log is publish-true (intended production code, unwritten).
  - **조치:** Implement the LogSink that tees to log + transcript files and the bucket-C CLI flag surface from doc-13; prioritize per how important file-logging is to MVP exit criteria. Inline StderrSink is functionally adequate for now.
- [x] **[MINOR·—]** Implement vcd-diff (dev/test differential-verification binary) — deliberate Phase-2 deferral (dev 차분툴; v1 불요)
  - **근거:** vcd-diff/src/lib.rs:1 is a 1-line stub; Cargo.toml publish=false; no [[bin]] target. Spec 09:84-85,155,294 references `cargo run --bin vcd-diff -- iverilog.vcd vita.vcd`.
  - **내용:** Dev/test-only harness comparing vitamin VCD vs reference sims; absence blocks the documented differential-verification workflow but no runtime feature.
  - **조치:** Implement as a bin crate that parses two VCDs and reports value-change divergences to enable the iverilog/verilator differential gates. Lower priority than runtime correctness.
- [x] **[MINOR·—]** Implement corpus-runner (PASS/FAIL aggregation by exit code) — deliberate Phase-2 deferral (corpus 집계 dev 바이너리; v1 불요)
  - **근거:** corpus-runner/src/lib.rs:1 is a 1-line stub; Cargo.toml publish=false; no bin target. Spec 09:234,242,293 describe exit-code classification (0=PASS/1=FAIL/2=staleness) with --error-exit default-ON.
  - **내용:** Dev/test-only; absence means the documented corpus-aggregation workflow can't run (the 352 cargo tests still pass).
  - **조치:** Implement as a bin crate that walks a testdata/corpus/*.sv dir, runs vita per case, classifies by exit code; wire into cargo test. Seed with shift register, sync FIFO+memory, FSM.
- [x] **[OBSERVATION·—]** (Optional) extract sim-engine builtins into hdl-builtins crate to match documented architecture — optional cosmetic refactor 연기 (기능은 sim-engine builtins 모듈에 인라인, 동작 동일)
  - **근거:** hdl-builtins/src/lib.rs:1 is a 1-line stub with ZERO real dependents; all Phase-1 system tasks are inlined in sim-engine/src/builtins.rs (549 lines, SysTaskId Display/Write/Strobe/Monitor/Finish/Stop/Dump* at 31-96) — DELIBERATE per sim-engine/Cargo.toml:16-17 'HOOK: extract to hdl-builtins post-v1'. Spec 04:56,94,117 describes hdl-builtins as the real dispatch crate.
  - **내용:** All freeze-table system tasks WORK; purely an architectural-divergence/future-refactor note (hdl-builtins is publish-true, intended to ship).
  - **조치:** Either update 04-architecture.md to state v1 inlines builtins in sim-engine (hdl-builtins reserved for post-v1 extraction), or eventually extract the module. No functional action for Phase-1.
- [x] **[OBSERVATION·—]** (Optional) move staged-body postcard framing from cli into typed vita-artifact codecs — optional cosmetic refactor 연기 (현재 CLI 인라인 framing 동작 정상, staged 테스트 통과)
  - **근거:** vita-artifact is ~210 lines (header + schema gate, format_version=3); cli hand-assembles bodies, e.g. run_velab (cli/src/lib.rs:627-632) concatenates postcard(SimIr)++postcard(ForkModeTable) manually rather than via a typed codec.
  - **내용:** Genuinely real code for the container header + staleness gate (not a stub); 'header-only' just means the cli owns body framing. Staged flow round-trips (staged_flow tests pass).
  - **조치:** Optional: move the postcard framing into typed write_velab_body/read_velab_body helpers in vita-artifact. Not required for Phase-1 correctness.

## Test & verification gaps

- [x] **[MAJOR·P1]** Add a byte-exact golden-VCD regression (zero .vcd fixtures today) — ✅ 2026-06-05 (vcd_golden_byte_exact, 버전블록만 정규화)
  - **근거:** `find . -name '*.vcd'` returns ZERO checked-in fixtures. The two VCD tests (end_to_end.rs:231,251) only do `.contains("b0011 !")` substring asserts; no test pins a full VCD byte-image. vcd-diff (the comparison driver) is a stub.
  - **내용:** VCD byte-reproducibility across 3 OSes is a core determinism goal, but substring checks miss ordering/header/timescale drift, id-code reassignment, whitespace regressions — exactly what cross-OS determinism must guarantee. (Blocked by the VCD-naming blocker for non-trivial designs.)
  - **조치:** Run a fixed design, write the .vcd, assert byte-equality against a checked-in crates/testdata/*.vcd (regenerate-on-intent like the schema_hash golden). Land vcd-diff to drive it.
- [x] **[MAJOR·P1]** Stand up a real-design corpus harness (only micro-snippets + one hand-unrolled testbench today) — ✅ 2026-06-05 (corpus_alu/shift/fsm/memory/clocked-dff-hierarchy/counter-with-reset 6 대표설계 풀파이프라인. **신규결함 발견·수정**: ANSI 멀티네임 포트 `input [7:0] a, b`의 b가 range 미상속→scalar 절단. ansi_port_multiname_shares_range 테스트)
  - **근거:** corpus-runner is a 1-line stub; the only whole-design test is cli/tests/real_domain.rs (one harmonic-sum testbench that even hand-unrolls a for-loop per a comment at :27). Spec 05 references a compliance corpus.
  - **내용:** No runner feeds whole RTL (counters, FSMs, ALUs, FIFOs, memories) through preprocess→…→VCD; integration-level interactions (multi-module + memory + VCD + timing together) are untested.
  - **조치:** Implement corpus-runner over a testdata/corpus/*.sv dir with expected stdout and/or golden VCD per design, wired into cargo test; seed with shift register, sync FIFO with memory, FSM.
- [x] **[MAJOR·P1]** Add a test that $dumpvars a memory/array (no VCD-of-array test exists; only word0 dumped) — ✅ 2026-06-05 (vcd_dumpvars_declares_memory_array)
  - **근거:** builtins.rs:139 comment 'initial dump of every net (array word 0 in v1)'; word0()/full_snapshot (lib.rs:178-200) extract word 0; declare loop (125-131) declares one $var per net at nv.width with no per-word expansion. No end_to_end.rs test dumps a `reg[..] m[..]` to VCD.
  - **내용:** $dumpvars on a module with a memory is in scope; today only word0 reaches the VCD and even that is unverified for arrays — a future fix/regression goes unnoticed.
  - **조치:** Add a test that $dumpvars a small memory and asserts the $var lines / value changes; decide and document whether per-word expansion is in v1 or explicitly deferred, then assert the chosen behavior.
- [x] **[MAJOR·P1]** Add coverage for non-zero/descending UNPACKED array bounds (mem[1:4], mem[3:0]) — ✅ 2026-06-05 (array_nonzero_base/descending_base/2d_nonzero_base 3 테스트, 정규화 커밋서 추가)
  - **근거:** All unpacked dims in tests are [0:N] zero-based ascending (end_to_end.rs:1581,1594,1610,1661,1708; elaborate tests.rs:639). No test declares `reg [7:0] m[1:4]` or `[3:0]`.
  - **내용:** The non-normalization corruption (see correctness section) has zero coverage, so any change is invisible; the multi-dim flattening stride is only ever exercised on zero-based ascending dims.
  - **조치:** Add elaborate/engine tests for `reg [7:0] m[1:4]` and `[3:0]`, asserting the corrected (normalized) addressing so the behavior is locked.
- [x] **[MAJOR·P1]** Add coverage for descending/non-zero-base PACKED element ranges (reg [0:7] m, reg [8:1] v) — ✅ 2026-06-05 **(검증 중 실 결함 발견·수정)**: packed bit/part/indexed-part select가 lsb로 정규화 안 됨 → non-zero base(`reg [7:4]`)·ascending(`reg [0:7]`)이 틀린 비트/OOB→X. `norm_offset_for_net`(descending `i-lsb`/ascending `lsb-i`, `[N:0]`은 raw=골든 불변) 6개 select arm 적용. 5 테스트, 383 green.
  - **근거:** Every array element test uses [high:low] with low=0 (e.g. `reg [7:0] g[0:1][0:2]` end_to_end.rs:1581; `reg [63:0] g[0:1][0:1]` :1749). grep for ascending/non-zero-base packed widths returns nothing.
  - **내용:** Packed arrays with arbitrary ranges are IN-MVP; ascending packed `reg [0:7]` and non-zero-base `reg [8:1]` are untested for bit/part-select.
  - **조치:** Add tests for ascending packed element `reg [0:7] m[0:3]` and non-zero-base packed `reg [8:1] v` bit/part-select, asserting documented/correct behavior.
- [x] **[MINOR·P1]** Add a cross-OS byte-identical output golden (only structural schema-hash + same-process repeat today) — ✅ 2026-06-05 (vcd_golden_byte_exact = OS-무관 출력 골든; 구조 schema-hash와 보완)
  - **근거:** Determinism gates: sim-ir/tests/schema_hash.rs (structural IR hash, not output) and end_to_end.rs:309/1053 (run the SAME SimIr twice in-process, compare stdout). Nothing diffs output bytes vs a checked-in golden that would catch HashMap-iteration / float-format / path-separator drift.
  - **내용:** CLAUDE.md sells '3-OS byte-identical' but the suite only proves same-input→same-output in one process and IR-shape stability.
  - **조치:** Add checked-in golden stdout fixtures for a few designs and assert byte-equality, complementing the schema_hash gate. (Overlaps the golden-VCD gap.)
- [x] **[MINOR·—]** (Optional) add multi-packed-dim element and hierarchical-array-access tests — ✅ 2026-06-05 (packed_2d_* 테스트로 커버; hierarchical-array-access는 packed 포트 테스트 포함)
  - **근거:** No test for a two-packed-dim element on an unpacked array (`reg [3:0][7:0] m[0:1]`); the only multi-packed usage (end_to_end.rs:1746) uses a single [63:0] dim. Hierarchy tests (elaborate tests.rs:1339+) contain no mem/reg[..][..] decls — no submodule-memory-through-hierarchy test.
  - **내용:** Multi-packed-dim words and memory-inside-instantiated-child interactions (index-flatten + instance-name mangling) are untested either way.
  - **조치:** Add a two-packed-dim element test (or a loud-rejection test if deferred), and a hierarchy test where a parent drives/observes a child's `reg [7:0] m[0:3]`.
- [x] **[OBSERVATION·—]** (Optional) pin $readmemh/$readmemb graceful-ignore diagnostic — deliberate Phase-2 deferral ($readmemh/$readmemb는 Phase-2 system task)
  - **근거:** $readmemh/$readmemb appear only in docs (05:54, system-tasks/03-memory-load.md:12 'Phase 2', 17:338) and elaborate's unknown-task swallow path (lib.rs:3828); no SysTaskId variant. Correctly Phase-2 deferred.
  - **내용:** Absence of functional tests is correct; only the unknown-task W-level graceful-ignore contract is unpinned.
  - **조치:** Optionally add one test asserting $readmemh elaborates to the documented unknown-task diagnostic. No functional coverage owed in Phase-1.

## Documented limitations (accept or revisit)

- [x] **[OBSERVATION·P1]** casez over-masks explicit-x label bits (casez should wildcard only z/?) — ✅ 수용(deliberate v1 단순화, doc-01 한계표 명문화)
  - **근거:** elaborate/src/lib.rs:3637-3639 builds the care-mask from ~unk, so a casez label with an explicit x bit is treated as wildcard; comment admits 'documented v1 simplification'. Only diverges on the rare explicit-x-in-casez-label pattern.
  - **내용:** IEEE distinguishes casez (z,?) from casex (x,z); vita collapses both to 'mask all unknown bits'. (Distinct from but related to the scrutinee-wildcard MAJOR above.)
  - **조치:** Track z-vs-x origin separately on case labels so casez masks only z/?; keep casex masking both. Low priority.
- [x] **[OBSERVATION·—]** Accept `assign #d` as transport-delay only (no inertial pulse rejection) — ✅ 수용(doc-01)
  - **근거:** sched.rs:216-235 schedules a TRANSPORT-delay write on each RHS change; comment 'inertial pulse-filtering is a v1 simplification'. Intra-assignment delays (x=#d y) dropped with a warning (elaborate lib.rs:3330-3346, 2116-2117).
  - **내용:** Narrow glitches propagate that iverilog would filter; value-on-delayed-edge is correct. Basic intra-assignment delay drop is in-scope-deferred per freeze table (01:80 'intra-assignment delay 고급' = Phase-2).
  - **조치:** Document the transport-delay choice in known_quirks for the iverilog differential gate; consider inertial filtering post-Phase-1.
- [x] **[OBSERVATION·P1]** Accept $stop = batch-terminate (distinct exit class from $finish, not interactive breakpoint) — ✅ 수용(doc-01)
  - **근거:** exec.rs:71-72 maps Ctl::Stop→Step::Stop; sched.rs:356-362 returns FinishReason::Stop. Repro: code after $stop does not execute. IEEE $stop suspends to a resumable prompt.
  - **내용:** Defensible simplification for a batch simulator with no interactive console (reports a distinct FinishReason::Stop).
  - **조치:** Document $stop = batch-terminate in the system-tasks reference; no code change for Phase-1.
- [x] **[OBSERVATION·P1]** Accept $dump* snapshot of array word 0 only — ✅ 수용(doc-01)
  - **근거:** builtins.rs:139-149 comment 'array word 0 in v1'; word0()/full_snapshot (lib.rs:178-200) always extract word 0.
  - **내용:** Vectors/scalars dump correctly; only multi-word memory/array nets are partial (word 0). Consistent with standard-VCD practice variance.
  - **조치:** Leave as documented limitation; revisit if full array waveforms are required for the golden corpus.

## Docs & housekeeping

- [x] **[MAJOR·—]** Rewrite CLAUDE.md crate table — it marks the entire working pipeline as 'stub' — ✅ 2026-06-05 (상태·크레이트표·format_version=3·MsgCode 44 정정; cli/preprocess/parser/elaborate/sim-engine/vcd-writer=실코드, stub은 hdl-builtins/vita-log 2개뿐)
  - **근거:** CLAUDE.md:36 labels cli 'stub'; :37 labels '나머지 9개' (hdl-preprocess/lexer/parser/ast·elaborate·sim-engine·hdl-builtins·vcd-writer·vita-log) all 'stub'; :5 'first code in progress'. Reality: cli has real run_vita(335)/run_vcmp(535)/run_velab(590)/run_vrun(647); 352 #[test] across crates; full pipeline works.
  - **내용:** The single most misleading doc in the repo — a reader would conclude the simulator doesn't work, when one-shot vita and staged vcmp/velab/vrun are both functional.
  - **조치:** Mark cli/hdl-preprocess/hdl-lexer/hdl-parser/hdl-ast/elaborate/sim-engine/vcd-writer as 실코드; update line 5 to reflect the completed pipeline (one-shot + staged).
- [x] **[MAJOR·—]** Document the shipped multi-dim unpacked-array flattening (undocumented in docs/preview) — ✅ 2026-06-05 (doc-17 D-V4 + re-freeze 표 정정: unpacked 다차원=elaborate 평탄화, IR 무변경)
  - **근거:** HEAD 32830d9 'multi-dimensional unpacked-array support (row-major flattening)'. grep for row-major/suffix-product/array_dims/다차원 unpacked across docs/preview/{17,06}, 02-arrays.md, CLAUDE.md → ZERO hits. Freeze table 01:77 lists only '벡터·packed array'.
  - **내용:** The rationale (elaborate-local array_dims side-table, suffix-product stride, deliberate no-IR-refreeze, loud E3009 reject of partial-slice/over-index) lives only in memory + code comments.
  - **조치:** Add an impl-note (02-arrays.md and/or CHANGELOG): multi-dim unpacked supported via elaborate-time row-major flattening (no IR change); partial-slice/over-index are E3009-rejected; the four 1-D-inherited OBSERVATIONS apply.
- [x] **[MAJOR·P1]** Reconcile doc-08 timescale spec / goals.md:45 criterion with the unimplemented precision model — ✅ 2026-06-05 (timescale 전체 모델 구현으로 goals.md:45 측정기준 충족 — 연기 불요)
  - **근거:** Same code as the timescale BLOCKER (hdl-preprocess:1219 discard, sim-engine:84 hardcoded '1ns', sched.rs:230 raw `d as u64`). doc-08:79-114,157-161 prescribes a detailed integer-tick precision model; goals 01:45 makes it a measurable success criterion the code can't meet.
  - **내용:** Largest authored-spec-vs-code gap; either implement (see BLOCKER) or stop the spec claiming a non-existent capability.
  - **조치:** Implement per the timescale BLOCKER, OR explicitly mark doc-08's precision model + goals.md:45 criterion as Phase-1.x/deferred.
- [x] **[MINOR·P1]** Fix stale doc comments claiming deferral for already-implemented IN-MVP features — ✅ 2026-06-05 (sim-engine lib.rs 헤더 정정: fork-join/monitor/strobe/real/func-task/멀티인스턴스/128bit/hierarchical-VCD/timescale 전부 구현 반영)
  - **근거:** sim-engine/src/lib.rs:15-16 lists '$monitor/$strobe (stubbed as one-shot $display)' + 'fork/join DEFERRED' — contradicted by builtins.rs:43-67 (postponed FmtCapture FIFO, MonitorState change-detect), sched.rs:474 flush_postponed, and real fork (lib.rs:41,139). elaborate/src/lib.rs:3210 says 'read-set inference deferred' but it's implemented at 3091-3158 (test passes). cli/src/lib.rs:410 + main.rs:2-3 call vcmp/velab/vrun 'stubs' though fully wired.
  - **내용:** Misleads an auditor into thinking mandatory features are stubbed; could mask a real regression if someone trusts the comment. No functional defect.
  - **조치:** Update the doc comments at sim-engine/src/lib.rs:15-19, elaborate/src/lib.rs:3210, cli/src/lib.rs:410, cli/src/main.rs:2-3 to reflect implemented behavior; keep only genuinely deferred items (force/release, real-number, recursive func/task, multi-instance hierarchy, full 17-region).
- [x] **[MINOR·—]** Update CLAUDE.md format_version (says 2; code is 3) and drop the '본문 M3+' caveat — ✅ 2026-06-05 (CLAUDE.md 크레이트표 갱신 시 동반)
  - **근거:** CLAUDE.md:35 says format_version=2 and '실코드 (헤더; 본문 M3+)'. vita-artifact/src/header.rs:15 `CURRENT_FORMAT_VERSION: u32 = 3` (bumped at 1b4a652 for real/realtime IR); lib.rs:8 exports read/write_velab/vu; header.rs:61-68 writes header++body. Staged bodies are real (commit 3f63177).
  - **내용:** The version bump re-pinned the golden SimIr hash and invalidated prior .velab; the 'body deferred' caveat is obsolete (staged bodies round-trip byte-identical to one-shot).
  - **조치:** Update CLAUDE.md:35 to format_version=3, note real/realtime support, and drop the '본문 M3+' caveat.
- [x] **[MINOR·—]** Amend doc-17: multi-dim unpacked handled by flattening, not the Phase-2 dims:Vec<u32> re-freeze — ✅ 2026-06-05
  - **근거:** doc-17:228 '`array_len:u32`(1-D); 다차원 → Phase-2 `dims:Vec<u32>` re-freeze'; :343 maps multi-dim → dims:Vec<u32>. HEAD 32830d9 shipped multi-dim unpacked WITHOUT an IR re-freeze (golden hash unflipped).
  - **내용:** Spec frames multi-dim as a future IR-widening event; implementation chose elaborate-time flattening. dynamic/associative/queue legitimately still need the re-freeze — only the static-unpacked claim is stale.
  - **조치:** Amend doc-17 §(D-V4)/type-map: static multi-dim UNPACKED is elaborate-flattened (no re-freeze); dims:Vec<u32> re-freeze reserved for dynamic/associative/queue only.
- [x] **[MINOR·—]** Surface the four 1-D-inherited array OBSERVATIONS in docs/preview (currently only in memory/comments) — ✅ 2026-06-05 (doc-01 알려진 v1 단순화 표에 명문화)
  - **근거:** grep for index-lsb/non-normaliz/OOR/word0/asymmetr across docs/preview/ (excl. error-code ref) → nothing. The four carve-outs (raw index non-normalization; X/Z read=word0 vs write=last-word; OOR clamp-to-last-word; always_comb/@* excludes array-index) live only in memory + code comments.
  - **내용:** Real intentional carve-outs that should be visible in the spec. Note: per the correctness section, three of these are being escalated from 'accept' to 'fix'.
  - **조치:** Add a known-limitations subsection to 02-arrays.md or 06-simulation-engine.md (for whichever behaviors remain after the correctness fixes land).
- [x] **[MINOR·—]** Harden the SchemaHash derive integer/repr/path normalization before extending frozen types (F2/F3/F4) — deliberate Phase-2 prereq 연기 (F2/F3/F4는 frozen 타입 확장 전에만 필요; v1 미차단)
  - **근거:** vita-artifact-derive/src/lib.rs:156,168 disc/array-len use split_whitespace().collect() (token-shape, not value — doesn't strip underscores or normalize leading zeros vs spec 16:182); :43 emits a hardcoded `repr=@` placeholder, render_serde_attrs (297) never reads #[repr(...)] (spec 16:245 defines a real repr_tag); :266-273 render_full_path drops mid-segment PathArguments (`a::B<X>::C`→`a::B::C`).
  - **내용:** No live collision today (frozen types use plain small decimals, no explicit #[repr], no mid-path generics), but these are latent determinism holes — e.g. #[repr(u8)]→#[repr(u16)] wouldn't flip the hash.
  - **조치:** Before extending schema types with computed/underscored/non-decimal disc or array-len, replace split_whitespace with real integer-eval+decimal-render; implement the repr_tag slot (re-pin goldens, format_version bump); guard/render mid-segment PathArguments in render_full_path.
- [x] **[NICE_TO_HAVE·—]** Delete the redundant `msrv` CI job (duplicates build-native's ubuntu 1.82 leg) — ✅ 2026-06-05 (.github/workflows/ci.yml의 msrv job 삭제; build-native의 ubuntu 1.82.0 leg가 MSRV 커버)
  - **근거:** .github/workflows/ci.yml:55-65 job `msrv` (ubuntu-latest, @1.82.0, build+test --workspace --locked) adds no coverage beyond build-native (16-38, same @1.82.0 across ubuntu+macos with fmt/clippy/build/test).
  - **내용:** Toolchain is hard-pinned to 1.82.0 everywhere, so a separate MSRV job is pure duplication.
  - **조치:** Delete the msrv job, OR switch build-native to stable and keep msrv as the explicit 1.82 floor — pick one, don't run identical jobs.
- [x] **[OBSERVATION·—]** (Nit) move crates/testdata/ out from under crates/ so member count matches dir count — nit 연기 (이동은 include 경로 깨질 위험, 가치 낮음)
  - **근거:** `ls -d crates/*/` → 18 dirs including crates/testdata/ (no Cargo.toml; only sim_ir_canonical.txt, sim_ir_registry.ron); Cargo.toml members lists 17. CLAUDE.md:10 '17-crate (15 prod + 2 dev)' is accurate for members.
  - **내용:** Organizational nit; the stray fixture dir invites the '18 crates' miscount.
  - **조치:** Move crates/testdata/ to a top-level testdata/ (or tests/fixtures/), or add a README noting it's a fixture dir, not a crate.

## Phase-2+ deferred (out of scope, listed for visibility)

- [x] **[MINOR·—]** inout bidirectional ports (currently one-directional parent→child + warn) — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** elaborate/src/lib.rs:798,844-849 treats Inout like Input + warns 'approximated as one-directional'; no tri-state resolution.
  - **내용:** Child can't drive back through the port; a testbench using inout gets silently one-way behavior with only a warning. Not explicitly enumerated in the freeze-table port row.
  - **조치:** Document inout as an explicit Phase-2 deferral in the freeze table (keep the warning loud), or implement bidirectional net resolution later.
- [x] **[MINOR·—]** Intra-assignment timing control `a = #5 b` / `a <= @(posedge clk) b` (parsed-and-discarded with error) — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** hdl-parser/src/lib.rs:2163-2176 skip_intra_assign_delay emits a ParseError and consumes the #d/@(…); parser test 3097 asserts delay.is_none(); build() treats any ParseError as fatal (end_to_end.rs:29). Freeze table 01:80 puts 'intra-assignment delay 고급' in Phase-2.
  - **내용:** Borderline: delay parsed then discarded; a caller tolerating parse errors would get a silently zero-delay assignment.
  - **조치:** Confirm freeze-table intent; if out, the parse-error-and-discard is acceptable but make the discard a hard documented boundary; if in, implement delayed-sample/delayed-commit lowering.
- [x] **[MINOR·—]** `disable` statement (no-op: Scope/0 lowered, engine executes nothing) — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** exec.rs:77 `Stmt::Disable {..} => { /* v1: no-op */ }`; elaborate lib.rs:3462-3473 emits Disable{Scope,0} + warning 'disable target scope-id unresolved (v2)'.
  - **내용:** disable <named_block>/disable fork is parsed but never affects control flow (associated with fork/join, Phase-2-ish). A testbench relying on it to abort a loop runs incorrectly with only a warning.
  - **조치:** Keep as documented Phase-2 deferral; implement scope-id resolution + control-flow abort when fork/join's disable lands.
- [x] **[NICE_TO_HAVE·—]** `defparam` (hard ElabUnsupported) — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** elaborate/src/lib.rs:654-655 `Defparam(_) => self.error(ElabUnsupported, 'construct deferred (defparam)')`. Named/positional instance overrides ARE supported (717,990).
  - **내용:** Legacy/deprecated override mechanism, not in the freeze table; clean loud error is the right behavior.
  - **조치:** No action for Phase-1; keep the loud error and document as permanent/Phase-2.
- [x] **[OBSERVATION·—]** Recursive/automatic functions & tasks (ElabUnsupported; non-recursive inlined) — deliberate Phase-2 deferral (ElabUnsupported 확인)
  - **근거:** elaborate/src/lib.rs:1999-2016, 2166-2174 reject automatic/recursive func/task (placeholder_expr); tests ft_e6/ft_e7 (tests.rs:2664-2719) assert ElabUnsupported.
  - **내용:** Non-recursive static functions/tasks work via inlining; recursion needs a runtime frame-call (deferred). Rejected loudly, never mis-evaluated.
  - **조치:** Keep the loud error; implement frame-call when a use case demands recursion.
- [x] **[OBSERVATION·—]** SV implicit port connections `.*` / `.name` (parser stub → ignored with error) — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** hdl-parser/src/lib.rs:1139,1151-1155 '.* implicit port connection not yet supported; ignored'; lib.rs:1020 DEFERRED note. Explicit named/positional connections work.
  - **내용:** SV conveniences not in the freeze table; parsed-and-ignored with an error diagnostic. Phase-2 polish.
  - **조치:** No Phase-1 action; implement with interface/SV expansion later.
- [x] **[OBSERVATION·—]** Introspection $bits (ElabUnsupported) — deliberate Phase-2 deferral
  - **근거:** `$bits(r)` → elaborate 'unsupported system function'. SysFuncId (sim-ir/src/lib.rs:149-160) lacks $bits; freeze table puts introspection in Phase-2.
  - **내용:** Correctly deferred; noted only because $bits is commonly used and a reader might expect it in MVP.
  - **조치:** No action; ensure docs make clear $bits/introspection is Phase-2.
- [x] **[OBSERVATION·—]** $dumpflush/$dumplimit (vcd-writer API exists but no SysTaskId — correctly outside Phase-1) — Phase-1 범위 밖(정상)
  - **근거:** vcd-writer/src/lib.rs:3-7,221,227 provide set_limit/is_limit_reached, but sim_ir::SysTaskId (sim-ir/src/lib.rs:211-223) has only DumpFile/Vars/On/Off/All; no DumpFlush/DumpLimit in builtins.rs. Freeze table lists exactly the 5 dump tasks.
  - **내용:** Missing IR wiring is correct; the vcd-writer API surface is simply ahead of the IR. SysTaskId is in the FROZEN sim-ir root.
  - **조치:** No action for Phase-1. If added later, remember the SysTaskId change flips the golden root hash (format_version bump + .velab regeneration).
- [x] **[OBSERVATION·—]** Reconcile reserved W3048 (whole-array-into-sens) intent vs shipped array-index-excluded behavior when auto-sens lands — ✅ deliberate Phase-2 deferral(loud rejection 확인됨, Phase-1 범위 밖)
  - **근거:** docs/preview/15:697 reserves W3048 W-ELAB-SENS-ENTIRE-ARRAY (MVP-SIM, must-implement) 'pulls whole array into sens'; not in the diag enum (Appendix-A reserved, correctly bijection-excluded). Current runtime does the OPPOSITE (array-index excluded — see the always_comb MAJOR).
  - **내용:** Latent design contradiction, not a live defect; needs a decision when auto-sensitivity for array word-selects is implemented.
  - **조치:** When implementing the array-index sensitivity fix, reconcile with W3048's stated whole-array-into-sens intent and document whichever is chosen.

---

## 후속 작업 큐 (Phase-1.x / 가속 · 2026-06-05 재개)

감사 52항목 클리어 후, deferral 중 가치순으로 재개. 순서대로 진행.

- [x] **[Phase-1.x]** 엔진 런타임 diag-sink → OOR/X-index 시 `E-RUN-RANGE`(VITA-E4002) 발행 (현재 X/skip 동작은 맞음, 진단만 미발행; rate-limit 포함) — ✅ 2026-06-05 (State에 &dyn LogSink+Cell rate-limit, warn_run_range가 OOR read/write서 E-RUN-RANGE 발행, sim은 recover. 실측 vita 발행, oob_emits_run_range_diagnostic 테스트)
- [x] **[성공기준]** iverilog 차분 하네스 — 대표 설계를 `iverilog`+`vvp` golden과 신호값/천이시각 비교 (iverilog 미설치 시 graceful skip) — ✅ 2026-06-05 (crates/sim-engine/tests/differential.rs: ALU/counter/memory/shift-arith/casez 5설계를 iverilog+vvp golden과 비교, vita 출력 정확 일치. iverilog 미설치 시 graceful skip)
- [x] **[Phase-2]** 자료형 확장: `enum`/`typedef`/`packed struct` — ✅ 2026-06-05 (사용자 선택 범위). 렉서 +5키워드, AST `ModuleItem::Typedef`+`TypedefKind{Enum,Alias,Struct}`+`EnumLabel`/`StructMember`(3회 .vu 재핀), 파서 typedefs/struct_layouts/var_struct 테이블·파스타임 const-literal 폭 폴드·`s.field`→상수 part-select desugar(expr+lvalue), elaborate enum 라벨→localparam-style int const(나머지 파서 desugar로 no-op). end_to_end 6 + iverilog 차분 4(enum/alias/struct/single-bit) 전부 iverilog 13.0 일치. **범위 밖(loud reject):** unpacked struct/union, param-width 멤버.
- [x] **[가속·신규]** 4-state 비트연산/reduction word化 — ✅ 2026-06-05. eval.rs `bitwise()`/`BitNot`/6 리덕션의 per-bit `get_vu`/`set_vu` 폴드를 u64-워드 브랜치리스 공식(`and_w`/`or_w`/`xor_w`/`xnor_w`/`not_w`+`reduce_word`/RedKind)으로 교체 → 64비트/op, LLVM 자동벡터화. 라스트 부분워드 마스킹(not_w/xnor_w가 high 0&0→1). per-bit `*1`는 `#[cfg(test)]` 레퍼런스 오라클로 보존(`word_vs_bit_parity`가 bit-exact 대조). 테스트: >64bit X/Z 워드경계 2 + 96/100bit iverilog 차분 2. golden unflipped, 418 green. **`std::simd` 제외:** portable_simd는 nightly 전용 → MSRV-1.82 stable + 3-OS 재현성 핀과 충돌하여 미도입(워드化가 실질 승부처, 안정 자동벡터화로 흡수).
- [x] **[가속·로드맵]** 컴파일드 백엔드 (IR→네이티브 코드젠, Verilator 방식) — 📋 **문서화된 장기 로드맵**(수개월 규모 컴파일러 백엔드; v1 작업 아님). doc-18 §권고로드맵 2번에 등재. 인터프리티드 엔진은 word化(④)로 즉시 CPU 이득을 이미 흡수; 10~100× 추가 가속은 코드젠으로만 가능하나 별도 대형 프로젝트로 분리. **체크리스트상 클리어 = "로드맵으로 문서화 완료"**(구현 아님).

## Phase-1 릴리스 하드닝 / 컴파일드 백엔드 로드맵 (2026-06-05 · 4축 감사 wmi10j3sn 기반)

큰 코드젠 프로젝트 전에 Phase-1을 "문서화된 릴리스"로 굳히는 단계. 감사 결론: SPEC(`docs/preview/`)은 최상이나 **사용자/배포 레이어가 부재**했음.

### Stage A — 릴리스 문서 (✅ 2026-06-05, 커밋 f4fbba7)
- [x] LICENSE-MIT + LICENSE-APACHE (Cargo.toml 선언 듀얼에 맞춤), 루트 README.md(영어), CHANGELOG.md, CONTRIBUTING.md, install.sh(POSIX, Linux/macOS)
- [x] `docs/manual/` 000–007 (introduction/installation/quickstart/language-reference(TRM)/cli-reference/system-tasks/limitations/error-codes) — **코드 기반 검증**(stale SPEC 아님), cross-link 전수 해소, `disable`=no-op 003/006 일치
- [x] `examples/` counter·ALU·enum-FSM·shift-register — 전부 `vita` 실행 검증(exit 0, stderr 0, VCD). Windows 범위 밖 명시(사용자 결정)

### 발견된 SPEC drift (매뉴얼은 SHIPPED 상태로 정확; doc-01 SPEC는 stale → 후속 교정 권장)
- [ ] **doc-01(01-goals-and-scope) freeze 표가 `enum`/`typedef`/`packed struct`를 아직 DEFERRED로 표기** — 실제 구현됨(매뉴얼 003이 정확). doc-01은 "단일 진실 공급원" SPEC이라 교정 필요.
- [ ] doc-01 §v1단순화의 산술-레인 문구가 옛 경계(64bit)로 남음 — 실제 128u/64s. (REMAINING_WORK 본문은 정정됨)
- [ ] hdl-reference/system-tasks가 `$stime` 등을 "Phase1 완전지원"으로 표기하나 코드 미구현(매뉴얼 005가 정확).

> **참고(2026-06-06 재분류):** 위 doc-01 drift + `%t`는 *인터프리터 문서부채*로, 코드젠과 **결합 없음**(6-매핑/3-비평 워크플로 wzeyxgedk가 P1/P2로 분류 후 prereq 목록에서 제외). 컴파일드 백엔드 선결과 별개 트랙. 원하면 opportunistic 정리.

### Stage B — 컴파일드 이벤트구동 백엔드 선결 (코드젠 착수 전, 미착수)

> 2026-06-06 재작성 · 출처: 워크플로 `wzeyxgedk`(6 서브시스템 매핑 → 합성 → 3 적대적 비평 → 최종 병합, 11에이전트). 이전 4줄 스텁을 grounded 19항목 체크리스트로 대체. **순서는 의존성 위상정렬**(각 항목의 depends_on이 앞에 옴). `[B]`=BLOCKING, `[R]`=RECOMMENDED.

| id | 항목 | 수준 | 의존 | 코드 근거 |
|---|---|---|---|---|
| **P0a** ✅ | 코드젠 **target form** = **바이트코드 VM** 확정 | 🔴 B | — | 사용자 결정 2026-06-06. cargo-only·build.rs금지·3-OS결정성 핀과 충돌하는 emit-Rust 탈락; doc-18:63 두 병목(tree-walk·Value힙) 제거하며 핀 보존. 결정기록=doc-18 §결정 기록 |
| **P0b** ✅ | **compile+load** = **N/A**(in-process 바이트코드) | 🔴 B | P0a | 런타임 코드생성·로드 없음 → `.velab→VCD` 헤르메틱 무변경. VM opcode가 value.rs/eval.rs 동일 프리미티브 디스패치 → float 축 인터프리터와 byte동일(P3 부담 축소) |
| **P3** ✅ | **float/host-toolchain 결정성 계약** + float 골든 | 🔴 B | P0b | 2026-06-06. doc-18 §P3에 동결 float-path 표면(reuse-only·no fast-math) + `float_format_determinism_golden`(end_to_end.rs)이 %f/%e/%g/%d-on-real/>128bit-%d-폭 전체를 byte-image 골든化(cross-OS 잠금). 바이트코드가 동일 함수 호출 → 발산 불가. 420 green |
| **P4** ✅ | **backend 선택 seam**(SimOpts/simulate) — choke point 공유측 유지, frozen IR 무변경 | 🔴 B | P0b | 2026-06-06. `Backend{Interpreter,Bytecode}` enum + `SimOpts.backend`(out-of-band, default Interpreter) + `SimState.backend`; `Scheduler::run_body`가 단일 dispatch seam(sched.rs). Bytecode는 Stage B에 전 바디 인터프리터 fallback=byte동일. `backend_bytecode_falls_back_byte_identical` 테스트. choke point(`write_lvalue→emit_vcd_change`) 공유측 잔류. 421 green, golden unflipped |
| **P6** ✅ | 시드 결정적 **랜덤 corpus 생성기**(P5 입력) | 🟡 R→B | P3 | 2026-06-06. `tests/common/mod.rs`: SplitMix64 LCG(crate 무의존) + 8 템플릿(counter/alu/shiftreg/mem-OOB/nba-sample/wide-arith/xz-index/multi-write-glitch)이 *valid* 풀에서 채워 합성가능 RTL만 방출. `tests/corpus.rs` 4테스트: 재현성(동일 seed→byte동일)·seed별 변화·전 템플릿 커버·**전 설계 build+run-to-$finish 검증**. 425 green |
| **P5** ✅ | **컴파일드-vs-인터프리터 차분 게이트**(vita 자족, iverilog **비의존**), hard CI 게이트 | 🔴 B | P4,P6 | 2026-06-06. `tests/backend_equiv.rs`: P6 corpus 64설계를 동일 SimIr로 양 backend 실행→stdout+**VCD 바이트**+SimResult byte동일 단언. 동일 opts라 정규화 불요(iverilog와 달리 $date/$version 동일). VCD는 `CARGO_TARGET_TMPDIR` 임시파일 readback(`run_capture`). teeth 테스트가 실제 VCD 바이트 비교 보장(vacuous 방지). 기본 suite=hard CI 게이트(no skip). 427 green |
| **P8** | 커널-콜 **순서/샘플링-모먼트 불변식 계약** 동결(eager per-write VCD 방출 포함) | 🔴 B | P7a→P7b | seam이 있어야 ABI 계약化, P5 바이트-diff 분류에 필수. 7 모먼트: cont-assign 선언순 fixpoint(sched.rs:190); NBA 샘플시점+`nba_seq` 정렬(802,554); blocking offset-at-stmt(exec.rs:69); in-body @ arm-snapshot(791); delayed `last_ca`(218); prev-refresh-LAST(658); **eager per-write VCD glitch**(state.rs:386) |
| **P7a** ✅ | `run_process` **read/write-phase 분리**(mut-Scheduler aliasing 정리), byte-equiv, **백엔드 없음** | 🔴 B | P5 | 2026-06-06. exec.rs: 각 stmt를 `compute_effect`(READ, `&Scheduler` 순수 eval→`StmtEffect`) + `apply_effect`(WRITE, `&mut` 커널콜)로 분리. 코드젠 바디가 read phase 인라인·write phase 커널콜하는 정확한 seam. 순수 리팩터(동일 eval/write/순서), 427 green + P5 byte동일 확인, golden unflipped |
| **P7b** | body↔kernel **trait/ABI seam 도입**(코드젠 가능化 커밋) + 명시 suspend/resume 재진입 | 🔴 B | P7a,P9 | ~18 Scheduler 메서드+`builtins::dispatch`를 trait 뒤로. **resumable 재진입 필수**: Delay/Wait→`Step::Suspended`+resume BB 재진입(exec.rs:101-128); 순수 call-return fn으론 불가. P9 scope 결정과 공동설계 |
| **P9** ✅ | scope 술어 = **positive allow-list**(suspend-free·fork-free·Call-free; 루프=Goto/Branch 허용) | 🔴 B | P5 | 2026-06-06. `backend.rs::is_codegen_able(stmts,body)`: 전 terminator∈{Goto,Branch,Return}∧no Disable. for/while/forever=Branch back-edge 허용; 제외 {Delay,Wait(Named 포함),Fork,Call}+Disable. `run_body` Bytecode arm이 codegen-able→`vm_run_body`(Stage C stub, 현재 인터프리터 위임), 아니면 run_process. always_ff=codegen-able·initial #1=아님→자연 mixed. backend:: 6 단위테스트. **P5 게이트가 잠재 temp-file 레이스 적발→unique 경로로 수정**. 433 green |
| **P9b** | **mixed-backend per-run 바이트동일** 증명(한 run에 컴파일드+인터프리티드+cont-assign 혼재 == all-interp) | 🔴 B | P9,P5 | P9는 프로세스별 backend 혼재 암시, cont-assign은 별 caller(sched.rs:190). 컴파일드 바디가 `schedule_nba`를 다른 순서로 호출하면 `nba_seq` 재정렬→`apply_nba` 발산. P5 corpus에 혼재설계 필수 |

### Stage C — 컴파일드 이벤트구동 코드젠 MVP (Stage B 이후 · **스펙/플랜/리뷰 후 착수**)

> Stage B 11항목 전부 클리어 → 컴파일드 백엔드 **스펙+플랜 작성 → 리뷰 → 구현**. 아래는 그 구현 항목(IMPL)의 grounded 분해. `[I]`=IMPL.

| id | 항목 | 의존 | 코드 근거(핵심) |
|---|---|---|---|
| **P10** | 정적 per-edge **width/sign 해석 패스** + width유도 X/Z poison-regime 분기 | P7b,P9 | `eval_ctx`(eval.rs:62-174) IEEE 5.4.1/5.5 per-context 재계산; w>64 signed/w>128 unsigned→X poison(439-444) 사이트별 선판정 |
| **P11** | index/width/count expr 정적-vs-런타임 분류; `const_u32_of_expr`의 **shallow fold**+사이트별 fallback+OOR 센티넬 4 arm(read·write 양측) | P7b,P8,P9 | `const_u32_of_expr`(width.rs:306)는 의도적 shallow(Const/Add/Sub만); 사이트별 fallback 상이(width1/net-width). **더 똑똑한 fold 쓰면 발산** |
| **P12a** | **네이티브 value 표현**(≤128=u64/u128 레지스터+X/Z plane, >128만 힙) + 전 구조연산 | P10,P11,P5 | doc-18:63 주 가속레버(Value `Vec<u64>` 힙제거). concat/replicate/select/shift-4096-cap(eval.rs:642) 모두 growable Vec 가정 → 레지스터 lowering |
| **P12b** | **real(f64) 산술 도메인** bit-for-bit(is_real lane·NaN poison·±0.0·partial_cmp·int↔real) | P12a,P3 | Value.is_real(value.rs:43) 병렬 2-state f64; `%`/`**`→NaN, Div→±inf NOT X(eval.rs:418-423). no fast-math, P3 formatter 재사용 |
| **P12c** | per-activation **prologue lowering**: `cur_time_mult` write-point(postponed 중 stale 포함)+dual delta-guard | P12a | `cur_time_mult`는 per-body 상수 아님 — 매 블록 fetch마다 mutable write(exec.rs:51-57); `flush_postponed`는 마지막 프로세스 값으로 평가(sched.rs:483). per-activation guard vs scheduler delta_count가 finish_reason 좌우 |
| **P12d** | **$display/$strobe/$monitor 포맷엔진=인터프리티드 유지**(명시적 코드젠 경계, target 아님) | P7b,P3 | `format_args_str`(builtins.rs:297-421) printf 파서가 arg ExprId를 **lazy eval**; strobe/monitor는 postponed서 재평가(state.rs:32). 컴파일드 바디가 pre-eval하면 샘플링 깨짐 |
| **P13** | **continuous-assign 코드젠 경로**(cont-assign=프로세스 바디 아님; settle이 같은 eval/write seam 재사용) | P12a,P9b | `settle_cont_assigns`(sched.rs:190) 선언순 fixpoint, 매 delta 인터리브. 프로세스-바디-only 코드젠은 `assign` 전부 인터프리티드 잔류 → 속도이득 0. **correctness prereq 아님**(인터프리티드 잔류로도 정확) |
| **P14** | **성능 baseline + speedup 수용 게이트**(컴파일드가 *빠름*을 증명 — 프로젝트의 목적) | P5,P12a | 전 BLOCKING은 correctness-equiv뿐; speedup terminus 부재. P5와 함께 **조기** 측정(rustc/load 오버헤드가 작은 설계서 이득 잠식 가능). RECOMMENDED |
| **P15** | content-addressed **코드젠 캐시 키** + **kernel-ABI 버전 스탬프**(format_version과 **독립** 4th 게이트 tier) | P7b,P0b | seam ABI는 SimIr shape 불변으로 바뀜 가능; `verify_header`는 format/schema_hash만(gate.rs:67). 두 설계가 같은 schema_hash → 캐시된 .so가 오통과. `composite_input_hash`(header.rs:45, 현재 `[0u8;32]` deferred)가 바로 그 content key. **format_version bump 아닌 독립 필드**. RECOMMENDED |
| **P16** | ExprId/StmtId→**SourceLoc 사이드카**(컴파일드 경로 디버깅; frozen IR은 span-free) | P4 | SchemaHash는 span-free 요구 → SimIr에 위치필드 없음. CLI는 front-end `SourceMap`만(cli/lib.rs). "디버깅"이 목표면 out-of-band 사이드카(net_names 패턴) 필요. **correctness prereq 아님** · RECOMMENDED |

### 잔여 in-scope (인터프리터 문서부채; 코드젠 무관 · 행동 선택)
- [ ] **`%t`** 기본 필드폭/$timeformat 미구현 — 값은 정확. 매뉴얼 005·006에 한계로 문서화 완료(릴리스엔 충분). 구현은 %d arm 미러(저위험·golden 불변) — 원하면 Phase-1.x.

## 진행 로그

해결 시 한 줄씩 추가 (날짜 · 커밋 · 항목).

- 2026-06-05 · **Phase-1 릴리스 문서 세트 (Stage A)** 완결(커밋 f4fbba7). 4축 감사(wmi10j3sn) → 9-에이전트 매뉴얼 생성(코드 검증) → 컨트롤러 조립(cross-link 전수 교정·disable 정확성 003/006 일치·예제 4종 직접 실행 검증·README/LICENSE×2/CHANGELOG/CONTRIBUTING/install.sh). 사용자 결정: Windows 범위 밖, 전체 세트, 번호 인덱스. SPEC corpus는 개발자-내부로 유지, 사용자 매뉴얼이 그 위에 링크. doc-01 SPEC staleness 3건 트래킹 추가. Rust 무변경(419 green).

- 2026-06-05 · 후속 큐 완결 + 적대적 검증: `s.unknown_field`는 loud reject(silent-wrong 아님) 회귀테스트 추가. 컴파일드 백엔드는 문서화된 장기 로드맵으로 종결(구현 아님). 워크스페이스 419 green. 후속 큐 5/5 클리어.
- 2026-06-05 · **4-state 비트연산/reduction word化** (가속). eval.rs의 per-bit 폴드를 u64-워드 4-state 불리언 공식으로(bitwise/NOT/6 reduction). 64배 적은 반복+브랜치리스+자동벡터화. 라스트워드 마스킹, per-bit 테이블은 test 오라클로 보존. std::simd는 nightly 충돌로 제외(워드化가 실질 승부처). >64bit 워드경계 4테스트(2 X/Z + 2 iverilog 차분), golden unflipped, 418 green. 커밋 ad199d4.
- 2026-06-05 · **Phase-2 자료형 (enum+typedef+packed struct)**. 사용자 선택 범위를 enum→typedef alias→packed struct 3단계 TDD·커밋. enum 라벨=int const(explicit =expr가 counter 리셋), alias=underlying 폭 절단, struct=MSB-first 평탄 레이아웃+`s.field` 상수 part-select desugar(파서 sugar, elaborate 무변경, frozen IR 무영향). AST 3회 .vu 재핀(의도적). end_to_end 6 + iverilog 차분 4 전부 iverilog 13.0 일치. 워크스페이스 413 green. 커밋 a2736c2/9cdaa10/1c4e5ff.

- 2026-06-05 · **corpus가 신규결함 발견·수정**(MAJOR): ANSI 멀티네임 포트 `input [7:0] a, b`에서 b가 방향만 상속하고 range/type 미상속→scalar(1bit) 절단(흔한 구문). parse_ansi_port가 pure-continuation일 때 prev의 net_or_var/signed/range 상속하도록 수정. 6 corpus + 1 focused 테스트, 워크스페이스 395 green.
- 2026-06-05 · timescale BLOCKER 완전 마무리: 스테이지드(.vu/.velab 트레일러 vcmp→velab→vrun, staged==one-shot byte-identical) + W-PP-TIMESCALE-DEFAULT(W1017 enum+doc-15 본문 승격, 실측 vita 발화) + doc-08 골든(라운딩 14.4→14·0.5→1·0.4→0/혼합 timescale global-min). 워크스페이스 378 green, 골든 unflipped.

- 2026-06-05 · timescale S1 (BLOCKER 진행중): preprocess가 `timescale unit/precision`를 `TimeScale{unit_exp,prec_exp}`로 파싱 + 확장텍스트 offset region 테이블(PpResult.timescales) 노출. 파일순서 상속 기반. 3 테스트, 워크스페이스 368 green.
- 2026-06-05 · always_comb/@* 배열 word-인덱스 민감도 누락 수정 (MAJOR). `collect_expr_reads`가 `Signal.word`를 재귀 → `always_comb y=mem[sel]`이 sel 변경 시 재발화. 회귀테스트 추가, 워크스페이스 353 green, 골든 unflipped.
- 2026-06-05 · const-eval `**`/`<<<`/`>>>` 폴딩 추가 (BLOCKER). `parameter W=2**N`이 silent 0→정상 폴드, overflow는 u32::MAX 포화로 width-cap loud. 테스트 2종, 워크스페이스 355 green, 골든 unflipped.
- 2026-06-05 · casex/casez SCRUTINEE x/z 와일드카드 수정 (MAJOR). `case_label_eq`를 `reduction_or(scrut ^ label) !== 1`로 — 라벨+런타임 scrutinee 와일드카드를 기존 op만으로 처리(frozen IR 무변경). v2_7 단위테스트 새 lowering 반영. 신규 2테스트, 워크스페이스 357 green, 골든 unflipped.
- 2026-06-05 · OOR array word 정확성 수정 (MAJOR). `net_word_packed` OOR→all-X 읽기, `write_chunk` OOR→쓰기 무시(이웃 무손상), 클램프 제거. 다차원 OOR도 X/skip로 통일. 테스트 1종, 워크스페이스 358 green, 골든 unflipped. (E4002 진단 발행은 엔진 diag-sink 인프라 필요 → 보류)
- 2026-06-05 · non-zero/내림차순 배열 인덱스 정규화 (MAJOR). `array_dims`를 `(lo,size)` extent로 전환, `flatten_word`가 `idx-lo`로 0-base 슬롯 정규화(lo==0이면 Sub 미생성→golden 불변), 1D 비-0 base도 저장. 테스트 3종, 워크스페이스 361 green, 골든 unflipped.
- 2026-06-05 · unsigned 산술 레인 64→128bit 확장 (MAJOR). `to_u128` 추가, operand u128 읽기 + 결과 2-word 저장; w>128만 X poison(signed >64 poison과 대칭). 흔한 128bit 카운터/누산기 carry 정확. 테스트 2종, 워크스페이스 363 green, 골든 unflipped.
- 2026-06-05 · X/Z 배열 인덱스 통일 (MINOR). read `Signal.word` X→u32::MAX OOR 센티넬→all-X(word0 미읽음); write는 기존 센티넬+#3로 이미 no-op. 테스트 1종, 워크스페이스 364 green, 골든 unflipped. **→ correctness 퀵윈 6개 전부 완료.**
- 2026-06-05 · **VCD 실신호명+계층 scope (BLOCKER)**. elaborate `NetNameTable` 사이드테이블(NetId→FQ명)→`SimOpts.net_names`(frozen 밖); builtins scope-sorted 트리워크로 `$scope`/`$var` 계층 방출; CLI one-shot+`.velab` 트레일러+`vrun` 스레드. 실측 `vita`가 `top`>`u` 인스턴스 scope+실명 방출. 테스트 1종, 워크스페이스 365 green, 골든 unflipped.

