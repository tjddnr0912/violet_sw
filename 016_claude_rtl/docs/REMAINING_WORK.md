# vitamin — 잔여 작업 트래커 (Remaining Work)

> **리뉴얼: 2026-06-10** · 기준 HEAD `b3651fa` → **동일자 전 항목 소진**: P0 9건 → P1 9건 → P2 12/12건 → P3 4건+양호판정 → P4 T0a/T0b/T1 → native-eval follow-on → P5 문서부채 전체(571 green, golden unflipped fmt_ver 3) → **2탄: perf 축 2건 + Phase-1.x 전부**(스케줄러축 ≈1.85x · 구조 native lane ≈2.8x · vita-log 게이트+exit 2 · filelist · explain · **format_version 4**(런타임 delay·dump flush/limit·Force/Release) — HEAD `8664627`, **611 tests green**) · clippy/fmt clean · MsgCode **50**. **이 트래커는 완결 — 신규 작업은 §권장 순서(아래 갱신본) 또는 ROADMAP §2.**
> 출처: 7축 감사 — ①Gemini-fix 검토 ②spec-gap ③sim-engine ④front-end ⑤메모리/자원 ⑥운용성 ⑦병렬화. 핵심 항목은 라이브 재현(+iverilog 차분)으로 확정, 각 항목에 `재현:` 표기.
> 이전 트래커(2026-06-05 생성: 감사52 + Stage A/B/C 이력)는 **전항목 완결로 아카이브** — 이 파일의 git 이력(`b3651fa` 시점 버전) · perf 시계열 = [doc-18 §실측](preview/18-acceleration-analysis.md) · 전략 = [ROADMAP](ROADMAP.md). 요약은 맨 아래 §아카이브.
> 미해결 `- [ ]` / 해결 `- [x]` + 커밋·날짜. 우선순위: **P0**(silent-wrong 정확성) > **P1**(시뮬 의미론: warn-후-오동작) > **P2**(운용/CLI/진단) > **P3**(메모리/장기 안정) > **P4**(병렬화·신규 트랙) > **P5**(문서부채).

## Gemini shift fix 검토 결과 (2026-06-10 · 채택)

`const_eval_in_scope`의 `wrapping_shl/shr` → `checked_shl/shr().unwrap_or(0)` (elaborate/src/lib.rs:1379-1382):

- ✅ **채택** — Rust `wrapping_shl`이 shift량을 mod 32로 마스킹해 `1<<32`→1이 되던 함정 제거는 옳다. 460 green·clippy 무영향·골든 무영향, 4개 arm 통합도 무해.
- ⚠️ 단, gemini_debug.md의 근거 서술 2건은 부정확: ①"중복 매치 암 제거" = **오진**(제거된 것은 별개 variant `AShl/AShr`; 진짜 중복이면 clippy `-D warnings` 게이트가 이미 실패했음) ②"0이 정답" = 32bit-exact 해석에서만 참 — **차분 오라클 iverilog는 `1<<32`=4294967296**(unsized 상수를 >32bit로 폴딩)이고, `parameter [63:0] F = 1<<32`는 IEEE 컨텍스트 확장상 2^32가 명백 정답(vita 0, 수정 전 1 — 둘 다 오답). 근본 해소 = P0-6.

## P0 — 정확성: silent-wrong-value (최우선)

**런타임 >64bit 절단 클러스터** — 공통 근원: `Value::to_u64`(value.rs:313-320)가 width>64에서 None 대신 word0 절단값을 반환.

- [x] **[P0-1]** >64bit relational 비교 절단 — ✅ 2026-06-10 `7bfd8c3`. 임의 폭 word-wise 정확 비교(부호 인지)로 교체, 64/128 lane 의존 제거. 회귀 `wide_value_semantics.rs` + iverilog 차분 `diff_wide_value_truncation_cluster`.
- [x] **[P0-2]** shift-amount 절단 — ✅ `7bfd8c3`. over-u64 amount는 saturate(전부 shift-out: 논리 0/산술 sign-fill). x/z는 기존대로 X.
- [x] **[P0-3]** unary minus(negate) 단일워드 — ✅ `7bfd8c3`. 전 폭 two's complement(word carry).
- [x] **[P0-4]** **`to_u64`/`to_u128` 계약 수정**(overflow→None) + 호출부 전수 — ✅ `7bfd8c3`. array word index/lvalue offset의 `as u32` wrap(2^32+k→k, 읽기·쓰기 모두)도 OOR sentinel로; part-select offset·$clog2(임의 폭 정확)·%c(low byte 유지)·unsigned→real(u128 lane). arith()는 기존 width 게이트 뒤라 unwrap 안전. 워크스페이스 470 green.

