# Little Lion — Design Deep Dive (Graph & Routing Algorithms)

- Project: `015_little_lion`
- Status: Draft (extends `2026-05-18-little-lion-personal-assistant-design.md`)
- Created: 2026-05-18
- Author: SeongWook_Jang
- Reads with: 기존 design 문서 §8 (Knowledge Graph Automation), §7 (AI Routing Policy)

이 문서는 상위 design의 추상도를 한 단계 내려, 그래프·라우팅의 알고리즘과 파라미터 근거, 운영 사이클을 박제한다. 핵심 5개 섹션(§1~§5)을 깊게, 부록 3개(§6~§8)는 요약 수준으로 남긴다.

---

## §1. Atom Lifecycle State Machine

atom 노트는 vault 안에서 6개 상태를 거친다. 모든 상태는 frontmatter `state` 필드로 명시되어 외부(사람, reflection job, RAG 인덱서)가 동일하게 해석한다.

### 상태 정의

| state | 의미 | frontmatter 부속 필드 |
|------|------|---------------------|
| `draft` | LLM이 추출은 했지만 아직 vault에 박히지 않음 (메모리 상의 후보) | — |
| `published` | vault에 파일은 있지만 cross-link이 0개 (외톨이) | `created`, `assistant-touched-at` |
| `linked` | ≥ 1 outgoing link 보유. 그래프뷰에 엣지를 가진다 | `linked-count`, `last-reflected` |
| `archived` | 부적합 판정 또는 사용자 수동 표시. RAG 검색·cross-link 후보에서 제외 | `archived-at`, `archive-reason` |
| `conflicted` | writer가 `assistant-touched-at` 마커 부재 감지 → 사용자가 손댐 | `conflict-with`, `conflicted-at` |
| `merged` | 중복 atom 병합으로 흡수됨. 본문은 `## Merged from`만 남고 새 노드는 redirect | `merged-into`, `merged-at` |

### 전환 다이어그램

```
                    ┌──────────────────────────────┐
                    │                              │
   (사용자 발화)     │                              │
        │           │                              │
        ▼           │                              │
   ┌────────┐  write   ┌───────────┐  cross-link  ┌────────┐
   │ draft  │──────────▶│ published │─────────────▶│ linked │
   └────────┘           └───────────┘              └────────┘
        │                    │  ▲                     │
        │ extract            │  │ user edit           │ reflection
        │ returns None       │  │ (no marker)         │ (link removed)
        ▼                    ▼  │                     ▼
   (discarded)          ┌──────────────┐         ┌──────────┐
                        │ conflicted    │         │ archived │
                        └──────────────┘         └──────────┘
                                                     ▲
                                  duplicate merge    │
                                       ┌──────────┐  │
                              .........│  merged  │..│
                                       └──────────┘
                                       (terminal)
```

### 전환 트리거 (코드 포인트)

| 전환 | 트리거 | 구현 위치 (Phase 1a 기준) |
|----|------|----------|
| `draft → published` | `VaultWriter.write_atom()` 성공 | `backend/vault/writer.py` |
| `published → linked` | `pick_related()`가 ≥1 slug 반환 | `backend/pipeline/cross_link.py` |
| `linked → archived` | reflection job이 `quality_score < 0.3` 30일 누적 | Phase 2 `backend/jobs/reflect.py` |
| `* → conflicted` | writer가 기존 파일의 `assistant-touched-at` 마커 부재 감지 | `backend/vault/writer.py` |
| `published → merged` | duplicate detector가 cosine ≥ 0.95 + LLM "same concept" 응답 | Phase 2 `backend/jobs/dedupe.py` |
| `archived → published` | 사용자 수동 (frontmatter 편집) | — (이벤트 없음) |

### 운영 원칙

