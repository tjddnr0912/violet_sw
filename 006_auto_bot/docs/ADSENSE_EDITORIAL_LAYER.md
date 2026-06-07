# 애드센스 승인용 편집 레이어 자동화 설계

> 상태: **일부 구현됨 (Stage 0~1 핵심)** · 작성 2026-06-07 · 결정 시 참고용
> 대상: 006_auto_bot의 봇 출력(뉴스/버핏/섹터/부동산)을 애드센스 승인 가능한 품질로 끌어올리는 자동 편집 단계
> 전제: 플랫폼 이전(Blogger→WordPress 등)은 별개 트랙. 이 문서는 **콘텐츠 품질** 트랙이며, 어느 플랫폼이든 동일하게 적용된다.

## 확정된 운영 결정 (2026-06-07)

- **승인 타깃 = Tistory(이미 승인됨, 수익처).** Blogger는 **공개 미러**로만 유지(승인 포기).
- **자동 업로드는 Blogger만 가능**(Tistory API 사실상 부재) → 봇이 Blogger에 발행 → 그 콘텐츠를 **수동 copy**로 Tistory에 게시.
- **광고(인아티클·멀티플렉스)는 Blogger 업로드물에 그대로 유지** — 미승인 Blogger에선 노출 안 되지만, copy 시 광고 코드가 Tistory로 함께 따라가게 하기 위함. (※ 한때 "Blogger 광고 제거 + 로컬 통합본 저장"을 구현했다가 이 결정으로 **되돌림**.)
- 편집 레이어는 **본문(마크다운→HTML) 단계**에 주입 → Blogger·Tistory 양쪽 콘텐츠가 동일하게 E-E-A-T 신호를 갖는다.

## 구현 현황

| 컴포넌트 | 상태 | 위치 |
|---|---|---|
| C1 저자/E-E-A-T 박스 | ✅ 구현 | `shared/editorial/` + `config/authors.json` |
| C4 면책/투명성 라인 | ✅ 구현(면책+투명성). 출처 교차검증은 기존 research/orchestrator 유지 | `shared/editorial/` |
| 중앙 연결 | ✅ `convert_md_to_html_via_claude(editorial=...)` — 전 봇 호출부 배선 | `shared/claude_html_converter.py` |
| C2 anti-templating | ⬜ 미구현 (각 콘텐츠 SKILL.md에 구조 변주 풀 필요) | — |
| C3 고유 데이터·표 | 🟡 일부 구현 | `shared/editorial/data_blocks.py` |

### C3 상세 (2026-06-07)

핵심 제약: `convert_md_to_html_via_claude` 호출 시점엔 봇의 dict 데이터가 이미 마크다운 텍스트로 굳어 있음 → C3는 **각 봇의 마크다운 생성 단계(데이터가 dict로 살아있는 곳)**에서 표를 박아야 함. 중앙 변환기에 표 주입 불가.

| 봇 | C3 상태 | 비고 |
|---|---|---|
| 부동산봇 | ✅ 이미 준수 | `realestate_bot/digest.py`가 구별 온도차·전세가율·신고가/신저점 단지 **실거래 표**를 이미 렌더 중. 변경 불필요 |
| 뉴스봇(일간) | ✅ 구현 | `main.py` 일간 task에서 `orch.stats`(카테고리별 건수·Tier-1 비중·국내외 비율)를 `news_quality_block`으로 "## 이번 호 수집 데이터" 표로 박제 |
| 뉴스봇(주간/월간) | ⬜ 미적용 | orchestrator 미사용 → stats 없음. 후속 |
| 섹터봇 | ⬜ 보류 | 섹터 점수가 서술형(Claude/Gemini 텍스트)뿐, 숫자 dict 부재. 점수를 정량화하려면 분석 파이프라인 변경 필요 |
| 버핏봇 | ➖ 해당없음 | 구조화 숫자 없음(순수 뉴스 텍스트 분석) |

공용 표 렌더러: `shared/editorial/data_blocks.py` (`markdown_table`, `news_quality_block`). 차트 이미지화(matplotlib→Cloudinary)는 외부 의존·실패 위험으로 후속(Stage 3) 보류. 마크다운 표는 결정적·Tistory 복사 안전.
| C5 고유 이미지 | ⬜ 인프라 존재(`image_generator.py`), 활성화 보류 | — |
| C6 발행 거버넌스 | ⬜ 미구현 | — |
| C7 사이트 페이지 | ⬜ 미구현(1회성) | — |
| C8 품질 게이트 | ⬜ 미구현 | — |