**elaborate 상수 도메인 클러스터:**

- [x] **[P0-5]** 폴딩 불가 param/localparam/enum-label → silent 0 — ✅ 2026-06-10 `b30881a`. ternary `?:`+`$clog2` 폴딩 추가, 미폴딩 param/enum-label은 **ElabUnsupported Error**(0은 post-error recovery 값일 뿐). concat/함수호출 폴딩은 필요 시 후속(현재는 loud).
- [x] **[P0-6]** const 도메인 u32 → 부호 있는 i64 — ✅ `b30881a`. `1<<32`=4294967296(iverilog parity), checked 산술(overflow=loud), signed AShr sign-extend, 음수 param은 32bit signed const로 바인딩(`%0d`→`-4`), `0..=u32::MAX`는 기존 const 형상 그대로 → **기존 디자인 골든 byte 불변**(482 green). 잔여: >64bit 리터럴/i64 초과값은 도메인 밖 → None(loud).
- [x] **[P0-7]** 하강 generate-for 폭주 — ✅ `b30881a`(P0-6의 signed 비교로 해결). `for(i=3;i>=0;i=i-1)` 정상 4회 unroll + zero-trip(-1 시작) 무진단 통과. 회귀 `const_domain_semantics.rs` + iverilog 차분 `diff_const_domain_cluster`.

**display/monitor 의미론:**

- [x] **[P0-8]** `$display` 인자 의미론 — ✅ 2026-06-10 `5b3c6d4`. IEEE §17.1 순차 처리로 엔진 통합: ①잔여 인자=기본 radix(padded %d/실수 %g) ②문자열 인자=inline 포맷 세그먼트(StrUtf8 검출, 후속 인자 소비) ③무포맷 branch=패딩 필드 연접(공백 join 제거) ④`%v`(St0/St1/StX/HiZ)·`%u/%z`(소비+무출력)·`%p`(값) 인자 소비. elaborate 무변경(엔진만), 회귀 `display_semantics.rs` 10 + iverilog 차분 `diff_display_arg_semantics`(패딩까지 byte 일치).
- [x] **[P0-9]** `$monitor` 트리거 과민 — ✅ `5b3c6d4`. ①직접 `$time/$realtime` 인자는 변화 비교에서 제외(IEEE §17.1.3 — 시간만 흘러도 매 스텝 재인쇄하던 버그) ②비교를 비트평면(width/val/unk)만으로(`vals_same_bits`).

## P1 — 시뮬 의미론: warn-후-오동작 (정지·계속 클래스)