- **삭제 금지**: archived/merged도 파일은 남는다. 그래프뷰 노드는 사라지되 frontmatter `state` 조건으로 RAG에서 누락.
- **state는 단일 근원**: 다른 메타 필드들과의 모순이 생기면 `state` 우선. reconciliation 스크립트가 매주 모순 검출.
- **이름 변경 금지**: state 전환이 일어나도 슬러그/파일명은 그대로. Obsidian의 양방향 링크 보존 + git history 가독성.
- **사용자가 신뢰**: state 표시를 사람이 보고 직접 바꿀 수 있다. 모든 자동 전환은 frontmatter에 transition 이유를 동봉(`archive-reason: "30일 unlinked"`).

---

## §2. Cross-link Algorithm — 수학적 정의

상위 design은 "threshold 0.75 + LLM 가지치기 + K≤5"로 요약했다. 이 섹션은 그 수치의 출처와 score 합성 공식을 박제한다.

### Score 정규화

LanceDB가 반환하는 raw score는 L2 distance다(작을수록 가까움). 임베딩이 정규화된 벡터(nomic-embed-text는 정규화 출력)면 cosine과 다음 관계:

```
cosine(a, b) = 1 - L2(a, b)^2 / 2
```

따라서 `cosine ∈ [-1, 1]`. 임베딩 모델이 단방향(positive only) 학습이므로 실무 분포는 `[0, 1]`.

### Hybrid Score

벡터 검색만으로는 동의어·약어 누락이 잦다. BM25를 가중 합성:

```
hybrid(q, d) = α · vec_score(q, d) + (1 − α) · bm25_norm(q, d)
```

- `vec_score = 1 − L2 / max_L2_in_topK` (LanceDB raw → [0,1] 정규화)
- `bm25_norm = bm25_raw / max_bm25_in_topK` (max 1로 정규화)
- `α = 0.7` (벡터 우선, BM25는 정확 매칭 보강 역할)

α=0.7은 휴리스틱이지만 근거:
- 한국어 vault에서 BM25는 어형변화로 recall이 낮다 (예: "라우터"/"라우팅" 별개 토큰).
- nomic-embed-text 같은 다국어 임베딩은 한국어 어형변화에 견고.
- 따라서 벡터를 메인, BM25를 "동의어 백업"으로 가중.

### Cross-link 결정 흐름

새 atom A를 vault에 박을 때:

```
Input: A (title, body, embedding e_A)
Output: links ⊆ vault atoms, |links| ≤ K

1. candidates = LanceDB.search(e_A, k=20)        # 후보 over-fetch
2. filtered  = [c for c in candidates
                  if hybrid(A, c) ≥ τ_link]      # τ_link = 0.75
3. if len(filtered) == 0:
       return []
4. picks = LLM_gate(A, filtered, k_max=K)        # K = 5
5. links = picks ∩ {c.slug for c in filtered}    # 환각 제거
6. for slug in links:
       linker.link_bidirectional(A, vault[slug]) # A↔B 양쪽 ## Related 갱신
   return links
```

### 파라미터 근거

| 파라미터 | 값 | 근거 |
|---------|-----|-----|
| `top_k_candidates` | 20 | k=10이면 LLM gate가 잘 거를 후보 자체가 부족, k=50은 LLM 토큰 낭비. 20이 sweet spot. |
| `τ_link` | 0.75 | 정규화 cosine 기준 "확실히 같은 주제"의 경험적 하한. < 0.6은 잡노이즈, ≥ 0.85는 거의 중복. |
| `K_final` | 5 | Obsidian 그래프뷰 시각 가독성 한계(5개 이상 엣지부터 노드 거미줄). |
| `α (hybrid)` | 0.7 | 위 한국어 어형변화 분석 |

### Threshold 재보정 절차 (Phase 2)

τ_link=0.75는 초기값. 데이터 수집 후 자동 calibration:

1. 매주 일요일 — 지난 7일에 만들어진 cross-link 중 무작위 100쌍 sampling
2. 각 쌍에 대해 reflection LLM(qwen2.5:14b)이 "good/bad" 자동 라벨 (사람이 가끔 검수)
3. τ를 0.65~0.85 범위에서 스윕, F1 score 최대화하는 τ를 다음 주 적용
4. τ가 한 번에 ±0.05 이상 변하면 알림 (모델 드리프트 의심)