저자 페르소나(이름/약력/사진/링크)는 `config/authors.json`에서 직접 편집. 기본값은 "데이터 수집·분석 + 사람 감수"를 정직하게 직함화한 placeholder(날조 금지 원칙).
편집 레이어 on/off: env `EDITORIAL_ENABLED`(기본 true). 봇별 author/타입은 호출부에 `editorial={"author":..., "content_type":...}`로 배선됨.

---

## 1. 왜 필요한가 (문제 정의)

블로그들이 애드센스 광고 심사에서 반복 거부되는 근본 원인은 **플랫폼(Blogger)이 아니라 "AI 무편집 대량 생성물(low value / scaled content abuse)"** 일 가능성이 높다.

구글 공식 입장(검증된 1차 자료):

> "Our focus is on the quality of content, not how it was produced."
> — [Google Search Central, Using gen AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)

- AI 사용 자체는 정책 위반이 **아님**.
- 위반은 "사용자에게 가치를 더하지 않고 대량 생성한 페이지"(scaled content abuse).
- 2026-03 / 2026-05 스팸 업데이트로 단속 강화 — 편집 감수 없는 AI 대량 사이트는 트래픽 50~80% 급락 사례.

따라서 **플랫폼을 옮겨도 같은 콘텐츠면 같은 결과**다. 진짜 레버는 봇 출력에 "사람이 만든 가치 신호"를 자동으로 주입하는 **편집 레이어(Editorial Layer)** 다.