- [x] **[P1-1]** `$fatal/$error/$warning/$info` — ✅ 2026-06-10 `8d6abec`. Display 스텀트 + **SeverityTable 사이드테이블**(StmtId→kind, SimOpts/.velab 5번째 trailer, frozen IR 0줄·골든 무영향)로 구현. `$fatal`=묵시 $finish+ExitClass::Fatal(exit 1, 선행 finish_number 리터럴 소비), `$error`=HadErrors+계속, `$warning/$info`=진단만. 출력=진단 스트림(F4004/E4003/W4007/I4005, sim_time 부착) — stdout 비오염. Kernel/Op/StmtEffect에 StmtId 배선(인터프리터=VM parity 테스트). 회귀 `severity_tasks.rs` 8 + `severity_exit.rs` 4(staged trailer 왕복 포함).
- [x] **[P1-2]** force/release·proc assign/deassign·`->event` — ✅ 2026-06-10 `522e76c`. ElabUnsupported 하드에러 승격(구문별 메시지). 회귀 `legality_semantics.rs`.
- [x] **[P1-3]** 비상수 `#delay` — ✅ `522e76c`. loud-reject(런타임 delay=Phase-2, frozen Delay{u32}).
- [x] **[P1-4]** in-body `@(*)`·멀티엣지 — ✅ 2026-06-10 `097f2c3`. `@(*)`=제어 문장 read-set 추론(IEEE 1800 §9.4.2.2, Wait cause 사후 패치로 comb 기계 재사용); 멀티엣지=loud-reject(frozen Edge 1-term). iverilog 차분 포함.
- [x] **[P1-5]** b/o/h 16종 — ✅ 2026-06-10 `4292eec`. RadixTable 사이드테이블(StmtId→2/8/16, 6번째 trailer)+FmtCapture.radix, `fmt_radix` 재사용(iverilog 무구분자 padded join까지 byte 일치, 라이브+차분 검증). **Sidecars 구조체 도입**(5→7테이블 번들; trailer는 세그먼트별 append-only 유지). doc-01 주장은 이제 참.
- [x] **[P1-6]** `$finish` 동일스텝 postponed 유실 — ✅ `097f2c3`. Finish/Stop/Fatal 전부 현 스텝 드레인 후 종료(IEEE §17, Icarus/VCS 정합). MVP-분기 박제 테스트는 IEEE-strict 계약으로 갱신.
- [x] **[P1-7]** `fork_mode()` panic — ✅ `522e76c`. t0 게이트+런타임 둘 다 Fatal 진단(E9001)+graceful 종료. trailer 외과 절단 회귀(staged_flow.rs).
- [x] **[P1-8]** part/bit-select 멀티드라이버 — ✅ `097f2c3`. per-bit 구간 계상(whole=[0,w), 정적 select=[off,off+w), `(msb-lsb)+1` 폭 엣지 폴딩). 중첩=E3001, 분할 구동=합법 유지. 동적 offset은 보수적 미계상.
- [x] **[P1-9]** net-vs-var 적법성 — ✅ `522e76c`. **E3018 `E-ELAB-LVALUE-KIND`**(부록A→본문 승격): user `assign`→Reg/Integer/Real 거부, 절차 대입→Wire 거부, SV logic 양방향 통과, 포트바인딩/decl-init 합성분 면제(IEEE 1800 var-port). 위법 픽스처 3건 교정 부수확.

## P2 — 운용/CLI/진단 견고성

**silent-failure 군집:**

- [x] **[P2-1]** VCD open 실패 침묵 — ✅ 2026-06-10. `W-RUN-VCD-OPEN-FAIL`(VITA-W4018, 경로+OS에러) 경고 후 시뮬 계속. 회귀 `run_diagnostics.rs`.
- [x] **[P2-2]** VCD flush 에러 침묵 — ✅ `finalize_vcd` flush 실패 → `W-RUN-VCD-WRITE-FAIL`(VITA-W4019). 단위테스트 state.rs(FailWriter 주입).
- [x] **[P2-3]** delta-limit 무진단 — ✅ `F-RUN-NO-CONVERGE`(VITA-F4016, 부록A→본문 승격) 단일샷 발행. 전 경로 funnel(settle/run-loop `fatal_delta_limit` + interp/VM in-body guard `mark_fatal`), VM parity 테스트. ⭐4-state에선 `assign a=~a`가 X-안정이라 발진 repro에 정의값 시드 필요.
- [x] **[P2-4]** `--help/-h`/`--version/-V` — ✅ 전 applet(vita/vcmp/velab/vrun) usage+버전 출력, exit 0. `cli_ux.rs` 4 테스트. MsgCode 45→**48**(bijection 게이트 동기화, doc-15 본문 3절 추가).

**안전 레일:**