이 calibration은 **Phase 1에 미구현, Phase 2 추가**. Phase 1 동안은 사용자가 weekly review에서 잡노이즈를 보고 직접 τ를 환경변수로 조정.

### Reflection 주기 (그래프 건강도)

매주 일요일 03:00 KST에 cron으로 모든 `state ∈ {published, linked}` atom 대상:

1. **거리 재계산** — 본문이 7일 내 변한 atom에 대해 임베딩 재생성, outgoing link 양쪽 hybrid score 재계산.
2. **수상한 링크 후보** — hybrid가 0.85 이상 멀어진(`prev - current > 0.85·prev`) 링크 → 의심 마크.
3. **LLM verifier** — 의심 후보 쌍을 qwen2.5:14b에 (제목+요약 200자) 입력, "여전히 의미적으로 연결되나? yes/no + 한 줄 이유" 요청.
4. **링크 제거** — "no" 응답인 링크만 `## Related`에서 제거 + 양쪽 frontmatter에 `unlinked-at: <ts>` 박음.
5. **trace 저장** — 결과를 `_traces/reflection-<date>.md`로 보존.

→ 한 atom의 link가 30일간 0으로 떨어지고 quality_score < 0.3이면 weekly review 알림 큐에 추가 (자동 archive 아님 — 사람 확인).

---

## §3. Routing Decision Tree — 확장판

상위 design의 라우팅 표는 7행이었다. 실무에선 **규칙 33개 → 0.5b classifier → scorer**의 3단 캐스케이드로 확장한다.

### Stage 1 — Rule Patterns (33 regex/heuristic)

규칙은 **확실히 잡을 수 있는 신호만** 박는다. 잡으면 즉시 카테고리 + need_rag/need_web 결정, classifier 건너뜀.

```python
RULES: list[Rule] = [
    # ─── code (8) ───
    Rule(r"```", "code", need_rag=True, need_web=False),
    Rule(r"\b(def|class|import|return|async|await|yield)\b", "code", True, False),
    Rule(r"[a-zA-Z_/.]+\.(py|ts|tsx|js|jsx|swift|md|yaml|yml|json|sh|toml)\b", "code", True, False),
    Rule(r"\b(backend|frontend|src|tests|scripts)/", "code", True, False),
    Rule(r"\b(stack trace|traceback|exception|error log)\b", "code", True, False),
    Rule(r"리팩토링|버그|코드 ?리뷰|디버그", "code", True, False),
    Rule(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\w", "code", True, False),
    Rule(r"\b(typehint|타입 ?힌트|시그니처)\b", "code", True, False),

    # ─── web (5) ───
    Rule(r"https?://", "web", False, True),
    Rule(r"\b(오늘|어제|최근|지금|요즘|현재)\b", "web", False, True),
    Rule(r"\b(latest|today|yesterday|news|breaking)\b", "web", False, True),
    Rule(r"\b(주가|환율|시세|가격)\b", "web", False, True),
    Rule(r"\b(weather|날씨)\b", "web", False, True),

    # ─── rag (6) ───
    Rule(r"vault|볼트", "rag", True, False),
    Rule(r"내 ?(노트|메모|기록)", "rag", True, False),
    Rule(r"\b(atom|MOC|wiki)\b", "rag", True, False),
    Rule(r"검색해|찾아|모아|정리해", "rag", True, False),
    Rule(r"전에 (말|얘기)했(었)?(는데|던)", "rag", True, False),
    Rule(r"지난주|지난달|작년", "rag", True, False),  # 시간이지만 vault에 있는 본인 기록

    # ─── reasoning (4) ───
    Rule(r"^.{120,}", "reasoning", True, False),       # 120자 이상 = 긴 질문
    Rule(r"\?[^?]*\?", "reasoning", True, False),       # 의문문 2개 이상
    Rule(r"\b(왜|어떻게|분석|설명|비교)\b", "reasoning", True, False),
    Rule(r"\b(why|how|analyze|explain|compare)\b", "reasoning", True, False),

    # ─── schedule (3, Phase 2 활성) ───
    Rule(r"오늘 ?일정|내일 ?일정|일정", "schedule", False, False),
    Rule(r"할 ?일|todo|task", "schedule", False, False),
    Rule(r"\b(미팅|회의|약속|점심|저녁)\b", "schedule", False, False),

    # ─── greeting / default (3) ───
    Rule(r"^\s*(안녕|hi|hello|hey|반가워)\b", "default", False, False),
    Rule(r"^.{1,12}$", "default", False, False),       # 12자 미만 = 잡담 가능성
    Rule(r"고마워|감사", "default", False, False),

    # ─── 명시적 모델 호출 (4) ───
    Rule(r"^/claude\b", "_force_claude", False, False),
    Rule(r"^/gemini\b", "_force_gemini", False, False),
    Rule(r"^/local\b", "_force_local", False, False),
    Rule(r"^/code\b", "code", True, False),
]
```

규칙 우선순위: 위에서 아래로 OR. 첫 매치가 승리. `_force_*`는 사용자가 명시적으로 모델 강제 — 라우터 cascade를 우회하고 Stage 3 scorer를 건너뛴다.

### Stage 2 — Classifier (qwen2.5:0.5b)

규칙으로 못 잡은 쿼리만 0.5b 모델이 분류. 0.5b는 매우 가볍고(8GB RAM에서도 100ms 이내), JSON mode 강제로 환각 최소화.

System prompt (영구 박제):
```
You are a query classifier for a personal assistant. Given a Korean/English query, output ONLY a JSON object:
{"category": "code"|"web"|"rag"|"reasoning"|"schedule"|"default",
 "need_rag": true|false,
 "need_web": true|false,
 "confidence": 0.0~1.0}
