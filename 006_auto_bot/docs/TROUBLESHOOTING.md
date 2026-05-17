# 006_auto_bot 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다.

---

## 인라인 SVG 플로우차트 화살표가 박스에 안 닿음 / 다이어그램 깨짐

- **증상**: 봇이 만든 글의 의사결정 흐름 다이어그램에서 다이아몬드 옆구리에서 출발한 YES/NO 화살표가 결과 박스에 *연결되지 않고 허공에서 끝남*. 결과 박스가 SVG 영역 밖 별도 div로 빠지면서 시각적으로 어긋남.
- **원인**: SKILL.md 8번/9번 가이드가 "인라인 SVG로 노드+화살표 직접 좌표 계산"이었음. Claude가 매 호출마다 좌표를 재계산하면서 다음 3가지 실수 누적:
  - (A) 다이아몬드·화살표는 SVG, 결과 박스는 외부 HTML div로 *좌표계 분리* → 가장 빈번
  - (B) viewBox 고정인데 라벨 텍스트 길이 가변 → 시작점/끝점 어긋남
  - (C) 분기 ≥3이면 전체 레이아웃 재계산 필요한데 일부만 손봄
- **해결**: SKILL.md를 **Mermaid 코드블록 우선**으로 패치 (`flowchart TD` / `graph LR`). Blogger 테마와 Tistory 스킨에 Mermaid.js v11 글로벌 등록. 본문은 `<pre><code class="language-mermaid">` 양식만 작성 → JS가 자동 렌더. SVG 좌표 계산 0줄.
- **복구 절차**:
  - (a) `~/.claude/skills/blogger-html/SKILL.md` 8번/9번 섹션이 Mermaid 우선인지 확인
  - (b) Blogger 테마 → HTML 편집 → `</body>` 위 Mermaid CDN 스크립트 존재 확인 (`useMaxWidth` 또는 `import mermaid` 검색)
  - (c) Tistory: 꾸미기 → 스킨 편집 → html 편집 → 동일 확인
  - (d) 다음 봇 자동 실행 결과에서 `language-mermaid` 코드블록이 다이어그램으로 렌더링되는지
- **관련 사고**: 2026-05-17 (사용자 보고: 석회성건염 의사결정 다이어그램 — 화살표 박스 미연결), 2026-05-18 (검증 발행 4회로 Mermaid 도입 작동 확인)
- **재발 감지**: 발행물 raw HTML에서 `language-mermaid` 카운트 0이고 `<polygon`/`<line` 다수면 SVG 좌표 노가다로 회귀한 것. SKILL.md의 "Mermaid 코드블록을 우선 사용" 문구가 8번/9번 가이드에 남아있는지 확인.

### Claude 진단 미스 (2026-05-17 세션)

- **Claude 처음 가설 (도구 분석)**: 발행물의 다이어그램 상태를 *WebFetch* 도구로 확인 → "SVG 0개, Mermaid 스크립트 없음, border-left 카드 없음"이라는 잘못된 보고. 봇이 만든 시각화 자체가 빈약하다고 판단할 뻔함.
- **실제 원인**: WebFetch는 HTML→markdown 변환을 거치면서 인라인 `<svg>`, `<script>`, 인라인 style div를 모두 소실시킴. raw HTML 자체에는 SVG 27개·카드 24개가 멀쩡히 들어있었음.
- **방향 전환 지점**: 봇 출력 HTML 길이(50,000자+)와 WebFetch 결과(시각화 0)의 모순을 인지 → `curl -sL`로 raw HTML 직접 확인 후 정확한 카운트 확보.
- **교훈 (다음에 같은 패턴이 보이면)**:
  - 첫 의심 영역: **Blogger·Tistory 발행물 분석에는 WebFetch 사용 금지**. raw HTML이 필요한 모든 검증은 `curl -sL -A "Mozilla/5.0" "$URL"` 로 가져온 뒤 `grep`/`python3 -c "import re"`로 추출
  - 빨리 배제할 가설: "봇 출력이 변경됐다" — WebFetch에서 시각화가 0개로 보여도 *도구 한계*일 가능성이 90%. 봇 코드 변경 없이 출력만 빈약해지는 일은 드뭄
  - 핵심 진단 명령:
    ```bash
    curl -sL -A "Mozilla/5.0" "$URL" | grep -ciE "language-mermaid|<svg|border-left"
    ```

---

## Gemini 429 (서버 용량 부족)

