# Telegram Gemini Bot

질문 수신 → Gemini/Claude 리서치 → Claude HTML 변환 → WordPress 발행 (카테고리 선택 기능).

## 데이터 흐름

```
질문 수신 → WordPress 카테고리 선택 UI (Inline Keyboard) → 선택/타임아웃
                    ↓
         Deep research (Gemini × Claude 다라운드) 또는 /quick 단발
                    ↓
         Claude HTML 변환 (한글, 블로그 제목 생성)
                    ↓
         선택 카테고리로 WordPress(grace-moon.com) 발행 (Claude 제목 우선, Gemini 제목 fallback)
```

## 발행 방식 (2026-06-12: WordPress 단일 사이트 + 카테고리 선택)

- **카테고리 선택 시**: 선택한 **WordPress 카테고리 1곳**에 발행(HTML). 선택 UI에 8개 카테고리 버튼 표시. `callback_data=cat:{id}`.
- **무선택 타임아웃**: **발행 취소**(알림만). `BLOG_SELECTION_TIMEOUT`(default 180초).
- 옛 멀티 블로그(blogspot)·영문 변환·raw 첨부는 **전부 폐지**. 모든 글을 한글 그대로 WordPress에 발행.

## 발행 워크플로우 (`_finalize_and_upload`)

진입점: `_show_category_selection`(버튼) → `_handle_callback_query`(`cat:` 파싱) → `_process_after_selection` → `_finalize_and_upload`. (`/quick` 단발은 `_process_and_upload_single` 경유.)

1. **한글 본문 HTML 생성** — `convert_md_to_html_via_claude(..., apply_editorial_box=False)`. 저자 박스는 다음 단계에서 따로 적용.
2. **저자 박스(GraceMoon) 적용** — `shared.editorial.apply_editorial(author_key="research", content_type="research")`. 박스 이름=GraceMoon, 링크=grace-moon.com (`config/authors.json`).
3. **WordPress 발행** — `_upload_single`→`_do_upload`가 `shared.wordpress_uploader.WordPressUploader`로 선택 카테고리에 발행. **mermaid→PNG(kroki)·AdSense/raw strip은 업로더가 처리**(본문엔 박스까지만 넣고 넘김).
4. **텔레그램 통지** — 완료 메시지에 발행 URL 포함.

> 발행은 WordPress 한 곳으로만 (로컬 백업·메시지 내 백업 경로 없음).

## WordPress 카테고리 (선택 버튼 8종)

`WP_CATEGORY_CHOICES` (telegram_gemini_bot.py). 전체 카테고리 ID 맵은 `shared/wordpress_uploader.py`의 `CATEGORY_IDS`.

| 버튼 | 카테고리 ID |
|------|------------|
| 뉴스 | 5 |
| 일일시황 | 6 |
| 섹터 | 7 |
| 부동산 | 8 |
| SoC | 9 |
| SW | 10 |
| AI | 11 |
| 기타 | 4 |

## 진행 상황 메시지

1. "Processing: Asking Gemini..."
2. "Claude HTML 생성 중…"
3. "Publishing to WordPress…"
4. 완료 메시지 (발행 URL 포함)

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

`convert_md_to_html_via_claude()` - Markdown을 WordPress용 한글 HTML로 변환. 반환: `(html, blog_title)` 튜플.
- **블로그 제목 생성**: Claude가 `BLOG_TITLE:` 라인으로 제목 출력 → 텔레그램봇에서 Gemini 제목 대신 사용
- 투자 면책조항: Claude가 내용 판단하여 자동 포함
- 공통 금지: AI, 자동 생성, Gemini, Claude 등 AI 관련 문구
- 제목 미생성 시 Gemini 제목으로 fallback (뉴스봇/버핏봇/섹터봇은 자체 제목 사용, 제목 무시)
- `apply_editorial_box=False`면 본문(body)만 반환 — 호출부가 저자 박스를 따로 입힌다.
- (2026-06-12 정리) AdSense 인라인 삽입·영문 변환(`convert_ko_html_to_english`)·raw 첨부(`append_raw_source_details`)·`translate_markdown_to_english`는 **전부 제거됨**. mermaid→PNG·AdSense/raw strip은 발행 단계에서 `WordPressUploader`가 담당.

### shared/wordpress_uploader.py

`WordPressUploader` - WordPress REST(`/wp-json/wp/v2/*`) 발행. App Password + HTTP Basic Auth.
- `.env`: `WORDPRESS_URL` / `WORDPRESS_USER` / `WORDPRESS_APP_PASSWORD` / `WORDPRESS_DEFAULT_STATUS`.
- `CATEGORY_IDS`: 이름→ID 매핑 (투자2/기술3/기타4/뉴스5/일일시황6/섹터7/부동산8/SoC9/SW10/AI11).
- `create_post()` 발행 시 mermaid 코드블록→PNG(kroki) 렌더 후 미디어 업로드, `strip_adsense`/`strip_raw_source` 적용.
- `upload_post(...)` = 옛 `BloggerUploader.upload_post` 드롭인 호환 어댑터(`{success, url, post_id, message}` 반환) — 봇 호출부 무수정 교체용.

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
