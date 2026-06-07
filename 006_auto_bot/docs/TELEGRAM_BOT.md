# Telegram Gemini Bot

질문 수신 → Gemini 처리 → Claude HTML 변환 → Blogger 업로드 (블로그 선택 기능).

## 데이터 흐름

```
질문 수신 → 블로그 선택 UI (Inline Keyboard) → 선택/타임아웃
                    ↓
         Gemini 처리 (1500자+ 요구, 제목/라벨/출처 메타데이터)
                    ↓
         Claude HTML 변환 (1000자+ 요구, 블로그 제목 생성)
                    ↓
         블로그 업로드 (Claude 제목 우선, Gemini 제목 fallback)
```

## 업로드 방식 (2026-06-08 변경: 선택 블로그 1곳만)

- **블로그 선택 시**: **선택한 블로그 1곳에만** 업로드 (HTML only). 선택 UI에 모든 블로그 표시.
- **무선택 타임아웃**: **업로드 취소**(알림만). — 기존 "default(bravebabyogu) 자동 업로드"는 폐지됨.
- 단일 블로그 모드(`len(blogs)==1`): 그 블로그 1곳에 업로드.
- 구현: `_upload_single` (기존 `_upload_default_only`/`_upload_dual` 통합).

## 지원 블로그 (7개)

| Key | Name | URL |
|-----|------|-----|
| brave_ogu | Brave Ogu (Default) | bravebabyogu.blogspot.com |
| soc_design | SoC Design | socdesignengineer.blogspot.com |
| ogusinvest | OgusInvest | ogusinvest.blogspot.com |
| sw_develope | SW Develope | swdevelope.blogspot.com |
| booksreview | BooksReview | booksreview333.blogspot.com |
| virtual_lifes | Virtual Life's | virtuallifeininternet.blogspot.com |
| wherewego | Where we go | wherewegoinworld.blogspot.com |

## 진행 상황 메시지

1. "Processing: Asking Gemini..."
2. "Processing: Claude에서 HTML을 생성 중..."
3. "Processing: Uploading to blog..."
4. 완료 메시지 (URL 포함)

## 최소 글자 수

| 단계 | 최소 | 설명 |
|------|------|------|
| Gemini 응답 | 1500자+ | 메타데이터 제외 본문 |
| Claude HTML | 1000자+ | HTML 태그 제외 가시적 텍스트 |

## 공유 모듈 상세

### shared/telegram_api.py

| Method | Description |
|--------|-------------|
| `send_message()` | 텍스트 메시지 전송 |
| `send_message_with_inline_keyboard()` | Inline Keyboard 버튼 포함 |
| `answer_callback_query()` | 버튼 클릭 응답 |
| `edit_message_text()` | 기존 메시지 수정 |
| `get_updates()` | Long polling |

### shared/claude_html_converter.py

`convert_md_to_html_via_claude()` - Markdown을 Blogger용 HTML로 변환. 반환: `(html, blog_title)` 튜플.
- **블로그 제목 생성**: Claude가 `BLOG_TITLE:` 라인으로 제목 출력 → 텔레그램봇에서 Gemini 제목 대신 사용
- 투자 면책조항: Claude가 내용 판단하여 자동 포함
- 공통 금지: AI, 자동 생성, Gemini, Claude 등 AI 관련 문구
- 제목 미생성 시 Gemini 제목으로 fallback (뉴스봇/버핏봇/섹터봇은 자체 제목 사용, 제목 무시)

## Research Modes (Deep default, `/quick` opt-out)

봇은 **모든 평문 메시지를 다라운드 deep research로 처리**합니다. 결과가 블로그에 게시되므로 사실관계 검증이 항상 가치 있다는 판단입니다. 가벼운 질문이나 Gemini quota가 빠듯할 때는 `/quick <질문>`으로 기존 단발 모드를 사용할 수 있습니다.

### Deep 모드 (기본)

| 단계 | 도구 | 역할 |
|---|---|---|
| Round 1 | Gemini CLI | broad sweep (telegram-qa 스킬 프롬프트 그대로) |
| Eval | Claude CLI | 5차원(정의/현황/근거/반론/적용) 체크, JSON 반환 |
| Round 2~N | Gemini CLI | 평가가 지목한 빈 차원만 좁힌 query로 재호출 |
| Synth | Claude CLI | 누적 라운드를 telegram-qa 톤의 마크다운으로 종합 + TITLE/LABELS/SOURCES |

**예상 시간:** 60~300초. Gemini quota 소진 시 누적 결과로 fallback 종합.

### Quick 모드 (`/quick <질문>`)

기존 단발 Gemini 흐름. ~30초. Quota 1회만 소비.

### 환경변수

- `RESEARCH_QUICK_COMMAND` (default: `/quick`) — 단발 모드 트리거 문자열
- `RESEARCH_MAX_ROUNDS` (default: `3`, 상한 4) — Deep 모드 라운드 최대 횟수

### 운영상 주의

- Gemini 호출 횟수가 단발 대비 평균 3배지만, 운영자가 **Gemini Code Assist (Google One AI Pro) tier**라 일일 한도는 충분히 여유 있음 (예상 사용량의 30배 이상). 분당 RPM 버스트 throttle은 가끔 발생할 수 있으나 오케스트레이터가 누적 결과로 자동 fallback 종합하므로 게시는 끊기지 않음.
- 다중 블로그 사용자는 두 모드 모두 동일한 블로그 선택 UI를 거침. 선택 후 모드별 흐름이 갈라짐.
