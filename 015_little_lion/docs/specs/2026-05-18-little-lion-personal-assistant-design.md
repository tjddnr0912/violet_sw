# Little Lion — Personal AI Assistant Design

- Project: `015_little_lion`
- Status: Draft (design approved, pre-implementation)
- Created: 2026-05-18
- Author: SeongWook_Jang
- Successor doc: `docs/specs/2026-05-18-little-lion-phase1-plan.md` (to be written by writing-plans skill)

## 1. Vision (one-line)

Mac M1 Max를 항상 켜진 두뇌 서버로, Obsidian vault를 장기 기억 + 그래프 시각화 표면으로, PWA를 어디서든 같은 비서를 부르는 얇은 클라이언트로 두는 통합 개인 비서.

**핵심 발상**: 비서가 답을 만들 때마다 vault에 atom 노트와 wiki-link를 박는 것이 곧 Obsidian 그래프뷰에 영화 같은 연결성을 자라게 한다. 별도 그래프 엔진을 만들지 않는다.

## 2. Goals & Non-Goals

### Goals (이 디자인이 다루는 것)
- 음성(Push-to-Talk) + 채팅 양쪽으로 동작하는 통합 비서
- vault 기반 RAG로 사용자의 기존 지식 위에서 답함
- 답할 때마다 vault에 atom + cross-link를 자동 생성 (영화 같은 그래프)
- Mac 데스크와 외부(폰/노트북)에서 같은 비서 접속
- 작업별로 Claude / Gemini / 로컬 LLM을 자동 선택 (비용·프라이버시·품질 균형)
- 1인 사용 전제

### Non-Goals (YAGNI)
- 자체 그래프 시각화 엔진 (Obsidian에 위임)
- LLM fine-tuning / 학습형 라우터
- LangChain/LlamaIndex 같은 무거운 추상화
- 자동 토픽 발견 / 자동 MOC 생성 (사람이 키운다)
- 슬랙/이메일/노션 등 외부 메신저 통합 (Phase 3 이후만 검토)
- 멀티 사용자 / 권한 시스템

## 3. Hardware & Constraints

- Apple MacBook Pro M1 Max, 32GB 통합 메모리
- 동시 로드 LLM ≤ 2개 (Whisper Large-v3 ≈ 10GB + qwen2.5:14b ≈ 9GB 동시 가능, idle 5분 unload)
- 1인 사용, 단일 사용자 전제
- vault는 iCloud로 동기화됨 → 동시 쓰기 충돌 고려 필요

## 4. System Architecture

```
┌──────────────── Mac M1 Max (always-on) ──────────────────┐
│                                                          │
│  ┌─ Backend  (Python / FastAPI : 8765) ────────────────┐ │
│  │   STT     : mlx-whisper (Large-v3, Apple MLX)      │ │
│  │   Router  : LiteLLM + 규칙 + 0.5b 분류기            │ │
│  │   RAG     : LanceDB + nomic-embed (Ollama)         │ │
│  │   Writer  : Markdown atom + [[wiki-link]] inserter │ │
│  │   Watcher : fswatch on vault → re-embed delta      │ │
│  │   TTS     : macOS `say` (Phase1) → Coqui (Phase2)  │ │
│  │   Policy  : 클라우드 LLM 호출 공통 게이트            │ │
│  │   API     : REST + WebSocket (audio stream)        │ │
│  └────────────────────────────────────────────────────┘ │
│         │                              │                 │
│  ┌──────▼──────────┐          ┌────────▼─────────────┐  │
│  │ Ollama :11434   │          │ Obsidian Vault       │  │
│  │  qwen2.5:14b    │          │ (iCloud, passive)    │  │
│  │  qwen-coder:7b  │          │   violet_sw/         │  │
│  │  qwen2.5:0.5b   │          │   assistant/        ←─── 비서 자동 생성
│  │  nomic-embed    │          │     atoms/           │  │
│  └─────────────────┘          │     daily/           │  │
│         ▲                     │     sessions/        │  │
│         │ HTTP                │     MOC/             │  │
│  ┌──────┴──────────┐          └──────────────────────┘  │
│  │ Claude API,     │                                     │
│  │ Gemini API      │                                     │
│  └─────────────────┘                                     │
│                                                          │
│  Remote: Tailscale (default) / Cloudflare Tunnel (opt.)  │
└──────────────────────▲───────────────────────────────────┘
                       │ HTTPS (private)
              ┌────────┴────────┐
              │  PWA Client     │  any browser, no install
              │  /chat  /graph  │
              │  mic = PTT      │
              └─────────────────┘
```