### 승인 통과 사이트의 공통점 (목표 신호)
출처: [adsenseaudit.net 2026](https://adsenseaudit.net/guides/adsense-ai-content-policy-2026), [originality.ai](https://originality.ai/blog/adsense-rejects-site-ai-content)

1. 글마다 다른 구조·톤 (30개 글이 같은 헤딩·문체 = 자동 탈락 신호)
2. 식별 가능한 **저자 + 검증 가능한 전문성** (E-E-A-T)
3. 고유 이미지·차트·실제 데이터·사례 (AI가 못 만드는 것)
4. AI를 "초안 도구"로 쓰고 사람이 팩트체크·인사이트 추가한 흔적
5. about / 연락처 / 개인정보처리방침 등 "정상 사이트" 골격

---

## 2. 설계 원칙 — 구글 정책을 신호로 매핑

| 구글이 보는 위험 신호 | 편집 레이어가 주입할 반대 신호 | 담당 컴포넌트 |
|---|---|---|
| 익명 자동 생성 | 저자 정보 + 전문성(E-E-A-T) | C1 |
| 글마다 같은 템플릿/톤 | 구조·톤·길이 다양화 | C2 |
| 일반론, 어디서나 볼 수 있는 내용 | 고유 데이터·실거래 수치·차트 | C3 |
| 출처 불명 | 인라인 출처 + 팩트체크 | C4 |
| 텍스트만, 고유 시각자료 없음 | 고유 이미지·도표 | C5 |
| 짧은 기간 대량 양산 | 발행 빈도/볼륨 거버넌스 | C6 |
| 사이트 골격 부재 | 필수 페이지 자동 생성 | C7 |
| (게이트 없음) | 발행 전 품질 점수 게이트 | C8 |

핵심 철학: **봇은 이미 "고유 데이터"를 보유**하고 있다(섹터봇=11섹터 그라운딩, 부동산봇=MOLIT 실거래 392만행, 버핏봇=가치투자 관점). 이건 경쟁 AI 블로그가 흉내 못 내는 가장 강력한 차별 자산이다. 편집 레이어의 1순위는 **이 데이터를 전면에 끌어올리는 것**.

---

## 3. 파이프라인 위치

현재 흐름:
```
RSS/검색/MOLIT → AI 분석(Gemini/Claude) → markdown
   → claude_html_converter → blogger_uploader.upload_post()
```

편집 레이어 삽입 후:
```
... AI 분석 → markdown(raw)
   → [편집 레이어]
       C8 품질 게이트(점수 < 임계 → C2/C3 보강 루프, 최대 N회)
       C1 저자 메타 부착
       C2 anti-templating 변형
       C3 데이터 블록 주입 (봇 보유 수치/표)
       C4 출처 인라인 정리
       C5 고유 차트/이미지 생성·삽입
   → claude_html_converter → upload_post()
   → C6 발행 거버넌스(빈도/볼륨 스케줄러가 제어)
C7 사이트 페이지는 독립 1회성 생성기
```

기존 orchestrator(news_bot/orchestrator.py, sector_bot/orchestrator.py)의 **5차원 게이트 패턴을 그대로 차용** — 편집 레이어는 "발행 직전 6번째 게이트(AdSense readiness)" 로 붙인다.

---

## 4. 컴포넌트 상세

### C1 — 저자 / E-E-A-T 부착 (우선순위: 높음, 난이도: 낮음)

**목적**: "식별 가능한 저자 + 검증 가능한 전문성" 신호.

**구현**
- 블로그별 저자 페르소나 정의(JSON): 이름, 한 줄 직함, 약력 2~3줄, 사진(고정 이미지), 사회망/연락 링크.
  - 예: 섹터봇="퀀트 리서처 ○○○, 섹터 로테이션 16주 추적", 부동산봇="실거래 데이터 분석가 ○○○, MOLIT 119시군구 집계".
- 글 하단에 저자 박스(HTML 카드) 자동 삽입 → `blogger_html_inject.py`에 author-box injector 추가.
- 글 상단에 "작성/감수: <저자>, 최종 업데이트 YYYY-MM-DD" 라인.
- WordPress 이전 시: 실제 author 계정 + author archive 페이지로 승격(더 강한 신호).

**주의**: 가짜 전문성을 날조하지 말 것. 페르소나는 "이 봇이 실제로 하는 일"(데이터 추적·집계)을 정직하게 직함화한 것이어야 한다. 구글은 날조된 저자 정보(가짜 학위 등)를 별도로 페널티한다.

**산출물**: `shared/editorial/author.py` + `config/authors.json`

---

### C2 — Anti-Templating (구조·톤·길이 다양화) (우선순위: 최상, 난이도: 중)

**목적**: "30개 글이 같은 헤딩·문체" 자동 탈락 신호 제거. 현재 봇 출력의 가장 큰 위험.

**구현**
- 스킬 파일에 **출력 구조 변주 풀(pool)** 정의. 글마다 결정적(deterministic, 날짜·주제 해시 기반 — `Math.random` 금지) 으로 1개 선택:
  - 구조 변주: 비교표 중심 / 연대기 / Q&A / 사례 스토리 / 데이터 브리핑 / 반론 중심 등 6~8종.
  - 도입부 변주: 질문형 / 수치 충격형 / 사례형 / 시의성형.
  - 헤더 표현: 이미 적용 중인 규칙(한자·일반명사 단계 헤더 금지, 주제에서 따온 구체 헤더) 강제 유지 → [feedback-no-hanja-narrative-headers] 와 일관.
  - 길이 변주: 주제 무게에 따라 짧은 브리핑 ~ 심층 분석 (강제 동일 길이 금지).
- 톤 시드를 프롬프트에 주입: 같은 봇이라도 글마다 문체 미세 변주.
- **자기 점검**: C8 게이트가 직전 N개 글과 헤딩/구조 유사도(예: 헤더 문자열 자카드 유사도)를 측정 → 임계 초과 시 재생성.

**산출물**: 각 스킬 SKILL.md에 "구조 변주 풀" 섹션 추가 + `shared/editorial/diversify.py`(시드 선택·유사도 측정)

---

### C3 — 고유 데이터·차트 주입 (우선순위: 최상, 난이도: 중) ⭐ 최대 차별점

**목적**: "어디서나 볼 수 있는 일반론" → "이 사이트에만 있는 수치". 봇 보유 자산을 전면화.

**구현**
- 봇별 보유 데이터를 글에 **명시적 데이터 블록**으로 강제 삽입:
  - 부동산봇: MOLIT 실거래 시군구별 표, 전주 대비 diff, 거래량 — 이미 수집됨. HTML 표/차트로 격상.
  - 섹터봇: 11섹터 점수표, 16주 추세, 로테이션 시그널.
  - 버핏봇: 밸류에이션 지표, 뉴스 기반 정량 요약.
  - 뉴스봇: 출처 다양성/신선도 지표를 독자용 요약으로.
- 표·시계열은 **차트 이미지로 렌더**(matplotlib 등) → C5 이미지 파이프라인으로 업로드. "고유 차트"는 AdSense 심사에서 강력한 경험(Experience) 신호.
- 모든 수치는 출처·기준일 명기(C4 연계).

**산출물**: `shared/editorial/data_blocks.py`(봇별 데이터→표/차트 변환), 차트 렌더러

---

### C4 — 출처 / 팩트체크 인라인 (우선순위: 높음, 난이도: 낮음)

**목적**: "출처 불명" 제거. research 스킬이 이미 하는 1차 source 검증 패턴을 발행물에도 적용.

**구현**
- 본문 주장에 인라인 인용 `[출처: <매체>, YYYY-MM-DD]`, 글 끝 출처 목록.
- 가능하면 web_search(agy→Claude)로 핵심 수치 1~2개 교차검증 후 "검증됨" 표시.
- 면책 문구(투자·부동산은 필수): "본 글은 정보 제공 목적이며 투자 권유가 아님" — 금융 콘텐츠 애드센스 심사에서 중요.

**산출물**: `shared/editorial/citations.py` + 스킬에 인용 형식 규칙

---

### C5 — 고유 이미지 / 도표 (우선순위: 중, 난이도: 낮음 — 인프라 존재)

**목적**: "고유 시각자료" 신호. 이미 `image_generator.py`(pollinations 백엔드) + `image_uploader.py` + `blogger_html_inject.py` 3단 파이프라인 보유.

**구현**
- 글당 최소 1개 고유 이미지(현재 활성화 보류 상태 → 활성화 검토). 단, 생성형 일러스트보다 **C3의 실데이터 차트가 우선**(경험 신호가 더 강함).
- 스톡 이미지 재사용 금지(중복 콘텐츠 신호).
- alt 텍스트 자동 생성(접근성 + SEO).

**산출물**: 기존 모듈 재사용 + 차트 우선 정책

---

### C6 — 발행 빈도 / 볼륨 거버넌스 (우선순위: 높음, 난이도: 낮음)

**목적**: "짧은 기간 대량 양산" 신호 제거. 심사 통과 전후로 특히 중요.

**구현**
- 신청 직전 단계: 하루 다발 발행 금지, **일 1~2건 상한** + 발행 시각 분산.
- "품질 우선" 모드 플래그: 게이트(C8) 통과분만 발행, 미달은 보류 큐.
- 초기 사이트 빌드 시 30~40개 양질 글을 **수주에 걸쳐** 분산 축적(한 번에 100개 덤프 금지).

**산출물**: 기존 스케줄러(investment_bot.py)에 rate-limit + 보류 큐. env: `EDITORIAL_MAX_POSTS_PER_DAY`

---

### C7 — 필수 사이트 페이지 (우선순위: 높음, 난이도: 낮음, 1회성)

**목적**: "정상 사이트" 골격. 애드센스 심사 필수 체크 항목.

**구현 (1회 생성 후 유지)**
- About / 소개 (사이트 목적, 운영 주체, 데이터 출처 방법론)
- 연락처 (이메일 폼 또는 주소)
- 개인정보처리방침 (애드센스 쿠키 고지 포함 — **필수**)
- 면책조항 (금융·부동산 정보)
- (선택) 저자 소개 페이지(C1 연계)

**산출물**: `scripts/generate_site_pages.py`(1회성), 플랫폼별 발행

---

### C8 — 발행 전 품질 게이트 (AdSense Readiness Scorer) (우선순위: 최상, 난이도: 중)

**목적**: 위 모든 컴포넌트를 강제하는 단일 게이트. orchestrator 5차원 게이트와 동형.

**점수 차원 (각 0~1, 가중합 임계 통과)**
| 차원 | 측정 | 미달 시 액션 |
|---|---|---|
| 고유성 | 고유 데이터 블록·차트 존재 | C3 보강 |
| 다양성 | 직전 N개 글과 구조/헤더 유사도 < 임계 | C2 재생성 |
| 출처 | 인용 ≥ 2, 기준일 명시 | C4 보강 |
| 저자 | 저자 메타·면책 존재 | C1 부착 |
| 시각자료 | 고유 이미지/차트 ≥ 1 | C5 생성 |
| 깊이 | 최소 길이·고유 인사이트 문장 비율 | 재생성 |

- 임계 미달 → 자동 보강 루프(최대 N회) → 그래도 미달이면 보류 큐(발행 안 함, 알림).
- checklist 스킬 패턴 차용 가능: `docs/CHECKLIST.md`에 발행 전 검증 항목으로 박제.

**산출물**: `shared/editorial/readiness.py` + 보강 루프

---

## 5. 신규 모듈 구조 (제안)

```
001_code/shared/editorial/
    __init__.py
    author.py        # C1 저자/E-E-A-T 박스
    diversify.py     # C2 구조·톤 변주 + 유사도 측정
    data_blocks.py   # C3 봇 데이터→표/차트
    citations.py     # C4 출처·팩트체크·면책
    readiness.py     # C8 품질 게이트 + 보강 루프
    pipeline.py      # 위를 순서대로 묶는 EditorialPipeline.apply(markdown, ctx) → markdown
001_code/config/
    authors.json     # 블로그별 저자 페르소나
001_code/scripts/
    generate_site_pages.py   # C7 1회성
```

기존 모듈 재사용: `image_generator.py`/`image_uploader.py`/`blogger_html_inject.py`(C5), `web_search.py`(C4 교차검증), `claude_html_converter.py`(최종 변환).

호출부 변경 최소화: 각 봇은 `upload_post(markdown)` 직전에
`markdown = EditorialPipeline().apply(markdown, ctx)` 한 줄 삽입.

---

## 6. 구현 로드맵 (단계별)

| 단계 | 범위 | 효과/리스크 |
|---|---|---|
| **0** | C7 사이트 페이지 + C1 저자 박스 (1회성·저난이도) | 즉시 "정상 사이트" 신호. 거의 공짜 |
| **1** | C4 출처/면책 + C3 데이터 블록(텍스트 표 먼저) | 최대 차별점, 난이도 중 |
| **2** | C8 게이트 + C2 anti-templating | 품질 강제. 핵심 |
| **3** | C3 차트 렌더 + C5 이미지 활성화 | 경험 신호 강화 |
| **4** | C6 거버넌스 + 30~40글 축적 → **애드센스 신청** | 신청 타이밍 |

> 0~2단계만으로도 승인 확률이 의미 있게 오른다. 3~4는 강화.

---

## 7. 애드센스 신청 전 체크리스트 (수동 확인)

- [ ] 양질 글 30~40개, 수주에 걸쳐 분산 축적됨
- [ ] About/연락처/개인정보처리방침/면책 페이지 존재 (C7)
- [ ] 모든 글에 저자 정보 + 최종 업데이트일 (C1)
- [ ] 글마다 구조/헤더가 눈에 띄게 다름 (C2)
- [ ] 각 글에 사이트 고유 데이터·차트 ≥ 1 (C3)
- [ ] 인용 출처 + 기준일 명시 (C4)
- [ ] 고유 이미지/도표, 스톡 재사용 없음 (C5)
- [ ] Search Console 등록 + sitemap 제출, 주요 글 색인됨
- [ ] 도메인 연결, 깨진 링크·빈 카테고리 없음
- [ ] 투자/부동산 면책 문구 노출

---

## 8. 리스크 · 미결정 사항

- **승인 보장 없음**: 편집 레이어는 확률을 올릴 뿐. 구글 심사는 재량적이며 재신청 반복 가능성 존재.
- **저자 진정성**: 페르소나는 정직해야 함(날조 금지). "데이터 추적 봇"이라는 실체를 직함화하는 선.
- **AI 콘텐츠 자체 표기 여부**: 구글은 AI 사용 *투명 공개*를 권장하나, 애드센스 심사에서 명시적 "AI 생성" 표기가 유불리한지는 공개 정보로 단정 불가 → **미결정**. 보수적으로는 "데이터 기반 자동 분석, 편집 감수" 정도의 톤.
- **플랫폼 결정과의 관계**: 이 레이어는 플랫폼 독립적. WordPress 이전 시 C1(author archive)·C7(페이지)·디자인이 더 강해짐. Blogger 유지해도 C1~C8 적용 가능.
- **금융 콘텐츠 심사 강도**: 투자/부동산은 YMYL(Your Money Your Life) 영역이라 일반 주제보다 E-E-A-T 기준이 높음 → C1/C4 비중을 더 키워야 할 수 있음.

---

## 참고 출처

- [Google Search Central — Using gen AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content) (1차, 검증됨)
- [Google Search Central — Spam Policies](https://developers.google.com/search/docs/essentials/spam-policies)
- [AdSense AI Content Policy 2026](https://adsenseaudit.net/guides/adsense-ai-content-policy-2026)
- [AdSense rejects site due to AI content — Originality.AI](https://originality.ai/blog/adsense-rejects-site-ai-content)
- [Scaled Content Abuse — DigitalApplied](https://www.digitalapplied.com/blog/scaled-content-abuse-google-march-update-ai-pages-decimated)
