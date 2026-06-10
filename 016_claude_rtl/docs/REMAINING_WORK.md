# vitamin — 잔여 작업 트래커 (Remaining Work)

> **리뉴얼: 2026-06-10** · 기준 HEAD `b3651fa` + elaborate shift fix(uncommitted, Gemini) · **460 tests green** · clippy/fmt clean · golden(SimIr) unflipped(format_version 3).
> 출처: 7축 감사 — ①Gemini-fix 검토 ②spec-gap ③sim-engine ④front-end ⑤메모리/자원 ⑥운용성 ⑦병렬화. 핵심 항목은 라이브 재현(+iverilog 차분)으로 확정, 각 항목에 `재현:` 표기.
> 이전 트래커(2026-06-05 생성: 감사52 + Stage A/B/C 이력)는 **전항목 완결로 아카이브** — 이 파일의 git 이력(`b3651fa` 시점 버전) · perf 시계열 = [doc-18 §실측](preview/18-acceleration-analysis.md) · 전략 = [ROADMAP](ROADMAP.md). 요약은 맨 아래 §아카이브.
> 미해결 `- [ ]` / 해결 `- [x]` + 커밋·날짜. 우선순위: **P0**(silent-wrong 정확성) > **P1**(시뮬 의미론: warn-후-오동작) > **P2**(운용/CLI/진단) > **P3**(메모리/장기 안정) > **P4**(병렬화·신규 트랙) > **P5**(문서부채).

## Gemini shift fix 검토 결과 (2026-06-10 · 채택)

`const_eval_in_scope`의 `wrapping_shl/shr` → `checked_shl/shr().unwrap_or(0)` (elaborate/src/lib.rs:1379-1382):

- ✅ **채택** — Rust `wrapping_shl`이 shift량을 mod 32로 마스킹해 `1<<32`→1이 되던 함정 제거는 옳다. 460 green·clippy 무영향·골든 무영향, 4개 arm 통합도 무해.
- ⚠️ 단, gemini_debug.md의 근거 서술 2건은 부정확: ①"중복 매치 암 제거" = **오진**(제거된 것은 별개 variant `AShl/AShr`; 진짜 중복이면 clippy `-D warnings` 게이트가 이미 실패했음) ②"0이 정답" = 32bit-exact 해석에서만 참 — **차분 오라클 iverilog는 `1<<32`=4294967296**(unsized 상수를 >32bit로 폴딩)이고, `parameter [63:0] F = 1<<32`는 IEEE 컨텍스트 확장상 2^32가 명백 정답(vita 0, 수정 전 1 — 둘 다 오답). 근본 해소 = P0-6.

## P0 — 정확성: silent-wrong-value (최우선)

**런타임 >64bit 절단 클러스터** — 공통 근원: `Value::to_u64`(value.rs:313-320)가 width>64에서 None 대신 word0 절단값을 반환.