No prose, no explanation. If unsure, return category="default" with confidence ≤ 0.5.
```

User template:
```
Query: {query}
JSON:
```

운영 규칙:
- `confidence < 0.6` → 강제 `default` + RAG 사용 (보수적)
- JSON 파싱 실패 3회 → 영구 fallback `default`
- 응답 latency > 500ms 5번 연속 → 모델 unload 후 재로딩 알림

### Stage 3 — Scorer (모델 선택)

카테고리와 입력 토큰을 받아 **점수 최대 모델**을 고른다. 점수:

```
score(m | category) = α_c · quality(m, c) + β_c · speed(m) − γ_c · cost(m)
```

각 모델의 (quality_general, speed, cost) 상수표 (1~10 정규화):

| 모델 | quality | speed | cost | 한국어 보너스 | 코드 보너스 |
|------|---------|-------|------|--------------|-----------|
| claude-opus | 10 | 3 | 10 | +1 | +1 |
| claude-sonnet | 9 | 6 | 6 | +1 | +1 |
| claude-haiku | 7 | 9 | 2 | +0.5 | 0 |
| gemini-pro | 9 | 5 | 5 | 0 | 0 |
| gemini-flash | 7 | 8 | 1 | 0 | 0 |
| qwen2.5:14b | 7 | 7 | 0 | +1 | +0.5 |
| qwen2.5-coder:7b | 6 | 8 | 0 | 0 | +2 |
| qwen2.5:0.5b | 3 | 10 | 0 | 0 | 0 |

카테고리별 (α, β, γ):

| category | α (품질) | β (속도) | γ (비용) | 비고 |
|---------|--------|---------|--------|-----|
| reasoning | 1.0 | 0.2 | 0.5 | 품질 최우선 |
| code | 0.7 | 0.5 | 0.6 | 균형 |
| rag | 0.5 | 1.0 | 0.8 | 빠르고 무료 우선 |
| web | — | — | — | **gemini-flash 강제** (grounding 필요) |
| schedule | 0.5 | 1.0 | 0.5 | 무료/빠름 |
| default | 0.8 | 0.5 | 0.5 | 품질 |

**입력 토큰 분기**:
- `input_tokens > 100_000` → `claude-opus` 강제 (1M ctx)
- `input_tokens > 30_000` → opus / sonnet 후보로만 제한

**Fallback**:
- 1차 모델 호출 2초 timeout → 2차 모델(점수 2위)로 전환
- 2차도 timeout → "모델 응답 지연, 잠시 후 다시" 응답 + 사용자 trace에 실패 기록
- Phase 3에서 Telegram 알림 추가

**비용 카운터 (Phase 2)**:
- 응답마다 `(provider, model, input_tok, output_tok)`를 `data/usage.jsonl`에 append
- 일별 한도(예: Claude $5, Gemini $1) 초과하면 자동으로 `cost` 가중치를 일시 +5 (해당 모델 사실상 제외)
- 매일 자정 리셋

---

## §4. Memory Reflection & Graph Hygiene

§2에서 reflection을 짧게 언급했지만 이 섹션이 정식 정의다. **목표: 그래프가 시간이 지나도 의미를 유지하도록 자가 정비.**

### Reflection Job Catalogue

| job | 주기 | 입력 | 출력 | 사람 개입 |
|-----|------|------|------|---------|
| **link-decay** | 주 1 (일요일 03:00) | `state ∈ {linked}` atom 전체 | 잘못된 링크 제거 + `unlinked-at` 박음 | 자동 |
| **dedupe** | 주 1 (월요일 03:00) | 임베딩 cosine ≥ 0.95 쌍 | `merged` 상태 전환 + redirect | LLM 판정, 사람 검수 알림 |
| **moc-propose** | 주 1 (화요일 03:00) | clustering 결과 | `_proposals/MOC-*.md` | 사람 승인 후 적용 |
| **archive-review** | 월 1 (1일 03:00) | 30일 unlinked + score < 0.3 | weekly review 알림 큐 | 사람이 archive 결정 |
| **threshold-calibrate** | 주 1 (일요일 04:00) | 지난 주 cross-link 100 sample | 새 τ_link 값 | 자동, ±0.05 초과 시 알림 |

### link-decay 상세

```
for atom in vault.atoms(state in {linked}):
    if atom.body_mtime > now - 7d:
        atom.embedding = embed(atom.body)
    for link in atom.outgoing_links:
        target = vault[link.slug]
        if target is None or target.state == "archived":
            atom.remove_link(link.slug)
            continue
        prev = link.score_at_creation
        curr = hybrid(atom, target)
        if prev - curr > 0.85 * prev:    # 85% 이상 감소
            verdict = llm_verify(atom, target)
            if verdict == "no":
                atom.remove_link(link.slug)
                target.remove_link(atom.slug)
                trace.add({"atom": atom.slug, "removed": link.slug, "reason": verdict.reason})