- [x] **[P2-5]** parser 재귀 가드 — ✅ 2026-06-10 `41f5162`. expr 재귀 cap **256**(2MiB 디버그 테스트 스택에서 512도 초과 — 프레임 비대) → clean parse error. ⚠️깊은 **문장** 중첩(begin×N)은 별도(희귀, 잔여 소항목).
- [x] **[P2-6]** `MAX_ARRAY_LEN`(1<<24) — ✅ `41f5162`. 초과=ElabUnsupported.
- [x] **[P2-7]** 아티팩트 비원자적 쓰기 — ✅ 2026-06-10 `write_artifact_atomic`(`<out>.tmp.<pid>` → rename, 실패 시 tmp 정리). vcmp/velab 양쪽. 잔여물-부재 회귀 `staged_flow.rs`.
- [x] **[P2-8]** native_eval eid 방어 — ✅ `41f5162`. `exprs.get()?` bail→오라클 폴백.
- [x] **[P2-9]** `--timeout <ticks>` — ✅ `41f5162`. vita/vrun, SimOpts.time_limit 배선(도달=clean Quiescent exit 0). 기본은 무제한 유지.

**진단 taxonomy/계약:**

- [x] **[P2-10]** warn() 코드 오염 — ✅ `41f5162`. 범용 warn=**W3056 `W-ELAB-FEATURE-LIMIT`**(부록A→본문 승격). W3008은 실제 폭-절단 경고 구현 전까지 본문 예약(현재 emitter 0 — 의도된 dead).
- [x] **[P2-11]** ✅ `41f5162`(+P1-1로 RunUser\*/RunFatal 활성화). 중복 모듈=**E-DUP-UNIT Error**, `%m`=proc_scopes 사이드카(7번째 trailer)로 실 계층경로(strobe/monitor는 등록 스코프 복원; iverilog 내용 일치 라이브 검증). 잔여 dead codes(DupUnit→활성됨 제외: ParseImplicitNet·ElabUser\*·RunAssertFail·RunNoLocations·LintUnclosed·W3008)=예약 상태 명문화. exit class 2 문서 불일치=P5로.
- [x] **[P2-12]** 정책 소항목 묶음 — ✅ 2026-06-10 일괄 처리. ~~`$finish(n)` doc 주장~~(✅ doc-04) · `timescale_unit_string`=clamp([-15,+2] 포화, "-16→100s" 오렌더 제거) · **`time` 타입 수용**(64-bit unsigned 4-state 변수, NetKind::Reg 매핑 — frozen IR 무변경; unpacked 배열·`parameter time` 포함, iverilog 차분 `diff_time_type_semantics` 추가) · `` `pragma`` 수용-무시(IEEE §22.11, 줄 소비·무진단) · implicit-net 정책 명문화(doc-15 W2003: v1=사실상 `default_nettype none`, 미선언→E3010, W2003=예약) · `same_path`=이미 canonicalize 동작 확인(./x.sv vs x.sv 거부 회귀 박제). 잔여 없음.

## P3 — 메모리/장기 시뮬 안정성

- [x] **[P3-1]** fork 아레나 무한 성장 — ✅ 2026-06-10 `0945dfe`. free-list 슬롯 재활용(child=보고 직후, barrier=전 자식 보고 시 — 그 시점엔 살아있는 참조 0 ⇒ ABA-safe; 순서키=tie라 byte 불변). churn 회귀 2종(join_none×5000 정확 1회 실행, blocking join×2000).
- [x] **[P3-2]** monitor baseline Vec — ✅ `0945dfe`. eval→비교→in-place 덮어쓰기(모니터 수명당 1회 할당).
- [x] **[P3-3]** VCD sink BufWriter — ✅ 2026-06-10. `BufWriter::with_capacity(64KiB)` 래핑(finalize가 명시 flush → byte 불변). dump-heavy perf 측정(T0b 잔여)은 P4에서.
- [x] **[P3-4]** net_to_edge clone — ✅ `0945dfe`. 인덱스 루프(바디는 cur.active만 push).
- [x] **[P3-5]** native 스택 alloc — ✅ `0945dfe`. 고정 64슬롯 배열+sp(호출당 heap 0); try_compile이 post-order 깊이 검증(초과=오라클 bail).
- [x] **[P3-기록] 종료/메모리 위생 양호 판정 (2026-06-10 감사)** — `unsafe` 0건 · Rc 9곳(vm_cache 한정) 비순환 · `finalize_vcd` 전 종료경로(정상/$finish/$stop/delta-limit/error) 호출 · HashMap 3곳(vcd by_id·parser typedefs 등) lookup-only로 결정성 무해 · BTree-only 스케줄러 재확인. Ctrl-C 핸들러 없음 = 커널 fd flush로 마지막 완료 write까지 유효한 truncated VCD(문서화만 권장). CLI 종료 시 미해제 누수 없음(정상 Drop + OS 회수). 라이브러리 임베딩 시 재평가.

## P4 — 병렬화 트랙 (신규 · 2026-06-10)

**현황:** 프로덕션 코드 스레딩 0(std::thread/rayon/Arc/Mutex 부재), 기존 계획 0 — doc-18:19가 PDES를 "결정성(3-OS byte-identical)과 상충·장기"로 박제했을 뿐, `--threads`류 옵션 구상 부재. 엔진은 의도적 단일스레드(`!Send`인 `Box<dyn Write>`/`LogSink`/`Cell`)이나 Rc는 9곳(vm_cache)으로 얕고, `simulate(&SimIr)`은 불변 입력의 순수 함수 — **스레드/프로세스당 1 시뮬은 이미 자유**.

**옵션/UX 설계(확정안):**
- `--threads N`(alias `-j N`) — `vita`/`vrun`에 추가(vcmp/velab은 당장 대상 없음). 기본 `auto` = `min(available_parallelism, 8)`(std, MSRV 1.82 OK, 신규 dep 0). env `VITA_THREADS`(플래그 우선). `--threads 1` = 현행과 완전 동일 경로.
- **계약: 모든 N·모든 OS에서 VCD/stdout/아티팩트/exit code byte-identical** — thread 수는 wall-clock만 바꾼다. corpus를 `--threads 1` vs `4`로 byte-diff하는 P5식 차분 게이트로 강제. 구현은 `SimOpts` out-of-band(frozen IR·골든 무영향).

| 단계 | 내용 | 기대효과 | 결정성 리스크 | 공수 |
|---|---|---|---|---|
| ✅ **T0a** | ~~multi-run 병렬~~ — 2026-06-10 완료. `backend_equiv`가 interp·VM을 `thread::scope` 동시 실행(`SimIr`=Sync, sink/VCD 경로 스레드별 분리) | 차분 스위트 ~2x | 0 | — |
| ✅ **T0b** | ~~BufWriter+측정~~ — BufWriter(P3-3)+`perf_dump_share` 측정 케이스. **실측: dump-heavy VCD 비중 40.9%(BufWriter 적용 후), T1 이론상한 ≤1.69x** | 측정 완료 → T1 정당화 | 0 | — |
| ✅ **T1** | ~~`--threads ≥2` VCD writer 스레드~~ — 2026-06-10 완료. `vcd_thread::ThreadedWriter`(bounded FIFO 8×64KiB chunk, 순서보존, write에러는 flush에서 표면화→W4019 경로 유지, Drop=drain+join). CLI `--threads N`/`-j N`(vita·vrun)+`VITA_THREADS`+auto(min(cores,8)). **byte-identical 계약 게이트**: `tests/threads.rs`(엔진 1vs4) + `cli_ux.rs`(subprocess 1vs4 VCD byte-diff) | VCD I/O 은닉(상한 1.69x) | 0(게이트 강제) | — |
| ⬜ **T2** | front-end per-compilation-unit 병렬 — 현 다중파일은 의도적 단일 연결(`` `define`` 순서 의존)이라 SV `-u` 의미론 결정 선행 | 小(front-end는 ms 스케일) | 中 | 보류 |
| ✕ **T3** | parallel elaborate — **비추천**: 전역 arena ID 순서 자체가 골든 계약, byte-identical 재현 머지 비용 高 | 小 | **高** | — |
| 🔬 **T4** | 엔진 내 PDES/정적 파티셔닝 — 연구 트랙 유지(doc-18 판정대로). Verilator `--threads`는 cycle-based 정적 파티셔닝+배리어라 가능; 이벤트구동+tie 순서+eager VCD에는 부적합, Icarus도 미지원 | 설계 의존 | 最高 | 연구 |

