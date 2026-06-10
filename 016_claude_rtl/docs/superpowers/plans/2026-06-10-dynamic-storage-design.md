# Design — dynamic array / queue / assoc array 스토리지 (Phase-2 관문 (C), v5 bump 선행 문서)

> **2026-06-10 · §F 진입 시퀀스 ②.** v5 format bump를 한 번으로 끝내기 위한 사전 설계.
> 이 문서가 확정한 IR 형상 목록이 곧 v5 diff의 전부다 — 여기 없는 형상 변경이
> bump 후에 또 필요해지면 설계 실패로 간주하고 문서부터 갱신할 것.

## 0. v5 일괄 범위의 재분류 (이 문서의 첫 결정)

| §F 항목 | 당초 분류 | 확정 분류 | 근거 |
|---|---|---|---|
| (A) NBA delayed write `q <= #d rhs` | bump 필수 | **bump 필수 — v5 포함** | `NonblockingAssign`에 delay 필드(아래 §5) |
| (B) named event `->`/`@(ev)` | bump 필수 | **sim-ir 무변경으로 강등 — v5 제외** | **카운터 desugar**: `event e` → 64-bit Reg(init 0), `->e` → `e = e + 1`(BlockingAssign), `@(e)` → 기존 net AnyEdge 센스티비티. 같은-슬롯 이중 trigger도 카운터 증가라 prev/cur 비교에서 변화 보장(1-bit 토글의 0→1→0 누락 함정 회피). 표현식에서의 event 읽기/쓰기는 elaborate `event_nets` 집합으로 loud 거부. 잔여 비용 = AST decl kind 1개(.vu flip — (D)와 일괄). 동결 `WaitCause::Named`/`WakeCond::NamedEvent`는 예약-미사용으로 유지(제거 불가·무해) |
| (C) dynamic storage | bump 필수 | **bump 필수 — v5 코어** | 아래 전체 |
| (D) interface | 무변경(스파이크 GO) | 무변경 — `.vu`만 | [interface 스파이크](2026-06-10-interface-flattening-spike.md) |

**⇒ v5 (SimIr) bump = (A) + (C) 형상만. `.vu`(AST) flip = (B)+(D)+(C 문법) 일괄 1회.**

## 1. (C) 스코프 — MVP 컷

| 지원 (v5 구현 대상) | 명시 제외 (loud, 후속) |
|---|---|
| dynamic array: `int d[];` `d = new[n];` `new[n](d)`(복사) `d[i]` r/w `d.size()` `d.delete()` | `d[i:j]` 슬라이스, 다차원 dynamic |
| queue: `int q[$];` `q[i]` r/w, `q[$]`, `push_back/push_front/pop_back/pop_front/size/delete()` | `insert/delete(i)`(후속 가능), bounded queue `[$:N]`, 슬라이스 |
| assoc: `int a[int];`(정수 키 ≤64bit) `a[k]` r/w `a.exists(k)` `a.delete(k)`/`a.delete()` `a.num()` | **string 키**, `first/next/last/prev`, `foreach`(전부 후속 — 순회는 BTree 정렬이라 추가 시 결정성 공짜) |
| 원소 타입: 임의 폭 packed(4-state `Value` 보존), real | 원소가 struct/another-dyn인 중첩 |

## 2. 스토리지 모델 — handle-net + 엔진 힙

**원칙: 동적 객체는 BitPacked 평탄 스토어에 들어가지 않는다.** NetVar는 "핸들 선언"만:

- IR: `NetKind` += `DynArray | Queue | Assoc`. `NetVar.width` = **원소 폭**, `array_len = 0`,
  `init` = 빈 BitPacked. msb/lsb는 원소의 것.
- 엔진: `SimState.dyn_heap: BTreeMap<u32 /*NetId*/, DynObj>` (lazy-init; 핸들 net 수만큼).
  ```rust
  enum DynObj {                       // 엔진 내부 — 직렬화 안 됨(런타임 상태)
      DynArray { elems: Vec<Value> },         // new[n]만 크기 변경
      Queue    { elems: VecDeque<Value> },
      Assoc    { map: BTreeMap<i64, Value> }, // 정수 키, BTree = 순회/덤프 결정성
  }
  ```
- **결정성 계약**: 슬롯 키 = NetId(선언 순서), 주소/capacity는 어떤 표면(stdout/VCD/진단)에도
  비노출, assoc 순서 = BTree 키 순서. 3-OS byte-identity 불변식 유지.

## 3. v5 IR 형상 diff (전체 목록 — 이것이 bump의 전부)

