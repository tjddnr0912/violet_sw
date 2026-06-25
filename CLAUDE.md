be brief

# CLAUDE.md - violet_sw

멀티 프로젝트 개발 및 운영 저장소.

## Repository Overview

```
violet_sw/
├── 005_money/          # 암호화폐 트레이딩 봇 (Bithumb)
├── 006_auto_bot/       # 뉴스 자동화 봇 (RSS→AI→Blogger)
├── 007_stock_trade/    # 주식 퀀트 자동매매 (한국, KIS API)
├── 008_stock_trade_us/ # 주식 퀀트 자동매매 (미국, KIS API)
├── 009_dashboard/      # 트레이딩 대시보드 Flask 백엔드
├── 010_ios_dashboard/  # 트레이딩 대시보드 iOS 앱 (SwiftUI)
├── 011_macos_cc_usage/ # Claude Code 사용량 모니터 (macOS 메뉴바)
├── 012_stock_dashboard/ # 글로벌 시장 대시보드 (Bloomberg-style, FastAPI)
├── 013_shortcut/       # 비주얼 블록 Apple Shortcuts 빌더 (SwiftUI)
├── 014_casper/         # 미장봇 (US Stock Bot) — SPMO/GEM + Casper(ORB+FVG) 멀티 bucket, KIS API
├── 016_claude_rtl/     # vitamin — 오픈소스 Rust RTL 시뮬레이터 (vita/vcmp/velab/vrun)
├── 000~004_*/          # Lab & Study (Archive)
├── start_all_bots.sh        # 전체 봇 일괄 실행 (iTerm2 6탭)
└── start_all_bots_cmux.sh   # 전체 봇 일괄 실행 (cmux 단일 워크스페이스 3×2 pane)
```

## Quick Start

```bash
./start_all_bots.sh         # iTerm2에서 모든 봇 일괄 실행
./start_all_bots_cmux.sh    # cmux에서 모든 봇 일괄 실행
```

## Production Systems