## P5 — 문서부채 (docs ↔ code 불일치)

- [x] 01-display-io.md b/o/h·예시 주장 — ✅ **구현으로 해소**(P0-8이 :46 예시를, P1-5가 :11/219 "16종" 주장을 참으로 만듦). 문서 수정 불요.
- [x] ROADMAP §D "의도적 deferral 전부 loud-reject 확인됨" → 거짓이었음 — ✅ 2026-06-10 리뉴얼에서 §D 정정 + P1-2/3으로 실제 loud-reject화 완료.
- [x] doc-13/15 동기화 잔여 — ✅ 2026-06-10. ~~`$fatal` abort·exit-1~~(✅ P1-1로 참) · `-Wno-*`/`-Werror=` 억제 플래그=Phase-1.x 미래형 명기(doc-15 거버넌스 + doc-13 suppression 절, `--help`=진실 공급원) · 예약 dead codes(ParseImplicitNet·ElabUser\*·RunAssertFail·RunNoLocations·LintUnclosed·W3008) 실태 명기(doc-15 거버넌스 불릿) · exit class 표 정정(doc-13: 현 구현=0/1/3+101, class 2=예약·현재는 1로 분류 명기).
- [x] 소항목 잔여 — ✅ 2026-06-10. ~~10-vcd "7종"~~(✅) · ~~04 "$finish severity"~~(✅) · hdl-parser:1119 주석(게이트 프리미티브=키워드-led, 이 arm 미도달·E2002 loud 명기) · doc-01:22-26 filelist `-f`/multi-lib/`vita explain`=**Phase-1.x 인라인 표기로 결정**(de-scope 아님, 목표 유지).
- [x] (구)트래커:290-292 doc-01 drift 3건 — 2026-06-07에 이미 교정 완료된 stale checkbox였음. 이번 리뉴얼로 해소.