trace.save_to("_traces/reflection-{date}.md")
```

LLM verifier 프롬프트 (영구 박제):
```
두 노트가 의미적으로 진짜 연결되는지 판정해.

[A] {a_title}
{a_body[:300]}

[B] {b_title}
{b_body[:300]}

JSON으로만:
{"connected": true|false, "reason": "한 줄"}
```

### dedupe 상세

1. LanceDB에서 모든 atom 임베딩을 가져와 코사인 페어 매트릭스 (≤ 10k atom 가정에서 100MB 메모리 OK)
2. cosine ≥ 0.95 쌍을 후보 큐에 적재
3. 각 쌍을 qwen2.5:14b에 (제목+요약 300자씩) 주고 "이 둘이 같은 개념인가? yes/no + 한 줄 이유"
4. "yes"면:
   - 더 오래된 atom을 base
   - 새 atom 본문을 base의 `## Merged from` 섹션에 흡수
   - 새 atom은 `state: merged`, `merged-into: <base-slug>`만 남기고 본문은 짧은 redirect 문구
   - base의 outgoing/incoming link는 그대로, 새 atom으로의 외부 링크도 base로 redirect (다음 RAG 인덱싱 시 자동)

→ 사용자가 매일 1회 Telegram으로 "이번 주 자동 병합 N개" 요약 받음(Phase 2).

### moc-propose 상세

단일 연결(single-linkage) hierarchical clustering으로 atom 그룹화:

1. 임베딩 cosine 0.7 cut → 클러스터들
2. 각 클러스터 중 크기 ≥ 5 + 기존 MOC와의 atom 중복 < 30% 인 것 = MOC 후보
3. LLM(qwen2.5:14b)에 클러스터 atom 제목들 주고 "이들의 공통 주제 한 줄 + 슬러그(영문 케밥) 제안" 요청
4. `_proposals/MOC-<topic>.md` 파일 생성:
   ```markdown
   ---
   type: moc-proposal
   suggested-by: reflection-2026-06-07
   atoms-count: 12
   ---

   # 제안: MOC — Trading Bot Architecture

   포함 atom (12):
   - [[atom-1]] (cosine 0.84)
   - [[atom-2]] (cosine 0.82)
   ...

   승인하려면 이 파일을 `MOC/MOC-trading-bot-architecture.md`로 이동하세요.
   ```
5. 사용자가 이동/리네임하면 적용. 4주간 무이동이면 `_proposals/` 안에서 자동 삭제.

### archive-review 알림 큐

- 큐는 vault의 `assistant/_review-queue.md` 한 파일
- 매월 1일 03:00에 다음 조건 atom을 큐에 append:
  - 30일 동안 incoming/outgoing link 변화 0
  - quality_score < 0.3 (Phase 2의 quality signal — §6에서 부록 처리)
  - mention-count < 2

사용자는 vault 안에서 `_review-queue.md`를 열고 각 atom 옆 체크박스로 archive 여부 결정. 다음 주기에 비서가 그 결정을 반영.

---

## §5. Explainability & Decision Trace

비서의 모든 답변은 **재현 가능한 trace**를 동봉한다. 디버깅·신뢰·학습 모두 이 trace에서 출발한다.

### Trace 데이터 구조

응답 JSON:

```json
{
  "answer": "라우터는 규칙 33개 → 0.5b 분류기 → scorer 3단으로...",
  "session_id": "2026-05-18T14-23-12-a4b9",
  "atom_slug": "router-cascade-3-stage",
  "trace": {
    "stt": {
      "engine": "mlx-whisper",
      "model": "mlx-community/whisper-large-v3-mlx",
      "input_bytes": 184320,
      "text": "라우터 구조 설명해줘",
      "lang": "ko",
      "duration_ms": 320
    },
    "router": {
      "stage1_rule": {"matched": null, "checked": 33},
      "stage2_classifier": {
        "model": "qwen2.5:0.5b",
        "raw_output": "{\"category\":\"rag\",\"need_rag\":true,\"need_web\":false,\"confidence\":0.78}",
        "parsed": {"category": "rag", "need_rag": true, "need_web": false},
        "confidence": 0.78,
        "duration_ms": 87
      },
      "stage3_scorer": {
        "category": "rag",
        "input_tokens": 8,
        "candidates": {
          "qwen2.5:14b": {"score": 8.4, "quality": 7, "speed": 7, "cost": 0, "ko_bonus": 1},
          "claude-haiku": {"score": 6.2, "quality": 7.5, "speed": 9, "cost": 2, "ko_bonus": 0.5},
          "claude-sonnet": {"score": 5.9, "quality": 10, "speed": 6, "cost": 6, "ko_bonus": 1}
        },
        "chosen": "qwen2.5:14b",
        "reason": "category=rag → speed/cost 가중치 우위"
      },
      "decided_at_stage": 3
    },
    "policy": {
      "offline_mode": false,
      "provider": "ollama",
      "action": "allow",
      "redacted_paths": []
    },
    "rag": {
      "query_embedding_ms": 42,
      "search_ms": 18,
      "hits": [
        {"path": "atoms/litellm-router-pattern.md", "vec_score": 0.86, "bm25_score": 0.71, "hybrid": 0.82},
        {"path": "atoms/policy-gate-design.md", "vec_score": 0.74, "bm25_score": 0.40, "hybrid": 0.64}
      ],
      "passed_threshold": 1,
      "used_in_prompt": 1
    },
    "llm": {
      "provider": "ollama",
      "model": "qwen2.5:14b",
      "input_tokens": 1234,
      "output_tokens": 312,
      "duration_ms": 4200,
      "stop_reason": "end_of_sequence"
    },
    "atom_extraction": {
      "model": "qwen2.5:14b",
      "extracted": {"title": "Router Cascade 3-Stage", "tags": ["router", "architecture"]},
      "skipped": false
    },
    "cross_link": {
      "candidates_count": 18,
      "passed_threshold": 9,
      "llm_picked": 4,
      "linked": ["litellm-router-pattern", "policy-gate-design", "qwen-0-5b-classifier", "obsidian-graph-as-memory"]
    },
    "vault_writes": [
      "assistant/atoms/router-cascade-3-stage.md",
      "assistant/atoms/litellm-router-pattern.md",
      "assistant/atoms/policy-gate-design.md",
      "assistant/atoms/qwen-0-5b-classifier.md",
      "assistant/atoms/obsidian-graph-as-memory.md",
      "assistant/sessions/2026-05-18T14-23-12-a4b9.md",
      "assistant/daily/2026-05-18.md"
    ],
    "total_duration_ms": 4881
  }
}
```