| Project | 설명 | 실행 | 상세 |
|---------|------|------|------|
| 005_money | Bithumb 암호화폐 봇 (Ver3, 15분 주기) | `./scripts/run_v3_watchdog.sh` | [CLAUDE.md](005_money/CLAUDE.md) |
| 006_auto_bot | 뉴스/버핏/섹터 봇 (Gemini+Claude→Blogger) | `./run_investment_bot.sh` | [CLAUDE.md](006_auto_bot/CLAUDE.md) |
| 007_stock_trade | 한국주식 퀀트 (KOSPI200, 15종목) | `./run_quant.sh daemon` | [CLAUDE.md](007_stock_trade/CLAUDE.md) |
| 008_stock_trade_us | 미국주식 퀀트 (S&P500, 15종목) | `./run_quant.sh daemon` | [CLAUDE.md](008_stock_trade_us/CLAUDE.md) |
| 009_dashboard | Flask 대시보드 (port 5001) | `python app.py` | [CLAUDE.md](009_dashboard/CLAUDE.md) |
| 010_ios_dashboard | SwiftUI iOS 앱 (MVVM) | `xcodegen generate` | [CLAUDE.md](010_ios_dashboard/CLAUDE.md) |
| 011_macos_cc_usage | Claude Code 사용량 모니터 (macOS 메뉴바) | `./install.sh` | [CLAUDE.md](011_macos_cc_usage/CLAUDE.md) |
| 012_stock_dashboard | 글로벌 시장 대시보드 (Bloomberg-style, port 5002) | `./run_dashboard.sh` | [CLAUDE.md](012_stock_dashboard/CLAUDE.md) |
| 013_shortcut | 비주얼 블록 Apple Shortcuts 빌더 (iOS/macOS) | `xcodegen generate` | [CLAUDE.md](013_shortcut/CLAUDE.md) |
| 014_casper | **미장봇 (US Stock Bot)** — SPMO 50%/GEM 30%/Casper(ORB+FVG) 20% 멀티 bucket, 자본 $5k/$10k에서 MTUM·QUAL·Clenow 자동 활성화 | `./run_casper.sh start` | [CLAUDE.md](014_casper/CLAUDE.md) |
| 016_claude_rtl | **vitamin** — 오픈소스 Rust RTL 시뮬레이터 (SystemVerilog/Verilog, cargo 워크스페이스). 전 파이프라인 동작 + Phase-3 SVA 서브셋 + deferred immediate asserts + frame-call 콜스택 + **HIER-REST 완결** + **functional coverage 완성(N5+N5-G)** + 2-state 정수타입·게이트 프리미티브 + **N7 class/OOP(코어+상속+가상 동적 디스패치)** + **SVA-REST 완결**(property ops `always`/`until`/`implies`/`s_eventually`·`cover property`·`let`·`$assertoff/on/kill`·`assume property`·`seq[+]`) + **적대 재감사 silent-wrong 4종 수정**(class 필드 init·auto super.new·`%0N` 패딩·VCD real) + **하드닝 백로그(32 findings, ROADMAP §5) + 추천순서 1~6 + hostile-input cap 묶음 완료**(STAGED-DROP=staged 사이드카 13종 직렬화·PP-FANOUT-CAP=매크로 fan-out DoS 256MiB budget·VCD-SCRATCH=값변화 alloc 제거 1.41x byte-identical·CLASS-HEAP-CAP=class 힙 F4024 cap·WIDE-ARITH-CAP=광폭 산술 X-poison+W4025·GEN-NET-CAP=add_net 집계 budget·STMT/SEQ-DEPTH=재귀 cap·ELAB-ERR-CAP=진단 flood cap·FORK-TIE-CAP=tie-overflow fatal·PARSE-CONCAT-CAP=파서 전역 노드 예산 1<<21) + **잔여 perf/robustness 17/18 완료**(LOGEQ-WORD word-parallel·FMT-CACHE·POW-LANE const Mul-chain·REALG-DEDUP 단일 fmt_g·VM-REGPOOL/WIDEZERO/ARITY-ASSERT·MCD/FD-RECLAIM·CLS-FIELD/CALL·FORCE-REEVAL·WAITER-POOL·MW-DIV-HOIST·TRAILER-PIN·GEN-3X part b·**RULEV-MTIME**=option A 15번째 trailer WorkStamps+vrun mtime fast-path) + **SVA-QUAD 테스트 강화 완료**(윈도우 매처 13종 특성화+무오라클 적대검증; divergence hunt가 `##[0:$]` d=0 동클럭 silent-wrong 발굴→수정; perf 리팩터 자체는 deferred·비권고) + **Phase A — Tier ⓐ honest-loud 갭 4종 닫기**(`function void`+typed `parameter int/byte/...`·고정크기 `foreach` 선언방향·leading-`##` SVA·**`return` kw**=format-bump 주장 반증→IR-0; 닫기 직후 적대 hunt가 silent-wrong 3종 즉수정=param 값 coercion·foreach 하강순서·frame 2-state 기본값, 전부 iverilog parity; pre-existing 광범위 2종 surface=task copy-out·SVA X/Z 불리언 match→의사결정 대기) + **Phase B — N7-REST 검증 플랫폼(CRV B1)**: `rand` 멤버 + `constraint`(range/relational·`&&`) + `obj.randomize()`(결정적 seeded `dist_uniform`·3-OS byte-identical) — 제약 폴딩 `class_rand` 사이드카 IR-0, `SysTaskId::ClassRandomize`만 **format_version 9→10 bump**(골든 4종 재생성); 적대 hunt가 광폭-필드 제약-drop silent-wrong 1건 즉수정(i64 draw lane); randc/inside/dist/implication/inter-var/soft=B2 loud-reject (1707 tests green, format_version 10·MsgCode 57) + **Tier0 silent-wrong 전량 수정**(SVA X/Z 불리언=non-match §16.13.5 전 consequent+`disable iff(X)`·task output-formal copy-in/copy-out 전면교체 §13.5.1[width/sign coercion·static retention·glitch 제거·nested threading]·2-state X→0 coercion·2-state/param-expr 변수 init 1회성화, 적대 hunt 2회 29 confirmed 전량 수정, 1733 green·전부 IR-0) + **B-CRV(B2) 코어 일반 constraint solver**(rejection sampling·`COp` 술어 바이트코드 non-frozen=골든 무영향; inter-variable·`inside`·implication·`soft`; randomize() §18.11 반환값·signed>64bit·wide-술어 등 B2 hunt 8 confirmed 수정; format_version 10→11 artifact-only; 1743 green) + **`unsigned` 타입 버그 수정**(`int/longint unsigned` 등이 signed로 비교/출력되던 broad pre-existing silent-wrong: opt_signed tri-state+range_to_dims flag 존중, iverilog parity; 1748 green) + **B2 dist/randc**(가중 sampling `:=`/`:/`·cyclic 순열 per-instance, class_dist/class_randc 사이드카·format 11→13; 1751 green) + **B-CRV 완결=inline `randomize() with {…}`**(IEEE §18.7 per-call 제약·statement+assign-rhs·클래스 제약에 ADD: range는 도메인 narrow+나머지는 predicate AND·`randomize_with` 사이드카=SimOpts+14번째 staged trailer·format 13→14 artifact-only·AST `ExprKind::RandomizeWith(Box)` 박싱=depth-cap 회귀 방지; 적대 6-lens hunt→silent-wrong 5종 즉수정[2는 class 경로 pre-existing: unknown-field range·dist-field range silently drop]; **1760 green**) + **B-breadth array 메서드**(format 14→17: reduction sum/product/and/or/xor·ordering sort/rsort/reverse·locator min/max/unique/find*→queue·`with(item)` iterator; 적대 6-lens hunt→silent-wrong 3종 수정[sort/min/max 선언-타입 sign·동명 dyn-storage block-local heap 공유 loud·with-clause accumulator=VCS parity design pin]) + **B-breadth string 메서드**(format 17→18: atoi/atohex/atooct/atobin/atoreal·itoa/hextoa/octtoa/bintoa; atoi leading-sign·atooct/atobin=hand-IEEE) + **B-breadth program·union·parameterized class·virtual interface**(program=module AST·union packed=overlay·parameterized class=파스타임 monomorphization[셰도잉 존중·5-lens hunt 2종 즉수정]·virtual interface=정적 alias[unbound/rebind/type-mismatch loud]; 전부 IR-0·iverilog 미지원→hand-IEEE) — **🏁 B-breadth 6종 완료, 1822 green**. + **✅ ⓑ-breadth 후속 4종 + fill-width-system silent-wrong cluster + POW 2종 완료**(2026-06-24, **1878 green**, 전부 IR-0): `'1`/`'0`/`'x`/`'z` fill **context-determined 폭 완전 구현**(IEEE §11.6 width-inference + 전 context-site=assignment/init/fn·task-arg/return/case-label/port-conn/static-fn-body/repeat; **3회 적대 differential hunt** 전량 발굴→수정)·**task/function body-local 해소**·**string concat `{a,b}`/`{N{a}}`**·**class 멤버 shadowing distinct storage**(§8.14 rposition)·**POW `**`/`repeat` pre-existing 6종**(지수 sign-flip·wide-base overflow·left-assoc·self-det 폭=LEFT·`0**음수`=X·`repeat(런타임 count)` 0회→down-counter desugar, fill 무관). iverilog parity·**1885 green**. + **🔒 정확성 거버넌스 감사**(2026-06-24, **1903 green**, 전부 IR-0·format_version 18 불변, 사용자="정확도 최우선"): 14-target 적대 audit이 "correct-or-loud" 불변식 검증→11 SAFE(loud/match)+silent-wrong 발굴, fix-verify hunt가 edge 추가발굴 → **silent-wrong 7종 수정**(typed param 선언폭=bare/fill/override/hier `dut.W`·`$bits(param)`·untyped sized-literal 폭·static task body-local 영속(init-once)·non-const var-init module+block-local=t0 synthesized initial), **unpacked-array task-local=LOUD 승격**, var-init-from-cont-net·static-local t0 race=impl-defined 문서화 + **개발예정①-A ascending part-select 완결**(2026-06-24, 1920 green, IR-0: `logic [0:N]` regular+indexed·read+write·array-elem/port/gen 방향 인지 lowering; 적대 5-angle hunt가 indexed-부 silent-wrong cluster 발굴→전량 수정·48-case 차분 0; 잔여=ascending packed-struct 멤버=별개 슬라이스) + **개발예정①-B task output/inout select actual 완결**(2026-06-25, 1928 green, IR-0: part/bit/indexed-select·array-element actual을 lowered lvalue copy-out §13.5.3; 적대 hunt가 slice-B 회귀 PANIC=frame-local select→loud 승격, pre-existing silent-wrong 2종[2-state frame copy-in X-coercion·X-index part-write]은 후속 커밋) + **후속#1 2-state frame copy-in/write X→0 coercion 수정**(2026-06-25, 1935 green, IR-0: byte/int/shortint/longint frame formal·body-local X-보유 broad silent-wrong §6.11.3→intro_kind 등록+frame_slot_write coercion; 잔여=2-state return 슬롯=ParamType AST 확장 필요) + **후속#2 indexed-part `[X+:w]` WRITE X-index discard**(2026-06-25, 1942 green, IR-0: X/Z index 부분기록→`has_xz()` 감지+`OOR_DROP` discard, real-negative P0-IPU 부분기록 보존; **🏁 개발예정① + hunt silent-wrong 전량 처리**) + **후속#3 return-slot 2-state coercion**(2026-06-25, 1950 green, AST `.vu` 재핀·sim-ir 18 불변: `function int/byte f; f=x;`가 X 보유하던 silent-wrong→`FunctionDef.ret_two_state`+2-state-return을 frame 경로 라우팅+return slot `intro_kind` 등록→`frame_slot_write` coercion·4-state 보존) + **후속#4 wide/unsigned-OOR write index discard**(2026-06-25, 1952 green, IR-0: clean beyond-u32·unsigned `0xFFFFFFFF` index가 부분기록하던 silent-wrong→`ev`를 `to_i128_signed`+i32-range로 교체, small-neg P0-IPU partial 보존·X/Z와 통합) + **①-a struct-member ascending part-select READ 완결**(2026-06-25, 1966 green, parser-only IR-0·format/AST 해시 불변: 패킹 구조체 멤버 서브셀렉트가 ascending 멤버서 descending 슬라이스로 읽히던 silent-wrong→`StructLayout` per-member `ascending`+모든 READ 서브셀렉트를 field part-select `pv` 위 `IndexedPart`로 정규화=field-bounded[OOB→X·인접 멤버 leak 없음]·regular `[a:b]`→`[min(a,b)+:│a-b│+1]`·역순 range loud·`struct_member_expr` non-inline로 paren stack-overflow 회귀 방지; 오라클=등가 ascending NET[iverilog 자체 struct 필드 버그]; 적대 리뷰 루프 silent-wrong 2종 적발→수정[flat-remap cross-field leak·OOB regular X-misplacement]; WRITE=loud 유지=elaborate lvalue 후속) + **①-b 로우드 갭 2종**(2026-06-25, 1975 green, IR-0): unpacked-array task-local(`79b5ddc`=비-automatic task의 unpacked 배열 local을 모듈 배열처럼 array_len+사이드카 등록·static 영속·8-case 차분)·generate idx `g[P].x`(`b688926`=리터럴값 localparam만 fold via `const_locals`/`try_const_index`·parameter/param-derived=loud 유지[override silent-wrong 방지]·모듈-스코프 격리·5-case 차분); 잔여=base-class cast `Base'(d)`=`Type'(expr)` 구문 부재+iverilog 미지원 오라클 없음=deferred + **③ N6 real-math + 비균등 `$dist_*` 완결**(2026-06-25, **1995 green, format_version 18→19**, 사용자 결정 D1 구현·D2 vendoring·D3 내부 불변식·D4 전부): **vendored 순수-Rust libm**(`third_party/libm` libm 0.2.16·`[workspace].exclude` non-member→clippy 무영향·`default-features=false`→arch intrinsic 없음→3-OS 비트 동일). real-math 21종 §20.8.2(`$ln/$log10/$exp/$sqrt/$pow/$floor/$ceil/$sin/$cos/$tan/$asin/$acos/$atan/$atan2/$hypot/$sinh/$cosh/$tanh/$asinh/$acosh/$atanh`, SysFuncId×21·정수 arg→real coercion·domain error NaN/±inf·iverilog %g/%f 표시정밀도 일치) + 비균등 `$dist_normal/exponential/poisson/chi_square/t/erlang`(DistT/DistErlang 신규·`dist_uniform_special` 일반화·`k_dist_seeded` which-dispatch·rng.rs Annex 포팅; **seed 스트림=iverilog 바이트 동일**[정수 LCG·6종 전부 검증·t=χ²-then-normal 순서 수정]·**결과 int=hand-IEEE 핀**[D3, exp/normal/erlang 일부 ±1]). 적대 differential 워크플로(33 agent)가 real `%f/%e/%g` NaN 대문자(`NaN`→`nan`)·음의 0(`-0.0`→`0`, 상수/리터럴 flush 정규화·기존 핀 2개 교정) silent-wrong family 발굴→수정; 잔여=런타임 구성 `-0.0` 표시(impl-defined·문서화) + **🟡 ② SVA empty-match `[*0:n]`/`[*0:$]`/`[*]`/`sig[*]` `##1`-인접 슬라이스**(2026-06-25, **2009 green**, IR-0·format_version 19 불변): `b[*0:n]`≡`empty|b[*1:n]`, empty 분기=`SeqTerm::Empty` 센티넬. `a ##1 b[*0:n] ##1 c`(≡`a ##1 c`)·suffix `a ##1 b[*0:n]`(≡`a`)·multi-empty all-`##1` 지원(window-length 논증). **적대 2-round 리뷰(no oracle=iverilog 거부)가 trailing-`##0` silent-wrong 발굴→`##1`-인접 가드로 수정**(비-`##1` 인접 융합은 §16.9.2.1 association-순서 모순+오라클 부재라 honest-loud=`EMPTY_MATCH_HASH1_ONLY` E3009; 2차 리뷰 65프로브 CLEAN). honest-loud 유지=비-`##1` 인접·empty SEED·consequent·throughout/within·seq local var·cross-clock multi-term·advanced skew | `cargo test --workspace --locked` | [CLAUDE.md](016_claude_rtl/CLAUDE.md) |

## Development Guidelines

1. **프로젝트 경계 존중**: 각 프로젝트는 독립적. 다른 프로젝트 코드 참조 금지.
2. **파일 생성 최소화**: 기존 파일 수정 우선. `.md`는 명시적 요청 시에만 생성.
3. **환경변수**: 각 프로젝트별 `.env` 파일 필요. **절대 Git에 커밋하지 말 것.**
4. **Telegram**: 각 프로젝트는 독립 Bot Token 사용. 충돌 없음.

### Git Commit Convention

```
Add <feature> / Fix <bug> / Update <component> / Refactor <module>
```

## 상세 문서

- [프로젝트 상세](docs/PROJECTS.md) - 각 프로젝트 실행 방법, 기능 설명
- [환경변수](docs/ENVIRONMENT.md) - 프로젝트별 .env 설정
- [트러블슈팅](docs/TROUBLESHOOTING.md) - 봇 중복 실행, Telegram 에러, API Rate Limit