- [ ] **[P0-1]** >64bit relational 비교 절단 — eval.rs:537이 `to_u64`(arith는 이미 `to_u128`, relational만 누락). **재현:** `128'h1_0000_0000_0000_0000 > 128'h1` → vita `0` / iverilog `1`.
- [ ] **[P0-2]** shift-amount 절단 — eval.rs:630·648. amt 피연산자의 상위 word 무시 → `2^64`만큼 shift가 no-shift로. `to_u128`+width 클램프.
- [ ] **[P0-3]** unary minus(negate) 단일워드 — eval.rs:266-281. `-128'h1`의 word1이 0 (`128'h0 - x` arith 경로와 결과 불일치).
- [ ] **[P0-4]** **`to_u64` 계약 수정**(overflow→None) + 호출부 10곳 전수 감사 — eval.rs:85·731(part-select offset, 동일 절단 클래스)·816 / sched.rs:771(signal발 #delay) / value.rs:340(`to_i128_signed` — signed >64 비교에도 절단 유입)·528(real cast) / builtins.rs:623(%c, 무해).

**elaborate 상수 도메인 클러스터:**

- [ ] **[P0-5]** 폴딩 불가 param/localparam/enum-label → **silent 0** — lib.rs:1239(`unwrap_or(0)`)·727·743·1622. `const_eval_in_scope`에 ternary `?:`/`$clog2`/concat/함수호출 arm 부재(:1384 `_=>None`). **재현:** `parameter W = MODE ? 16 : 8` → vita W=0 / iverilog 16, 진단 0줄. 조치: Cond·$clog2 폴딩 추가 + 그래도 미폴딩이면 **Error**(0 기본값 절대 금지 — 2026-06-05 BLOCKER#2에 적힌 미이행 조치).
- [ ] **[P0-6]** const 도메인 u32 → **부호 있는 i64+ 확대** — ①`1<<32`: vita 0 vs iverilog 4294967296 ②`parameter [63:0] F=1<<32` → 0(IEEE 컨텍스트 확장상 2^32) ③64bit 리터럴 param u32 절단(lib.rs:4521 `as u32`) ④signed AShr가 논리시프트(:1382, `(-4)>>>1`→0x7FFFFFFE) ⑤Mul wrapping(:1346 — Pow는 saturate, 비대칭). Gemini fix의 잔존 한계 해소(위 검토 결과 참조).
- [ ] **[P0-7]** 하강 generate-for 폭주 — unsigned u32 비교라 `i>=0` 항상 참 → GENERATE_UNROLL_CAP(4096) E3009. **재현:** `for(i=3; i>=0; i=i-1)` vita 에러 / iverilog 정상. loud지만 합법 IEEE 거부, 실사용 빈출 패턴. (P0-6에 포함 가능; 선행 단독 fix = 비교 연산만 signed)

**display/monitor 의미론:**

- [ ] **[P0-8]** `$display` 인자 의미론 3종 — ①선행 문자열 뒤 인자 유실: **재현:** `$display("val=", val)` → vita `val=` / iverilog `val=255`(IEEE 1364 §17.1: 잔여 인자를 기본 radix로 출력) ②bare-arg 자리 문자열 리터럴이 10진수로 출력 ③`%v/%u/%z/%p/%l`이 literal로 찍히며 **인자 미소비 → 후속 specifier 인자 시프트**. elaborate:4368-4377 + builtins.rs:301-425.
- [ ] **[P0-9]** `$monitor` 트리거 과민 — ①직접 `$time/$realtime` 인자도 변화 비교에 포함(sched.rs:586; IEEE §17.1.3은 제외 요구) ②last_vals 비교가 derived `PartialEq`(signed/is_real 메타 포함) — 비트평면(val/unk/width)만 비교로.

## P1 — 시뮬 의미론: warn-후-오동작 (정지·계속 클래스)

- [ ] **[P1-1]** `$fatal/$error/$warning/$info` = warn+no-op — **$fatal TB가 exit 0**(CI silent PASS). **재현:** vita는 W3008 경고 후 계속 실행·exit 0 / iverilog FATAL 출력·exit 1. 조치: SysTaskId 4종 추가(frozen IR 변경 → format_version bump 동반) or 단기 브리지: `$fatal`→Finish+error exit. cli/lib.rs:11 주석("runtime $fatal → exit 1")은 현재 거짓.
- [ ] **[P1-2]** `force/release` / procedural `assign/deassign` / `->event` = warn+no-op — 값 불변, `@(ev)` 영구 대기(lib.rs:4056-4062). `ElabUnsupported` 하드에러 승격(defparam :880과 일관) or 구현. ROADMAP §D "전부 loud-reject" 문구는 거짓이었음 → 이번 리뉴얼에서 정정.
- [ ] **[P1-3]** 비상수 `#delay` → `#0` 강등 — lib.rs:4310-4319(`unwrap_or_else(warn→0)`). `forever #x clk=~clk`가 delta-limit fatal로 변질. loud-reject로(런타임 delay는 frozen `Terminator::Delay{u32}` 형상 변경이라 Phase-2).
- [ ] **[P1-4]** in-body `@(*)` 영구 대기(`Level{nets:[]}`) + in-body 멀티엣지 `@(posedge a or posedge b)` 첫 항만 — lib.rs:4278-4295. 블록 헤더 형은 정상(read-set/EdgeTerm 기계 존재 — 재사용).
- [ ] **[P1-5]** `$displayb/o/h`·`$writeb/o/h` → 10진 alias(기수 무시·무진단, lib.rs:4463-4464) + `$monitorb/o/h`·`$strobeb/o/h` 미구현(:4465). doc(01-display-io.md:219)은 "16종 모두 Phase-1 구현" 주장. radix 사이드채널(out-of-band, fork_modes 패턴) or doc 강등.
- [ ] **[P1-6]** `$finish` 동일 타임스텝의 postponed `$strobe/$monitor` 유실 — sched.rs:402-404가 flush(:454) 전 반환. end_to_end.rs:943에 "의도적 MVP 분기"로 박제 — iverilog 정합(flush 후 종료)으로 전환 권장.
- [ ] **[P1-7]** `fork_mode()` panic — staged `.velab`의 빈/불일치 ForkModeTable trailer(스키마 게이트 밖)로 사용자 도달 가능(sched.rs:915-924). E-code Fatal 진단으로 전환.
- [ ] **[P1-8]** 멀티드라이버 검출 = whole-net cont-assign 한정 — part/bit-select 드라이버 미계상(lib.rs:1412-1424). 충돌 시 IEEE x-resolution 아닌 last-write-wins/델타 폭주. per-bit 구간 계상 or doc-01 v1 단순화 표 등재.
- [ ] **[P1-9]** net-vs-variable 대입 적법성 미검사 — `always`에서 wire 대입·`assign`으로 reg 구동 둘 다 수용(iverilog 거부, doc-02는 에러로 기술). NetKind 검사 2건.

## P2 — 운용/CLI/진단 견고성

**silent-failure 군집:**

- [ ] **[P2-1]** VCD open 실패 완전 침묵 — builtins.rs:116-119 `Err(_) => return`. **재현:** unwritable 경로 → exit 0·진단 0줄·VCD 없음(주 산출물 무단 증발). 최소 Warning 진단.
- [ ] **[P2-2]** VCD write/flush 에러 침묵 — state.rs:489-490·511 `let _ =`. 최소 `finalize_vcd`의 flush 결과는 진단으로.
- [ ] **[P2-3]** delta-limit 도달 시 진단 0줄(exit 1만) — `RunDeltaLimit`류 Fatal 진단 발행.
- [ ] **[P2-4]** `--help`/`--version` 부재 — **재현:** `vita --help` → `cannot read '--help'`(파일로 해석). 첫인상 UX.

**안전 레일:**

- [ ] **[P2-5]** parser 재귀 깊이 가드 부재 — 깊은 중첩식(`(((…)))` 수천 단)에 stack overflow(SIGSEGV, 진단 불능). depth cap(~512)+진단. (elaborate generate는 DEPTH_CAP=32 보유, parser만 무방비)
- [ ] **[P2-6]** unpacked `array_len` cap 부재 — `reg [7:0] m [0:2147483647]` 즉시 수GB alloc → OS OOM kill. `MAX_NET_WIDTH`(1<<20)처럼 `MAX_ARRAY_LEN`+ElabUnsupported.
- [ ] **[P2-7]** 아티팩트 `.vu/.velab` 비원자적 쓰기 — cli/lib.rs:617·703 `fs::write`. 크래시 시 부분 파일을 게이트가 format-mismatch로 혼란 보고. temp+rename(+"재생성" 안내 진단).
- [ ] **[P2-8]** native_eval `lower()`가 eid를 무검사 인덱싱 — 같은-schema 손상 `.velab` 방어로 `exprs.get()`+None fallback(native_eval.rs).
- [ ] **[P2-9]** `--timeout`/기본 time_limit 부재 — `always #1;`가 무한 진행(SimOpts.time_limit 기본 None). CI용 킬스위치 옵션.

**진단 taxonomy/계약:**

- [ ] **[P2-10]** elaborate 범용 `warn()`이 전부 `W-ELAB-WIDTH-TRUNC` 코드 — lib.rs:578-580(미지원-task skip·force no-op·dup-module·unconnected port까지 전부). doc-15 bijection·suppress 라우팅 파괴. 정확한 MsgCode 부여.
- [ ] **[P2-11]** dead MsgCodes ~10종(DupUnit·ParseImplicitNet·ElabUser\*·RunAssertFail·RunUser\*·RunFatal·RunNoLocations·LintUnclosed) + 중복 모듈 정의=warn(doc-15 `E-DUP-UNIT`는 Error) + `%m` 항상 `top`(builtins.rs:371; NetNameTable 패턴으로 FQ 경로 배선) + exit class 2 문서 불일치(실제 0/1/3) — P1-1과 묶어 정리.
- [ ] **[P2-12]** 정책 결정 소항목 묶음 — `$finish(n)/$stop(n)` 인자 무시(doc은 "처리 포함" 주장) · `timescale_unit_string` 범위외 silent "s"(cli:302-310) · `time` 타입 E3009 거부(64bit unsigned 수용 trivial) · `` `pragma`` "undefined macro" 거부(수용-무시로) · implicit net 항상-strict(E3010; W2003 dead) 정책 명문화 · `same_path` 문자열 비교(canonicalize로).

## P3 — 메모리/장기 시뮬 안정성

- [ ] **[P3-1]** fork `activities`/`barriers` 아레나 append-only 무한 성장 — sched.rs:979·997. `forever fork…join_none` 패턴에서 O(타임스텝) 누적(10M cycle×2child ≈ 800MB). 타임스텝 경계 컴팩션/epoch 재사용.
- [ ] **[P3-2]** `$monitor` last_vals 매 스텝 Vec 재할당 — sched.rs:586·600. in-place 재사용.
- [ ] **[P3-3]** VCD sink **BufWriter 부재** — builtins.rs:120이 raw `File`을 직접 Box → VCD 레코드당 ~1 write syscall. **P4-T0b와 동일 항목**(1줄 fix + dump-heavy perf 측정 추가).
- [ ] **[P3-4]** `net_to_edge[n].clone()` per changed-net per delta — sched.rs:657(borrow 회피용). 인덱스 루프화.
- [ ] **[P3-5]** native_eval `run()` per-call 스택 Vec — native_eval.rs:213. SimState scratch/SmallVec화.
- [x] **[P3-기록] 종료/메모리 위생 양호 판정 (2026-06-10 감사)** — `unsafe` 0건 · Rc 9곳(vm_cache 한정) 비순환 · `finalize_vcd` 전 종료경로(정상/$finish/$stop/delta-limit/error) 호출 · HashMap 3곳(vcd by_id·parser typedefs 등) lookup-only로 결정성 무해 · BTree-only 스케줄러 재확인. Ctrl-C 핸들러 없음 = 커널 fd flush로 마지막 완료 write까지 유효한 truncated VCD(문서화만 권장). CLI 종료 시 미해제 누수 없음(정상 Drop + OS 회수). 라이브러리 임베딩 시 재평가.

## P4 — 병렬화 트랙 (신규 · 2026-06-10)

**현황:** 프로덕션 코드 스레딩 0(std::thread/rayon/Arc/Mutex 부재), 기존 계획 0 — doc-18:19가 PDES를 "결정성(3-OS byte-identical)과 상충·장기"로 박제했을 뿐, `--threads`류 옵션 구상 부재. 엔진은 의도적 단일스레드(`!Send`인 `Box<dyn Write>`/`LogSink`/`Cell`)이나 Rc는 9곳(vm_cache)으로 얕고, `simulate(&SimIr)`은 불변 입력의 순수 함수 — **스레드/프로세스당 1 시뮬은 이미 자유**.

**옵션/UX 설계(확정안):**
- `--threads N`(alias `-j N`) — `vita`/`vrun`에 추가(vcmp/velab은 당장 대상 없음). 기본 `auto` = `min(available_parallelism, 8)`(std, MSRV 1.82 OK, 신규 dep 0). env `VITA_THREADS`(플래그 우선). `--threads 1` = 현행과 완전 동일 경로.
- **계약: 모든 N·모든 OS에서 VCD/stdout/아티팩트/exit code byte-identical** — thread 수는 wall-clock만 바꾼다. corpus를 `--threads 1` vs `4`로 byte-diff하는 P5식 차분 게이트로 강제. 구현은 `SimOpts` out-of-band(frozen IR·골든 무영향).

| 단계 | 내용 | 기대효과 | 결정성 리스크 | 공수 |
|---|---|---|---|---|
| ⬜ **T0a** | multi-run 병렬: P5 `backend_equiv`가 interp·VM을 `thread::scope` 동시 실행 + Send-가능 capture sink | 차분 스위트 ~2x, run 수에 선형 | 0 | 시간 |
| ⬜ **T0b** | VCD `BufWriter`(=P3-3) + `perf_baseline.rs`에 dump-heavy 케이스(현재 VCD 비중 **미측정**) | 측정 후 판단(현 1 syscall/record) | 0 | 시간 |
| ⬜ **T1** | `--threads ≥2`: VCD 전용 writer 스레드 — 인코딩·`$dumplimit` byte-카운팅은 producer측 유지, bounded FIFO(순서=byte 보존), `$dumpflush`/finalize는 block-drain | T0b 측정 VCD I/O 비중에 비례(30%→≤1.43x, 50%→≤2x) | 低 | 일 |
| ⬜ **T2** | front-end per-compilation-unit 병렬 — 현 다중파일은 의도적 단일 연결(`` `define`` 순서 의존)이라 SV `-u` 의미론 결정 선행 | 小(front-end는 ms 스케일) | 中 | 보류 |
| ✕ **T3** | parallel elaborate — **비추천**: 전역 arena ID 순서 자체가 골든 계약, byte-identical 재현 머지 비용 高 | 小 | **高** | — |
| 🔬 **T4** | 엔진 내 PDES/정적 파티셔닝 — 연구 트랙 유지(doc-18 판정대로). Verilator `--threads`는 cycle-based 정적 파티셔닝+배리어라 가능; 이벤트구동+tie 순서+eager VCD에는 부적합, Icarus도 미지원 | 설계 의존 | 最高 | 연구 |

## P5 — 문서부채 (docs ↔ code 불일치)

- [ ] 01-display-io.md:11·219("b/o/h 16종 Phase-1 구현")·:46(`$display("val=",val)` → `val=255` 예시) — P0-8/P1-5 해소 전까지 실태 명기.
- [ ] ROADMAP §D "의도적 deferral 전부 loud-reject 확인됨" → **거짓**(force/release/->ev/disable=warn+no-op, 비상수 delay→#0) — ✅ 이번 리뉴얼에서 §D 정정함.
- [ ] doc-13/15의 `$fatal` abort·exit-1 / `-Wno-*`·`-Werror=` 억제 플래그 / "body MsgCode 전부 MVP 구현 대상" 서술 vs dead codes 실태 — P1-1·P2-11과 동기화.
- [ ] 소항목: 10-vcd-dump.md:15 "7종"(실제 5종) · 04-simulation-control.md:137 "$finish severity 처리"(실제 무시) · hdl-parser:1119 게이트 프리미티브 주석(실제 키워드 lex) · doc-01:22-26 filelist `-f`/multi-lib/`vita explain` 커밋 vs 부재(Phase-1.x 트래킹 or de-scope 결정).
- [x] (구)트래커:290-292 doc-01 drift 3건 — 2026-06-07에 이미 교정 완료된 stale checkbox였음. 이번 리뉴얼로 해소.

## 권장 작업 순서 (다음 세션)

1. **P0 런타임 절단 클러스터**(P0-1~4) — `to_u64` 계약 수정 + 호출부 전수. 소규모·고가치. iverilog 차분 회귀 추가.
2. **P0-5/6/7 elaborate 상수 도메인** — silent-0 박멸(Cond·$clog2 + 미폴딩=Error) → 부호 i64 확대 → 하강 genvar. 같은 파일 연쇄 작업.
3. **P1-1 `$fatal` 계열** — 최소 $fatal→error-exit 브리지(CI 신뢰성 직결).
4. **P2 quick wins** — VCD open/flush 진단·delta-limit 진단·`--help/--version`·BufWriter(T0b)·아티팩트 temp+rename.
5. **P4 T0a/T0b → T1** — 병렬화 진입(측정 게이트 후 writer 스레드).
6. 이후: P0-8/9 display·monitor 의미론 → native-eval follow-on(ROADMAP §C) → 스케줄러축 → P1 나머지 → P3.

## 아카이브 (완결 이력 요약)

2026-06-05 6축 감사 52항목(BLOCKER 3: timescale 전체 모델 · `**` const-eval · VCD 계층/실명 — 전부 해결) + 후속 큐 5 + Stage A 릴리스 문서 + **Stage B** 컴파일드 백엔드 선결 11/11 + **Stage C** C1·C2 바이트코드 VM(byte동일·P5 차분 게이트) + profile-driven perf 4R(eval-heavy 2781→461ms ≈ **6x**) + **C4-lite native-eval**(식-바운드 VM ≈2.3x) + C7 혼합-timescale postponed 버그(`fbb869c`) + 멀티-top 다중 root(`148116b`) — **전부 완결**. 상세 시계열: 이 파일 git 이력(HEAD `b3651fa` 시점) · perf = [doc-18 §실측](preview/18-acceleration-analysis.md) · 결정 근거 = [ROADMAP](ROADMAP.md) §0·§3.
