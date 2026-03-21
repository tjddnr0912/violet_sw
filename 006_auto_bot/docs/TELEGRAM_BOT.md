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

## 업로드 방식

- **블로그 선택 시**: 2군데 업로드 (Default: HTML+Raw, 선택 블로그: HTML만)
- **Default만 클릭 / 타임아웃**: 1군데만 업로드 (Brave Ogu)

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