### 저장 정책

- **응답 JSON에 trace 포함** — PWA에서 접기/펴기로 표시
- **vault에 trace 보존** — `assistant/_traces/<session_id>.json` 별도 파일. atom의 frontmatter에 `trace: _traces/<sid>.json` backref
- **trace 파일은 인덱싱 제외** — `_traces/` 는 `_SKIP_DIRS`에 추가, RAG에 노이즈 안 됨
- **보관 주기** — 90일 후 자동 압축(`_traces/archive/YYYY-MM.tar.gz`), 1년 후 삭제

### UX (PWA)

- 답변 카드 하단에 "Why this answer?" 토글 — 4줄 요약 표시:
  ```
  • Route   : qwen2.5:14b (rag category, score 8.4)
  • RAG     : 2 hits, 1 used (litellm-router-pattern, hybrid 0.82)
  • Latency : 4.9s total (stt 320ms · router 87ms · llm 4.2s)
  • Atoms   : 1 new (router-cascade-3-stage), 4 cross-linked
  ```
- "Show full trace" 클릭 → JSON syntax-highlighted 전체 표시
- 디버그 모드(`?debug=1`)에서 trace를 즉시 펼침

### 사후 학습 기반

trace는 다음 작업의 입력:
- threshold-calibrate job (§4): cross_link.passed_threshold + 사용자 archive 결정으로 τ 재학습
- routing-bench job (Phase 3): stage3_scorer.chosen vs 사용자 만족도(feedback API)로 가중치 α/β/γ 미세조정
- cost dashboard (Phase 2): llm.input_tokens × cost로 일별 비용 그래프

→ **trace 없이는 자가개선 불가**. Phase 1a 시점부터 trace를 반드시 박는 이유.

---

## §6. Conversational Coherence (부록)

- 같은 세션 안에서는 직전 N=3 turn의 (user, assistant) 텍스트를 system prompt에 슬라이딩 윈도우로 포함
- vault의 `assistant/daily/<오늘>.md` 본문을 RAG 컨텍스트로 항상 동봉 (사용자가 오늘 이미 본 내용 잇기)
- 세션 종료 후 7일 지나면 daily MOC reflection이 turn 시퀀스를 1문단 요약으로 압축 → 장기 검색 가능

윈도우 정책 결정 사유: 무한 누적은 토큰 폭증 + 일관성 흐려짐. 3 turn은 한 "주제 단위" 평균 길이. 그 이상은 vault로.

## §7. Inter-project Knowledge Integration (부록)

violet_sw의 005~014 프로젝트들은 이미 obsidian-sync 스킬로 vault에 다음을 동기화 중:
- `violet_sw/projects/{프로젝트}/` 디렉토리에 프로젝트별 노트
- `violet_sw/lessons/` 에 실패 사례, `feedback/`, `knowledge/` 등

Phase 3에서 이 컬렉션을 별도 LanceDB 컬렉션 `vault_projects`로 인덱싱:
- 라우터에 새 카테고리 `project_query` 추가 — 트리거 단어 ("캐스퍼봇", "007 봇", "어제 거래", "<코인> 시그널")
- 매치 시 RAG가 `vault_projects` 컬렉션 우선 검색
- 답변 후 atom은 별도 `assistant/atoms/projects/<프로젝트>/` 디렉토리에 박혀 본인 지식과 프로젝트 지식 분리