## 5. End-to-End Data Flow (지식 쿼리 시나리오)

1. 사용자가 PWA의 마이크 버튼(PTT)을 누르고 발화한다.
2. 브라우저가 `MediaRecorder`로 오디오를 캡처해 WebSocket으로 Mac 백엔드에 청크 스트림.
3. 백엔드 `stt` 모듈이 mlx-whisper(Large-v3)로 한국어/영어 자동 감지 + 텍스트화.
4. `router`가 쿼리 분류: RAG 필요 여부, 긴 reasoning 여부, 웹 grounding 필요 여부, 코드 여부.
5. `rag`가 LanceDB에서 vault 임베딩 top-K 청크 검색.
6. `policy` 게이트를 통과시켜 (오프라인 모드 / `local-only` 노트 redaction 체크) → 선택된 LLM에 (질문 + RAG context) 호출.
7. `vault_writer`가 응답에서 atom 후보를 추출, threshold + LLM 가지치기를 통과한 K ≤ 5개의 기존 노트와 양방향 cross-link.
8. Obsidian이 파일 변경을 감지 → 그래프뷰에 새 노드/엣지가 자동 출현.
9. PWA에 텍스트 응답 + (옵션) TTS 음성 재생.

## 6. Component Responsibilities

| 모듈 | 책임 | I/O | 의존 |
|------|------|-----|------|
| `stt` | 음성 → 텍스트 | `bytes(audio)` → `{text, lang, ts}` | mlx-whisper |
| `router` | 쿼리 분류 + 모델 선택 | `text` → `{provider, model, system_prompt, need_rag, need_web}` | qwen2.5:0.5b + rules |
| `rag` | vault 검색 | `(query, k)` → `list[{path, score, excerpt}]` | LanceDB, nomic-embed |
| `llm_client` | 통합 LLM 호출 | `(provider, model, messages)` → `stream[token]` | LiteLLM |
| `vault_writer` | 노트/링크 생성 | `{title, body, tags, links_to[]}` → `path` | fs (atomic rename) |
| `vault_watcher` | vault 변경 감지 | fs event → re-embed task | fswatch |
| `session` | 대화 상태 + 영속화 | `turn` → `session_id, daily_md_path` | vault_writer |
| `policy` | 프라이버시 게이트 | `(text, target_provider)` → `allow / deny / redact` | regex + frontmatter |
| `api` | PWA ↔ 백엔드 | REST + WebSocket | FastAPI, 토큰 인증 |
| `frontend` | PWA UI (chat + PTT) | — | Vite + TS + PWA manifest |

설계 원칙:
- 모든 모듈은 함수 호출로만 결합한다 (전역 상태 금지). 단위 테스트가 곧 격리 테스트.
- `policy`가 모든 클라우드 LLM 호출의 단일 진입점이어야 한다. redaction을 한 군데에서만 진화시키기 위해.

## 7. AI Routing Policy