## 권장 작업 순서 (다음 세션 — 2026-06-10 2탄 후 갱신)

1. ~~트래커 P0~P5 전체~~ ✅ · ~~perf 축(스케줄러 R1·구조 native lane)~~ ✅ · ~~Phase-1.x 전체(게이트/filelist/explain/v4 bump/force-release)~~ ✅ — **611 green, HEAD `8664627`.**
2. ~~①dirty-list 넷 스캔(R2)~~ ✅ 2026-06-10(NETS_HEAVY 305→15.5ms ≈19.7x — dirty 스윕+snapshot_prev 삭제) · ~~②filelist typed 버킷~~ ✅ 2026-06-10(-D/-I·+define+/+incdir+·WRONG-STAGE·OVERRIDE) · ~~③native-eval C6 lane~~ ✅ 2026-06-10(array-indexed `LoadIndexed` + 65..=128bit u128-pair wide 스택 — WIDE_HEAVY 0.59x·MEM_HEAVY 0.72x, narrow 무변경; 잔여 native = signed>64/wide 구조/real/sysfunc 저ROI 문서화, doc-18 §실측). ~~④vita-log 2단계~~ ✅ 2026-06-10(--log 단일-writer tee·-q/-v/--verbosity·counts epilogue `errors= warnings= notes=`·unopenable log=exit 3) · ~~⑤intra-assignment delay·force 재평가·implicit-net~~ ✅ 2026-06-10(blocking `= #d` 실semantics + NBA `<= #d`=loud E3009→차기 bump·force 연속 재평가·implicit-net=E3010 정책 확정으로 종결). ~~⑥Phase-2 관문~~ ✅ 2026-06-10 평가 완료(ROADMAP §F: bump-필수=NBA-delay·named-event·dynamic-storage는 v5 일괄, IR-무변경=immediate-assert·interface 스파이크·disable은 즉시 가능 — 진입 시퀀스 명문화) · ~~⑦3-OS CI~~ ✅ 2026-06-10(`.github/workflows/vitamin-ci.yml` — ubuntu/macos-14/windows 매트릭스, fmt/clippy/test --locked, ubuntu에 iverilog 설치로 차분 오라클 실가동, paths 필터로 vitamin 변경시만). **첫 가동이 Windows-전용 발산 3건을 연속 적발·수정 후 3-OS 전부 green**(run `27276108641`): ①테스트 include 셰임의 `/`-키 맵이 `Path::join`의 `\` 미스(`b34f67e`) ②autocrlf 체크아웃이 LF 골든을 CRLF화 → `.gitattributes` `-text` 핀(`b28ecb8`) ③ron `PrettyConfig::default()`가 플랫폼 newline(Windows `\r\n`)로 생성 → 명시 `\n` 핀(`3a52230`). 셋 다 프로덕션 코드 아닌 주변부의 byte-identity 누수. ~~⑧net_to_edge/waiter 자료구조~~ ❎ 2026-06-10 **측정으로 폐기** — `perf_nets_scaling` 프로브(512→2048→8192 idle nets)가 평탄(~15-17ms)을 보임: R2가 idle-net 세금을 전부 제거, waiter 워크는 부하 비례라 세금 아님. 프로브는 영구 회귀 계기로 잔류. ~~ROADMAP §F 진입 시퀀스~~ ✅ **2026-06-10/11 완주(674 green)**: (E) immediate assert(파서 If-desugar, AST 동결 유지, iverilog 차분 — `66c880b`) → (D) interface 스파이크(GO: 심볼 aliasing, SimIr 무변경 확정 — `3068be9`) → (F) disable 실동작(동봉 named block Goto, lazy exit-BB로 기존 CFG byte-불변)+proc-assign/deassign(force weak-rank 재사용, `assign_ranks` 사이드카+trailer 세그먼트 — `0ac0069`) → (C) dynamic-storage 설계 문서(`af5898a`, v5 형상 diff 전량 확정+B 재분류) → **v5 bump**(형상+REGEN, 기능 0 — `e7f08e8`) → (A) NBA transport delay(`delayed_nba` wheel, 차분 4레인 — `1617980`) → (B) named-event 카운터 desugar(sim-ir 0, 차분 3레인, `.vu` 재핀 — `0a39dec`). ⭐동시-틱 tie(Active $finish vs due-update/edge-wake)는 도구-발산 영역 — 차분 디자인은 tie를 회피하고 주석으로 핀. **다음 후보:** **(C) 엔진 증분 — ③dyn array 3a(heap/new/size/delete) ✅ 2026-06-11(`33e741a`, 677 green: `dyn_heap`+`DynObj`+`NetReader::dyn_size` 시임, W4020 warn-once, VCD 핸들 skip, hand-built SimIr 시임 테스트 — 문법은 ⑥) → 3b(인덱스 r/w 라우팅) ✅ 2026-06-11(`dyn_is_handle` 비트맵 깔때기 라우팅, OOB/X=원소폭 X·무시+W4020, 680 green) → ④queue ✅ 2026-06-11(691 green: `DynObj::Queue{VecDeque}` — push=SysTask 디스패치(원소형 §5.5 cast·cap warn+drop), 인덱스 r/w=3b 깔때기 공유+**`q[size()]`=push_back 동등 append(IEEE §7.10.1, iverilog 라이브로 설계문서 "무시" 가정 정정)**, **pop=`StmtEffect::QPop` 문장-레벨 인터셉트**(P7a read-phase 순수성 유지, Kernel 2메서드)+pop-rhs 바디 `is_codegen_able` 제외(VM=interp fallback, teeth는 parity 테스트로 입증), 비지원 배치 pop=eval arm X+W4020, pop SelfWidth=원소형(signed/unsigned 확장 차분), `q[$]`=DynSize-1 desugar 시임 테스트, empty pop=X+warn-once) → ⑤assoc ✅ 2026-06-11(701 green: `DynObj::Assoc{BTreeMap<i64,Value>}` — **키 도메인=signed i64 전역**(음수·>u32 합법)이라 u32 offsets 쌍에 못 실림 → `Offsets::AssocKey(Option<i64>)` variant 신설+`k_write_lvalue` ABI를 slice→`&Offsets`로(NBA·CA·VM·QPop 전 깔때기 공유=by-construction), READ는 eval Signal arm이 u32 coercion **전에** `is_assoc` 분기→`assoc_key`(64-bit 부호확장, X/Z·real=invalid)→`assoc_read`; exists/num=순수 eval arm(VM parity 자동)·delete(k)=SysTask 디스패치(미존재 키=무음 no-op §7.9, X키=W4020)·delete()=DynDelete 공용; X키 r/w=X/무시+W4020, 미존재 read=X+warn, write=원소 생성(§7.8.6), cap 1<<24 warn+drop; **native-eval LoadIndexed에 Assoc bail**(u32 도메인 발산 차단); concat-lvalue 내 assoc chunk=loud degrade. **iverilog 13.0이 assoc 선언 자체를 거부(라이브 확인)** → 유일하게 hand-IEEE 핀 레인(§7.8/§7.9, expression-force 선례)) → **⑥front-end 일괄 ✅ 2026-06-11(722 green, .vu 해시 재핀 1회)**: (C) 문법(lexer `$`·`Dim` 3변형·`ExprKind::{New,Dollar}`·메서드=기존 Call AST 재사용·핸들 decl/인덱스/메서드/특수형 elaborate 인터셉트·오용 전부 E3009 loud — dyn/queue=iverilog 차분 13 e2e, assoc=hand-IEEE) + (D) interface(스파이크 그대로: ModuleDecl 재사용+Modport+AnsiPort.iface, **nets 단계 4c 조기 평탄화**(부모 body `i.sig` 해소), 포트=심볼 aliasing(net/cont-assign 0), resolve_net 다중-세그 dot-join, modport 존재검증 — **iverilog가 interface port도 거부 → hand-IEEE 핀**, e2e 8). SimIr 무변경(format_version 5 유지). 잔여 = **(D) modport 방향 강제·interface 파라미터·generate-내 iface 포트 전달(후속 증분)** · ⑨P4-T2(front-end 병렬) · §A 잔여(저빈도 value-op word化 등 저ROI).
3. **Phase-1.x 기능** — ~~`-Wno-*`/`-Werror=` 게이트 + exit class 2~~ ✅ 2026-06-10 `791cca4`(vita-log GatePolicy/GatedSink; 승격 실패=class 1·산출물 미생성, 아티팩트 게이트=exit 2) · ~~filelist `-f`/`-F`~~ ✅ `eedd486`(argv-레벨 전개 v1 서브셋; 잔여=+incdir+/+define+ 버킷·WRONG-STAGE·OVERRIDE) · ~~`vita explain`~~ ✅ `2ca8949` · ~~런타임 delay~~ ✅ **format_version 4 bump**(Delay.amount=ExprId, 평가·×M·round는 엔진 suspension-time; X/Z→0 iverilog parity) · ~~`$dumpflush/$dumplimit`~~ ✅ (bump 무임승차, vcd-writer 기계는 기존재) · ~~force/release 실semantics~~ ✅ 2026-06-10 — per-net `forced` 플래그가 write_chunk 깔때기에서 전 일반 경로(절차/NBA/settle/delayed-ca) 차단, release=net settle-복원/var 값-유지 비대칭, whole-net 타깃만(bit-select=loud). **같은 날 후속: expression force는 IEEE §9.3.2 연속 재평가로 승급**(`active_forces` 레지스트리 — const-rhs는 iverilog 차분 유지, expression lane은 iverilog가 자인한 비준수 영역이라 hand-IEEE 핀). **Phase-1.x 전 항목 소진.**

## 아카이브 (완결 이력 요약)

2026-06-05 6축 감사 52항목(BLOCKER 3: timescale 전체 모델 · `**` const-eval · VCD 계층/실명 — 전부 해결) + 후속 큐 5 + Stage A 릴리스 문서 + **Stage B** 컴파일드 백엔드 선결 11/11 + **Stage C** C1·C2 바이트코드 VM(byte동일·P5 차분 게이트) + profile-driven perf 4R(eval-heavy 2781→461ms ≈ **6x**) + **C4-lite native-eval**(식-바운드 VM ≈2.3x) + C7 혼합-timescale postponed 버그(`fbb869c`) + 멀티-top 다중 root(`148116b`) — **전부 완결**. 상세 시계열: 이 파일 git 이력(HEAD `b3651fa` 시점) · perf = [doc-18 §실측](preview/18-acceleration-analysis.md) · 결정 근거 = [ROADMAP](ROADMAP.md) §0·§3.