- **증상**: Gemini API가 `429 ResourceExhausted` 또는 "서버 용량 부족" 메시지 반환. 라운드/요약 도중 일부 호출만 실패.
- **원인**: Google 서버 일시적 과부하 또는 quota 초과 (Code Assist tier 일일 한도).
- **해결**: 자동 재시도 (지수 백오프 3회). 누적 결과로 fallback 요약 메시지 자동 전송.
- **복구 절차**: 자동 복구. 429가 1시간 이상 지속 시 → quota 초과 가능성, Google AI Studio 콘솔에서 잔여량 확인.
- **관련 사고**: 2026-03-13 (gemini-free-tier-quota), 2026-04-04 (gemini-empty-response), 2026-04-20 (gemini-503-cli-fallback)
- **재발 감지**: `logs/*_$(date +%Y%m%d).log`에서 `429`/`503`/`empty response` 빈도. 일일 5회 이상이면 quota 한계 의심.

---

## Claude CLI empty response

- **증상**: Claude CLI 호출이 성공 코드(0) 반환하지만 stdout 비어 있음. 분석 결과 누락.
- **원인**: Claude API 일시 장애 또는 CLI 내부 timeout.
- **해결**: 자동 재시도 (3회, 30초 간격). 모두 실패 시 fallback synthesis로 진행 (raw rounds concatenation).
- **복구 절차**: 자동. 수동 검증은 `claude --version` 후 단순 호출 (`echo hi | claude -p "echo back"`).
- **관련 사고**: 2026-03-26 (claude-cli-empty-retry), 2026-04-04
- **재발 감지**: `Claude CLI returned empty` 로그 빈도. 일일 0~1건이 정상.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: CLI 인스톨 문제 또는 PATH 미설정
- **실제 원인**: Anthropic API 측 일시 장애. CLI 자체는 정상.
- **방향 전환 지점**: 같은 명령을 30초 후 재실행하면 성공 — 인스톨 문제 아님 인식
- **교훈**:
  - 첫 의심 영역: **재시도 시 응답 변화 여부**
  - 빨리 배제할 가설: "CLI 설치 문제" — 한번이라도 정상 응답 받았으면 인스톨은 OK
  - 핵심 진단 명령: `echo "test" | claude -p "echo"` 로 minimal call 검증

---

## Blogger OAuth 인증 실패

- **증상**: Blogger 업로드 시 `invalid_grant` 또는 토큰 만료 에러.
- **원인**: 저장된 OAuth refresh token이 무효화됨 (장기간 미사용 또는 사용자가 권한 회수).
- **해결**: `credentials/blogger_token.pkl` 삭제 후 다음 실행 시 OAuth 플로우 재진행.
- **복구 절차**:
  ```bash
  rm credentials/blogger_token.pkl
  python news_bot/blogger_uploader.py --auth   # 또는 통합 봇 실행 시 자동 재인증
  ```
- **관련 사고**: 정기적 (refresh token 만료, 분기 단위)
- **재발 감지**: `invalid_grant` 로그 발생 즉시 알림.

---

## Telegram HTML parse error

- **증상**: Telegram 메시지가 도착 안 함 또는 plain text로만 도착.
- **원인**: 메시지 본문에 `<`, `>` 같은 HTML 메타 문자가 escape 안 됨, 또는 닫히지 않은 `<b>` 태그.
- **해결**: HTML parse 에러 감지 시 plain text fallback으로 자동 재전송.
- **복구 절차**: 자동. 수동 검증은 `python -c "from shared.telegram_bot import send_text; send_text('test &<>')"`.
- **관련 사고**: 2026-03-20 (telegram-underscore-escape), 2025-12-20 (telegram-html-parsing-error)
- **재발 감지**: `Telegram HTML parse error` 로그 빈도. 일일 0건이 정상.

---

## Sector Weekly Summary가 N-1/N 으로 나감 (스케줄 충돌)

- **증상**: 일요일 텔레그램 Weekly Summary가 `10/11` 등 마지막 섹터 1개 빠진 상태로 도착. 직후 마지막 섹터가 정상 업로드됨.
- **원인**: `investment_bot.py`의 Weekly Summary 시각이 마지막 섹터 시작 시각보다 **앞**에 등록돼 있었음. `config.py`의 sector 11(필수 소비재) `scheduled_time="18:40"` vs 통합 봇의 Weekly Summary `18:30` → summary가 sector 11 시작 전에 트리거. (단독 실행 모드 `weekly_sector_bot.py:263`은 `19:20`으로 올바름.)
- **해결**: `investment_bot.py:127`의 Weekly Summary `18:30 → 19:20`, `:132`의 Comprehensive Report `19:00 → 19:40`. 단독 실행·문서·통합 모드 3자 일치.
- **복구 절차**: 코드 수정 후 다음 일요일까지 대기 (당일 데이터는 sector 파일 모두 정상이므로 `python weekly_sector_bot.py --comprehensive`로 수동 재생성 가능).
- **관련 사고**: 2026-05-10
- **재발 감지**: `[WeeklySummary] Triggered` 로그 시각이 마지막 섹터 `Completed` 시각보다 앞이면 alert. `tail logs/investment_bot_*.log | grep -E "Sector-11.*Completed|WeeklySummary] Triggered"`로 순서 확인.