| 쿼리 유형 (감지 규칙) | 1차 모델 | Fallback | 이유 |
|---------|---------|---------|------|
| 임베딩 인덱싱 | `nomic-embed-text` (local) | — | 비용 0, 프라이버시 |
| 짧은 RAG 답변 (≤ 3문장, ctx ≤ 4k) | `qwen2.5:14b` (local) | Claude Haiku | 빠름, 무료 |
| 긴 reasoning / 한국어 톤 / 글쓰기 | Claude Sonnet | qwen2.5:14b | 한국어 자연스러움 + 추론 |
| 매우 긴 컨텍스트 (> 100k tok) | Claude Opus 1M | — | 1M ctx 활용 |
| 웹 grounding 필요 ("최근", "오늘", URL) | Gemini 2.5 Flash + grounding | Claude + 직접 검색 도구 | grounding 내장 |
| 코드 질문 (정규식: 파일경로/`def `/```) | `qwen2.5-coder:7b` (local) | Claude Sonnet | 가벼움 우선 |
| 음성 STT | `mlx-whisper large-v3` (local) | — | 프라이버시 |
| TTS | macOS `say` (Phase1) | Coqui XTTS / ElevenLabs (Phase2) | 무료/즉시 |

라우터 구조: **규칙(정규식) → 0.5b 분류 모델 → 디폴트** 3단 캐스케이드. 학습형 라우팅은 안 한다.

프라이버시 토글:
- 노트 frontmatter `local-only: true` → 절대 클라우드 LLM에 본문 전달 금지 (`policy`가 redact).
- 전역 "오프라인 모드" 스위치 → 모든 호출을 로컬로 강제.
- 응답 메타에 `{model, why}` 항상 노출 (어떤 모델이 답했는지 즉시 확인 가능).

## 8. Knowledge Graph Automation (Core of "영화 같은 연결성")

### 원리
- Obsidian 그래프 = `[[wiki-link]]`가 엣지, `.md`가 노드.
- 비서가 답할 때마다 `(a) 새 노드 (b) 관련 K개와 엣지`를 잇는다.
- `obsidian-sync` 스킬이 쓰는 디렉토리 컨벤션(atoms/, projects/, knowledge/)을 그대로 재사용해 한 vault 안에서 일관된 그래프 유지.

### vault 안의 4가지 노트 종류
```
assistant/
├─ atoms/              # 원자 지식 노트 (한 개념 = 한 파일)
├─ daily/              # 하루 단위 대화 로그 + atom embed
├─ sessions/           # 한 대화 세션 raw 기록
└─ MOC/                # Map of Content (사람이 키우는 큰 묶음 인덱스)
```

### Atom 노트 템플릿
```markdown
---
type: atom
created: 2026-05-18T14:23
tags: [ai/router, infra/litellm]
local-only: false
source: sessions/2026-05-18T14-23.md
embed-hash: <sha1>
---

# LiteLLM Router Pattern

작업 유형별로 Claude/Gemini/Ollama 통합 호출. 단일 진입점.

## Related
- [[obsidian-graph-as-memory]]
- [[ko-stt-whisper-large]]
- [[MOC-ai-infra]]
```

### Cross-link Algorithm
1. 새 atom 본문을 임베딩 → LanceDB에서 top-20 후보.
2. 임베딩 점수 필터: `cosine ≥ 0.75` 통과만.
3. LLM second pass — 후보 20개의 제목/요약을 주고 "정말 의미적으로 연결되는 것 5개 이내"로 가지치기 (임베딩만으론 잡노이즈).
4. 양방향 업데이트 — A→B, B→A 둘 다 `## Related`에 `[[link]]` 삽입.
5. 1주일 후 reflection job 재실행해 부적합 링크 제거.

설계 결정:
- K ≤ 5 고정. 그 이상은 그래프뷰가 시각적으로 무너진다.
- threshold + LLM 가지치기 둘 다 사용 (둘 중 하나만 쓰면 잡노이즈 OR 누락).
- MOC는 사람이 키운다 — 비서는 MOC에 추가만 하고 생성/제목은 사용자가 결정.

### 안전 장치
- **iCloud 동시 쓰기 충돌**: 모든 쓰기는 `tmp → fsync → rename` 원자적. 사용자가 같은 파일 편집 중이면 `assistant-touched-at` frontmatter를 보고 충돌 시 `-conflict-N.md`로 별도 저장.
- **삭제 금지**: 비서는 vault 파일을 절대 삭제하지 않는다. 잘못된 atom은 `archived: true` 표시만.
- **이름 변경 회피**: 비서가 만든 노트 이름은 가급적 유지 (슬러그 = ID).
- **local-only 노트 redaction**: RAG 검색 결과로는 나오지만 클라우드 LLM 호출 시 제목+태그만 컨텍스트로 전달.

## 9. Remote Access & Security

- 1차: **Tailscale** (사설 IP, 디바이스 추가만 하면 즉시 접속).
- 2차 (선택): Cloudflare Tunnel — 공유 링크가 필요할 때만.
- 백엔드 자체 인증: API에 토큰 헤더 1단 (Tailscale 위의 한 겹 더).
- TLS는 Tailscale의 MagicDNS + 자체 서명 또는 Cloudflare 종단 인증서.

## 10. Phased Roadmap

### Phase 1 — MVP (4~6주, "혼자 돌아가는 비서")
- FastAPI 백엔드 + LiteLLM 라우터 (Claude / Gemini / Ollama 3-way)
- Ollama 모델 핀: `qwen2.5:14b`, `qwen2.5-coder:7b`, `qwen2.5:0.5b`, `nomic-embed-text`
- mlx-whisper STT (PTT, 한국어/영어 자동)
- LanceDB RAG — vault 전체 1회 풀 인덱싱 + fswatch 델타
- Vault Writer: atom 생성 + cross-link (threshold 0.75 + LLM 가지치기, K=5)
- PWA 정적 클라이언트 (Vite + TS) — 채팅 + 마이크 PTT 버튼
- Tailscale 셋업 (외부 접근 1차 수단)
- `launchd`로 백엔드 항상 실행 + 헬스체크
- `policy` 모듈 1차 (`local-only` frontmatter 존중 + 오프라인 모드 토글)

**Phase 1 검증 게이트**: 폰 브라우저에서 PTT → atom 1개가 vault에 생기고 Obsidian 그래프뷰에 새 노드/엣지가 보이면 완료.

### Phase 2 — 비서다움 (3~4주)
- TTS: macOS `say` → Coqui XTTS-v2 평가/스위치
- Daily MOC 자동 묶음 + 1주 reflection job (cross-link 재평가)
- Apple Calendar/Reminders 1-방향 읽기 → "오늘 일정 요약"
- 라우터에 비용 카운터 + 일별 한도 (Claude/Gemini 토큰)
- PWA에 `/graph` iframe — vault 그래프 미리보기 (읽기 전용)
- Cloudflare Tunnel 옵션

### Phase 3 — 능동성/확장 (가변)
- 정기 푸시 (아침 브리프, 미해결 atom 알림) via Telegram
- 코드 도메인: violet_sw 프로젝트 임베딩 레이어 (별도 LanceDB 컬렉션)
- iOS 단축어 통합 (Siri → PTT 트리거)
- 자동 토픽 발견 / MOC 제안

## 11. Directory Structure

```
015_little_lion/
├── backend/
│   ├── main.py                   # FastAPI entry (build_app + uvicorn)
│   ├── config.py                 # pydantic-settings + get_settings()
│   ├── stt/whisper_mlx.py
│   ├── router/                   # 3-stage cascade (deep-dive §3)
│   │   ├── rules.py              #  Stage 1: 33-pattern matcher
│   │   ├── classifier.py         #  Stage 2: qwen2.5:0.5b JSON-mode
│   │   ├── scorer.py             #  Stage 3: weighted model picker
│   │   └── orchestrator.py
│   ├── policy/gate.py            # single choke-point for cloud LLM calls
│   ├── llm/{ollama.py, router_client.py}
│   ├── rag/{store.py, chunk.py, indexer.py, search.py, watcher.py}
│   ├── vault/{fs_utils.py, frontmatter.py, writer.py, linker.py}
│   ├── session/manager.py
│   ├── trace/builder.py          # 7-stage decision trace (deep-dive §5)
│   ├── pipeline/{atomize.py, cross_link.py}
│   ├── services/pipeline.py      # /chat composition
│   └── api/{auth.py, health.py, chat.py, voice.py}
├── frontend/                     # PWA (Vite + TS) — Plan 1b
│   ├── index.html, manifest.json, sw.js
│   └── src/{chat, mic, graph, lib}
├── ollama/models.yaml            # pinned versions
├── infra/                        # Plan 1c
│   ├── launchd/com.violet.littlelion.plist
│   ├── tailscale-setup.md
│   └── cloudflared/              # Phase 2
├── tests/                        # 모듈별 단위 + integration
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROUTING_POLICY.md
│   ├── VAULT_SCHEMA.md
│   ├── CHECKLIST.md
│   ├── TROUBLESHOOTING.md
│   └── specs/                    # design + plan + deep-dive (이 문서 포함)
├── scripts/{run_dev.sh, index_vault.py}
├── data/lancedb/                 # gitignored — vector store
├── .env.example
├── pyproject.toml
└── CLAUDE.md

# vault 측 구조 (외부 — iCloud로 동기화되는 Obsidian vault 내부)
<vault>/assistant/
├── atoms/<slug>.md               # state=published|linked|archived|conflicted|merged
├── daily/<YYYY-MM-DD>.md         # atom embed + session links
├── sessions/<sid>.md             # raw transcripts
├── MOC/MOC-<topic>.md            # 사람이 키우는 인덱스
├── _traces/<sid>.json            # 7-stage decision trace (deep-dive §5) — RAG 제외
├── _proposals/MOC-<topic>.md     # reflection job이 제안한 MOC 후보 — RAG 제외
└── _review-queue.md              # weekly review에 사람이 archive 결정할 atom 목록
```

## 12. Risks & Mitigations

| 리스크 | 대응 |
|------|------|
| Whisper Large-v3 + 14B Ollama 동시 로드 메모리 압박 | 동시 로드 모델 ≤ 2개 제한, idle 5분 후 자동 unload |
| iCloud 동시 쓰기 충돌 | `tmp → fsync → rename` + `assistant-touched-at` frontmatter + `-conflict-N.md` 분기 |
| 잡노이즈 cross-link으로 그래프 망침 | threshold 0.75 + LLM 가지치기 + K ≤ 5 + 1주 reflection |
| API 비용 폭증 | 라우터에 일별 토큰 카운터, 한도 초과 시 자동 로컬 강등 |
| 외부 접속 보안 | 1차 Tailscale (사설 IP) + 2차 백엔드 토큰 인증 + 노트 `local-only` 게이트 |
| 사용자 발화 잘못 인식 → 잘못된 atom | Phase 1은 자동, Phase 2에서 "vault에 저장할까?" 확인 토글 추가 |

## 13. Open Questions (Phase 1 진입 전 더 정해도 되는 것들)

- TTS Phase 1을 macOS `say`로 시작할지 아예 텍스트만으로 시작할지 (현재 디자인: macOS `say`로 시작).
- PWA `/graph` iframe을 어떻게 띄울지: Obsidian 자체 graph는 데스크탑 앱 내부 기능이라 외부 iframe이 안 됨 → Phase 2에서 vault를 정적 사이트로 빌드(Quartz/Obsidian Publish 같은 도구) 후 그래프 임베드.
- 한국어 음성 인식 정확도 — Large-v3가 부족하면 Phase 1.5에서 KoBigBird-Whisper 같은 변종 평가.

(이 항목들은 Phase 1 plan 작성 시점에서 결정한다.)

## 14. Next Step

이 디자인이 사용자 승인 후:
1. `writing-plans` 스킬로 Phase 1을 실행 가능한 task 단위로 쪼갠 implementation plan 문서를 작성 (`docs/specs/2026-05-18-little-lion-phase1-plan.md`).
2. plan 검토 후 별 세션에서 `executing-plans`로 코딩 시작.