예: 사용자 발화 "캐스퍼봇이 어제 왜 졌어?"
- Stage 1 rule: "캐스퍼봇" → category=project_query
- RAG: `vault_projects` 컬렉션 + 최근 7일 거래 로그 limit
- LLM: claude-sonnet (긴 reasoning + 한국어)
- atom: `assistant/atoms/projects/014_casper/2026-05-17-loss-analysis.md`로 박힘

## §8. Failure Modes & Graceful Degradation (부록)

| # | 시나리오 | 대응 |
|---|---------|-----|
| 1 | Ollama 다운 | 라우터 cascade가 cloud로 강제 fallback. 1분 후 헬스체크 재시도 |
| 2 | Claude/Gemini 401 | 토큰 만료 알림 + 로컬 강등. 사용자에게 키 갱신 요청 |
| 3 | mlx-whisper 모델 로드 실패 | "음성 인식 불가, 텍스트로 입력해줘" + STT 자동 비활성 |
| 4 | vault 경로 권한 거부 | 헬스체크가 사전 차단 → 백엔드 부팅 실패 + 명확한 에러 로그 |
| 5 | iCloud sync 지연 | fswatch 5분 timeout, 그 사이 변경된 파일은 다음 sweep에서 흡수 |
| 6 | 임베딩 차원 변경 (모델 업그레이드) | `scripts/rebuild_index.py` 마이그레이션 — 기존 DB 백업 후 전체 재인덱싱 |
| 7 | 동일 질문 반복 (atom 폭주) | 직전 5분 안 cosine ≥ 0.98 발화 → 새 atom 생성 안 함, 기존 atom의 `mention-count` 증가 |
| 8 | cross-link 순환 (A↔B↔C↔A) | BFS depth 4 제한, 순환 감지 시 마지막 링크만 추가 |
| 9 | PWA 토큰 유출 | Phase 1c에 토큰 회전 스크립트 — env 변경 + 모든 활성 WS 재연결 강제 |
| 10 | 라우터 cascade 무한 (classifier가 'unknown') | 무조건 default로 강등 |
| 11 | Daily MOC 거대화 | 50개 atom embed 초과 시 자동 분할 (`daily/<date>-1.md`, `-2.md`) |
| 12 | LanceDB 손상 | 주간 snapshot (`data/lancedb-backup-YYYY-MM-DD.tar.gz`) 자동 복원 명령 |
| 13 | STT 한국어 오인식 폭주 | "방금 뭐라고?" 패턴이 5턴 연속 시 비서가 "느린 모드로 전환할까?" 제안 |

---

## 변경 사항이 상위 design에 미치는 영향

이 deep-dive로 인해 상위 design 문서를 갱신해야 할 것:

1. §6 Components에 `policy` 모듈 외에 `trace` 모듈, `reflection` 모듈 추가 (Phase 2)
2. §10 Phase 1 검증 게이트에 **"응답 JSON에 trace.router.stage3_scorer가 존재한다"** 추가
3. §11 Directory Structure에 `backend/jobs/` (reflection 모듈), `assistant/_traces/`, `assistant/_proposals/` 추가
4. §13 Open Questions에서 "TTS Phase1을 macOS say로" 항목은 결정됨 (macOS say) — 제거 가능

Plan 1a (Backend) 영향:
- Task 14 (Router)는 33개 규칙 + Stage 3 scorer 둘 다 구현해야 함 → 1개 task가 아니라 **Task 14a (rules), 14b (classifier), 14c (scorer)** 3개로 분리 필요
- Task 19 (`/chat` 엔드포인트)의 응답 스키마에 `trace` 필드 추가 — `ChatResponse` 모델 확장
- Task 22 (Indexer script)에 `_traces`, `_proposals`, `_review-queue.md` 제외 디렉토리 추가

→ Plan 1a를 이 deep-dive에 맞춰 미세 조정해야 함 (다음 작업).