| 타입 | 변경 | 용도 |
|---|---|---|
| `NetKind` | += `DynArray, Queue, Assoc` | 핸들 선언 |
| `NonblockingAssign` | += `delay: Option<u32 /*ExprId*/>` | (A) NBA transport delay |
| `SysFuncId` | += `DynSize, QPopBack, QPopFront, AssocExists, AssocNum` | 값-반환 메서드. `q[$]` = elaborate가 `DynSize-1`로 desugar. pop류는 side-effecting → P9 allow-list 제외(VM은 해당 바디 interp fallback) |
| `SysTaskId` | += `DynNew, DynDelete, QPushBack, QPushFront, AssocDeleteKey` | stmt 메서드. `DynNew(handle, n [, src])`, `delete()` 공용(`DynDelete`), assoc `delete(k)`는 키 인자 |
| `Expr::Signal`/`LvalChunk` | **무변경** — `word: Some(idx)`를 dyn 핸들에 재사용 | `d[i]`/`q[i]`/`a[k]` r/w. 엔진이 NetKind로 평탄배열 vs 힙 라우팅 |

> 검토 각주: SysTask/SysFunc에 "DynMethod 1개 + method-id 인자" 안은 기각 — bump 비용이
> 동일한 이상 명시 variant가 doc-15 진단·P9 분류·코드 리뷰 전부에서 우월.

## 4. 의미론 (IEEE 1800 §7, 구현 시 오라클 라이브 필수)

- **OOB/미존재 read**: dyn/queue 범위 밖, assoc 미존재 키 → **원소-폭 X**(4-state) + 런타임
  warn(net당 1회 — 진단 폭주 방지). X/Z 인덱스 → 동일 (정적 배열 sentinel 모델 재사용).
- **OOB write**: dyn array 범위 밖 → 무시+warn. queue `q[size]` 직접 write는 IEEE상 무시(append는
  push로만). assoc write 미존재 키 → 원소 생성.
- **`new[n]`**: 기존 원소 보존 없는 형(`d = new[n]`)은 전부 X로, 복사형 `new[n](d)`는 prefix 복사.
  **n이 X/Z → 빈 배열 + warn-once; n==0은 합법-무음**(IEEE §7.5.1 — 구현 시 정정, 2026-06-11).
  n > 1<<24(=elaborate MAX_ARRAY_LEN과 동일 캡 클래스) → **경고 후 클램프**(no silent caps).
- **pop on empty**: 원소-폭 X + warn (iverilog/상용 모두 warn류 — 라이브 확인 후 핀).
- **이벤트/센스티비티**: dyn 핸들은 `@()`/wait/VCD 대상 불가 — elaborate loud 거부.
  내용 변경은 net dirty 채널에 **참여하지 않음**(조합 re-eval 트리거 없음) — 절차 코드 전용.
- **VCD**: 미덤프 — **구현됨(③)**: 두 declare 경로 모두 dyn 핸들 skip(vcd_id=None →
  initial dump·change record가 구조적으로 0). 1회 정보 진단은 보류(skip이 무해해 노이즈 판단;
  필요시 doc-07에 추가). 진단 코드 = **`VITA-W4020 W-RUN-DYN-DEGRADE`**(warn-once per net,
  doc-15 등재 — X-size new/캡 클램프/향후 OOB·empty-pop 공용).

## 5. (A) NBA delayed write — 같은 bump의 동승자

- 형상: `NonblockingAssign { lhs, rhs, delay: Option<u32> }` (ExprId — v4 런타임 delay 모델 재사용).
- 엔진: 실행 시 `d` 평가(suspension-time 규약과 동일) + RHS/인덱스는 **지금** 샘플 →
  wheel의 `t+d` NBA-region에 **값-운반 이벤트** `schedule_nba_at(t+d, lhs, value)`.
  겹침 활성화는 각자 자기 캡처 값을 운반(transport delay) — ⑤에서 정적 capture를 기각했던
  바로 그 사유의 해소. `delay: None` = 현행과 byte-동일.
- 차분: iverilog `q <= #d v` 겹침 케이스 오라클 라이브 → diff 핀. E3009 loud 제거.

## 6. 절차 — v5 bump 체크리스트 (v4 절차 재사용)

1. 형상 diff(§3) 일괄 적용 + `CURRENT_FORMAT_VERSION = 5`.
2. `REGEN_GOLDEN=1`로 canonical txt·RON registry·`.velab` corpus 재생성(스위치 기존).
3. doc-17 lowering 표 + doc-15 코드(신규 warn/error) + doc-14 trailer 문서 갱신.
4. 구현 증분 순서: ~~①bump PR~~✅(`e7f08e8`) ~~②(A) NBA-delay~~✅(`1617980`) —
   ③dyn array(**3a: heap/new/size/delete ✅ 2026-06-11** — `dyn_heap`+`DynObj`, hand-built
   SimIr 시임으로 테스트(문법은 ⑥); **잔여 3b: 인덱스 read/write 라우팅+OOB=X/무시+warn-once**)
   ④queue ⑤assoc ⑥front-end 일괄(.vu flip = (B는 완료)+(D)+(C) 문법).
   각 증분은 TDD + iverilog 라이브 오라클(§4의 warn 문구류는 hand-IEEE 핀).
5. P9/native-eval: dyn 관련 Expr/Stmt·NBA-delay는 allow-list 제외로 시작(전부 interp) —
   P5 차분 게이트가 자동으로 안전망.
