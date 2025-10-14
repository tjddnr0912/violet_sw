# 📰 자동 뉴스 요약 블로그 포스팅 봇

매일 전세계 주요 뉴스를 자동으로 수집하고, AI로 요약한 후 Tistory 블로그에 자동 업로드하는 Python 프로그램입니다.

## 🎯 주요 기능

- **뉴스 수집**: 6개 글로벌 뉴스 소스(CNN, BBC, Al Jazeera, The Guardian, Reuters, NYT)에서 RSS 피드를 통해 최신 뉴스 수집
- **자동 선별**: 최신성과 다양성을 고려하여 매일 TOP 10 뉴스 자동 선정
- **AI 요약**: OpenAI GPT를 활용하여 각 뉴스를 한국어로 간결하게 요약
- **자동 포스팅**: Tistory API를 통해 블로그에 자동으로 포스팅
- **스케줄링**: 매일 정해진 시간에 자동 실행

## 📁 프로젝트 구조

```
006_auto_bot/
├── 000_proposal/          # 프로젝트 기획 문서
├── 001_code/              # 소스 코드
│   ├── main.py            # 메인 실행 파일
│   ├── config.py          # 설정 관리
│   ├── news_aggregator.py # 뉴스 수집 모듈
│   ├── ai_summarizer.py   # AI 요약 모듈
│   ├── tistory_uploader.py # Tistory 업로드 모듈
│   ├── requirements.txt   # 의존성 패키지
│   └── .env.example       # 환경 변수 예제
├── 002_doc/               # 문서
│   └── README.md          # 이 파일
└── 003_test_code/         # 테스트 코드
```

## 🚀 설치 방법

### 1. Python 환경 설정

Python 3.8 이상 필요:

```bash
cd 006_auto_bot/001_code
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. API 키 설정

`.env.example` 파일을 `.env`로 복사하고 실제 API 키를 입력:

```bash
cp .env.example .env
```

`.env` 파일 편집:

```env
# Tistory API
TISTORY_ACCESS_TOKEN=your_actual_access_token
TISTORY_BLOG_NAME=your_blog_name

# OpenAI API
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-3.5-turbo
```

## 🔑 API 키 발급 방법

### Tistory API

1. [Tistory 오픈 API 관리](https://www.tistory.com/guide/api/manage/register) 접속
2. 앱 등록 후 Client ID, Secret Key 발급
3. OAuth 인증을 통해 Access Token 획득

**Access Token 발급 절차:**

```
1. 다음 URL로 접속 (Client ID 입력 필요):
https://www.tistory.com/oauth/authorize?client_id={Client-ID}&redirect_uri={redirect-uri}&response_type=code

2. 인증 후 받은 code로 Access Token 요청:
GET https://www.tistory.com/oauth/access_token?client_id={Client-ID}&client_secret={Secret-Key}&redirect_uri={redirect-uri}&code={code}&grant_type=authorization_code
```

### OpenAI API

1. [OpenAI API Keys](https://platform.openai.com/api-keys) 접속
2. "Create new secret key" 클릭하여 API 키 발급
3. 발급받은 키를 `.env` 파일에 입력

## 💻 사용 방법

### 1. 즉시 실행 (1회)

```bash
python main.py --mode once
```

### 2. 스케줄링 실행 (매일 정해진 시간)

```bash
python main.py --mode scheduled
```

기본 실행 시간은 `config.py`의 `POSTING_TIME`에서 설정 (기본값: 09:00)

### 3. 테스트 모드 (포스팅 없이 요약만)

```bash
python main.py --test
```

## ⚙️ 설정 변경

`config.py` 파일에서 다양한 설정 변경 가능:

```python
# 뉴스 개수
MAX_NEWS_COUNT = 10

# 요약 길이
SUMMARY_MAX_LENGTH = 300

# 포스팅 시간
POSTING_TIME = "09:00"

# OpenAI 모델
OPENAI_MODEL = "gpt-3.5-turbo"  # 또는 "gpt-4"

# 뉴스 소스 추가/변경
NEWS_SOURCES = [
    'http://rss.cnn.com/rss/edition_world.rss',
    # ... 원하는 RSS 피드 추가
]
```

## 📊 실행 흐름

1. **뉴스 수집**: 6개 글로벌 뉴스 소스에서 RSS 피드 파싱
2. **선별**: 최신성과 다양성 기반으로 TOP 10 선정
3. **AI 요약**: OpenAI GPT로 각 뉴스를 한국어로 요약
4. **블로그 생성**: HTML 형식의 블로그 포스트 생성
5. **업로드**: Tistory API를 통해 자동 포스팅

## 📝 로그

실행 로그는 `logs/` 디렉토리에 날짜별로 저장:

```
logs/news_bot_20251005.log
```

## 🛠️ 모듈 설명

### news_aggregator.py
- RSS 피드 파싱 및 뉴스 수집
- 최신성과 소스 다양성 기반 뉴스 선별
- HTML 태그 제거 및 텍스트 정제

### ai_summarizer.py
- OpenAI API를 사용한 뉴스 요약
- 배치 요약 처리
- HTML 블로그 포스트 생성

### tistory_uploader.py
- Tistory API 연동
- 포스트 업로드 및 수정
- 카테고리 관리

### main.py
- 전체 워크플로우 조율
- 스케줄링 관리
- 로깅 및 에러 처리

## 🔍 트러블슈팅

### "Configuration errors: TISTORY_ACCESS_TOKEN is not set"
- `.env` 파일을 생성하고 API 키를 올바르게 설정했는지 확인

### "ModuleNotFoundError: No module named 'requests'"
```bash
pip install -r requirements.txt
```

### RSS 피드 접근 오류
- 인터넷 연결 확인
- 특정 피드가 차단된 경우 `config.py`의 `NEWS_SOURCES`에서 해당 URL 제거 또는 교체

### OpenAI API 오류
- API 키가 유효한지 확인
- API 사용량 한도를 초과하지 않았는지 확인
- 모델명이 올바른지 확인 (gpt-3.5-turbo, gpt-4 등)

## 🎨 커스터마이징

### 뉴스 소스 추가
`config.py`의 `NEWS_SOURCES` 리스트에 RSS 피드 URL 추가:

```python
NEWS_SOURCES = [
    'http://rss.cnn.com/rss/edition_world.rss',
    'https://your-favorite-news.com/rss',  # 추가
]
```

### 포스트 스타일 변경
`ai_summarizer.py`의 `generate_blog_post()` 메서드에서 HTML 템플릿 수정

### 요약 프롬프트 변경
`ai_summarizer.py`의 `summarize_article()` 메서드에서 프롬프트 커스터마이징

## 📜 라이센스

이 프로젝트는 개인 학습 및 개발 목적으로 작성되었습니다.

## 🤝 기여

버그 리포트나 기능 제안은 이슈로 등록해주세요.

## ⚠️ 주의사항

- OpenAI API는 사용량에 따라 과금됩니다
- Tistory API 사용량 제한을 확인하세요
- 뉴스 저작권을 존중하고, 원문 링크를 반드시 포함하세요
- 자동화 봇 운영 시 각 플랫폼의 이용 약관을 준수하세요