---

## Comprehensive Report 업로드 Broken pipe

- **증상**: 종합 투자 평가 보고서 단계에서 `Upload failed: [Errno 32] Broken pipe`. 텔레그램으로 ❌ 실패 메시지 도착. 섹터 파일과 종합 MD/HTML은 정상 생성됨.
- **원인**: 마지막 섹터 업로드 이후 30분 이상 idle 후 cached `service.posts().insert()`를 그대로 호출. 그 사이 HTTP/2 keep-alive 또는 SSL 세션이 서버 측에서 종료된 상태에서 종합 HTML(타 섹터의 4-5배, ~118KB)을 한 번에 송신 → 첫 패킷 직후 broken pipe. `is_authenticated()`는 토큰 유효성만 검사하고 실제 connection은 검증하지 않음.
- **해결**: `shared/blogger_uploader.py`에 `_insert_with_retry()` 추가. `BrokenPipeError`/`ConnectionResetError`/`ConnectionError`/`RemoteDisconnected`/`SSLError`/`socket.error` 발생 시 `self.service = None` 후 `authenticate()` 재호출하고 1회 재시도. 모든 호출자(섹터/뉴스/버핏/종합) 적용.
- **복구 절차**: 일시적 실패면 자동 재시도로 복구. 재시도도 실패하면 sector 파일이 모두 살아있는지 확인 후 `python weekly_sector_bot.py --comprehensive`로 수동 재생성.
- **관련 사고**: 2026-05-10
- **재발 감지**: `Connection lost` WARNING 로그 (재시도 발생 신호). 동일 세션에 2회 이상이면 네트워크 또는 Blogger 서버 이슈 의심.

---

## Sector bot resume 실패

- **증상**: `weekly_sector_bot.py --once` 실행 시 "다른 주에 시작" 메시지로 거부.
- **원인**: `state.json`이 이전 주에 시작된 상태 보존. 일요일이 아닌 시점에 `--once` 호출 시 state 충돌.
- **해결**: `--reset` 후 `--once` 실행.
- **복구 절차**:
  ```bash
  python weekly_sector_bot.py --reset
  python weekly_sector_bot.py --once
  ```
- **관련 사고**: 정기적 (수동 호출 시 빈번)
- **재발 감지**: `state mismatch` 로그.

---

## Sector state 손상

- **증상**: 섹터 봇 시작 시 JSON parse error 또는 비정상 상태.
- **원인**: `state.json`이 비정상 종료(SIGKILL, 디스크 full)로 손상.
- **해결**: state 파일 reset.
- **복구 절차**: `python weekly_sector_bot.py --reset` 후 다음 일요일 13:00 자동 실행 또는 즉시 `--once`.
- **관련 사고**: 드뭄
- **재발 감지**: 시작 시 JSON parse error 즉시 alert.

---

## Blog selection timeout

- **증상**: 사용자에게 블로그 선택 prompt 보냈는데 응답 없음 → 봇이 timeout 후 default blog 사용.
- **원인**: `BLOG_SELECTION_TIMEOUT`(기본 180초) 내 응답 없음. 정상 동작이지만 default blog가 의도와 다를 수 있음.
- **해결**: `.env`에서 `BLOG_SELECTION_TIMEOUT` 값 조정 또는 `DEFAULT_BLOG`를 가장 자주 쓰는 블로그로 설정.
- **복구 절차**: 잘못 업로드된 블로그에서 글 삭제 후 정확한 블로그에 재업로드.
- **관련 사고**: 사용자 운영 패턴
- **재발 감지**: 일일 default blog 사용 비율 추적.

---

## ModuleNotFoundError

- **증상**: 봇 시작 시 import 에러.
- **원인**: venv 미활성화 또는 dependency 누락.
- **해결**:
  ```bash
  cd 006_auto_bot/001_code
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **복구 절차**: venv 재생성 필요 시 `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
- **관련 사고**: 환경 설정
- **재발 감지**: 시작 직후 ImportError → 즉시 fail-fast.

---

## 로그 파일 위치

```
logs/
├── investment_bot_YYYYMMDD.log  # 통합 오케스트레이터
├── news_bot_YYYYMMDD.log        # 뉴스봇
├── buffett_bot_YYYYMMDD.log     # 버핏봇
└── sector_bot_YYYYMMDD.log      # 섹터봇
```
