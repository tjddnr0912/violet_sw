# 📘 자동 뉴스 요약 블로그 포스팅 봇 - 사용 가이드

## 목차
- [시작하기](#시작하기)
- [설치 방법](#설치-방법)
- [설정 방법](#설정-방법)
- [실행 방법](#실행-방법)
- [트러블슈팅](#트러블슈팅)
- [고급 설정](#고급-설정)

---

## 시작하기

### 필수 요구사항
- Python 3.8 이상
- Google Gemini API 키 (무료)

### 준비물 체크리스트
- [ ] Python 설치 완료
- [ ] Google Gemini API 키 발급

---

## 설치 방법

### 1. 저장소 클론
```bash
git clone <repository-url>
cd 006_auto_bot
```

### 2. 가상 환경 생성 및 활성화
```bash
cd 001_code

# 가상 환경 생성
python3 -m venv .venv

# 가상 환경 활성화
# macOS/Linux:
source .venv/bin/activate

# Windows (Command Prompt):
# .venv\Scripts\activate.bat

# Windows (PowerShell):
# .venv\Scripts\Activate.ps1
```

가상 환경이 활성화되면 프롬프트 앞에 `(.venv)`가 표시됩니다.

### 3. 의존성 설치
```bash
pip install -r requirements.txt
```

설치되는 패키지:
- `requests` - HTTP 요청 처리
- `python-dotenv` - 환경 변수 관리
- `google-generativeai` - Google Gemini API
- `feedparser` - RSS 피드 파싱
- `beautifulsoup4` - HTML 처리
- `schedule` - 작업 스케줄링

---

## 설정 방법

### 1. Google Gemini API 키 발급

1. [Google AI Studio](https://aistudio.google.com/app/apikey) 방문
2. Google 계정으로 로그인
3. "Create API Key" 클릭
4. API 키 복사 (예: `AIzaSy...`)

**무료 할당량**: 월 150만 토큰 (충분히 무료로 사용 가능)

### 2. 환경 변수 파일 설정

#### 2-1. .env 파일 생성
```bash
cd 001_code
cp .env.example .env
```

#### 2-2. .env 파일 편집
```bash
nano .env
# 또는
vim .env
# 또는
code .env  # VS Code 사용 시
```

#### 2-3. 발급받은 값 입력
```env
# Google Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
```

**주의사항**:
- API 키는 절대 외부에 공유하지 마세요
- `.env` 파일은 git에 커밋되지 않습니다 (.gitignore에 포함됨)

---

## 실행 방법

### 1. 즉시 실행 (테스트용)
뉴스를 즉시 수집하고 마크다운 파일로 저장합니다.

```bash
cd 001_code

# 가상 환경 활성화 (아직 활성화하지 않은 경우)
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate.bat  # Windows

python main.py
```

**실행 과정**:
1. 설정 검증
2. 6개 RSS 소스에서 뉴스 수집
3. 최신 뉴스 10개 선별
4. Gemini AI로 한국어 요약
5. Markdown 포맷으로 변환
6. `004_News_paper/YYYYMMDD/` 폴더에 자동 저장

**예상 소요 시간**: 2~5분

**저장 경로**:
- 파일 위치: `004_News_paper/YYYYMMDD/news_summary_YYYYMMDD_HHMMSS.md`
- 예시: `004_News_paper/20251011/news_summary_20251011_090523.md`

### 2. 스케줄링 실행 (자동화)
매일 정해진 시간에 자동으로 실행합니다.

```bash
# 가상 환경 활성화 후 실행
source .venv/bin/activate  # macOS/Linux
python main.py
```

기본 설정: 매일 오전 9시 실행

**백그라운드 실행 (권장)**:
```bash
# nohup 사용
source .venv/bin/activate
nohup python main.py > output.log 2>&1 &

# screen 사용
screen -S newsbot
source .venv/bin/activate
python main.py
# Ctrl+A, D로 detach

# systemd 사용 (Linux)
# 별도 설정 필요 (고급 설정 참조)
```

### 3. 단일 기능 테스트

#### 뉴스 수집만 테스트
```python
from news_aggregator import NewsAggregator
from config import config

aggregator = NewsAggregator(config.NEWS_SOURCES)
news_items = aggregator.collect_news()
print(f"수집된 뉴스: {len(news_items)}개")
```

#### AI 요약만 테스트
```python
from ai_summarizer import AISummarizer
from config import config

summarizer = AISummarizer(config.GEMINI_API_KEY, config.GEMINI_MODEL)
summary = summarizer.summarize_article(
    title="테스트 제목",
    description="테스트 내용입니다."
)
print(summary)
```

---

## 트러블슈팅

### 문제 1: ModuleNotFoundError
**증상**:
```
ModuleNotFoundError: No module named 'google.generativeai'
```

**해결**:
```bash
# 가상 환경이 활성화되었는지 확인
# 프롬프트에 (.venv)가 표시되어야 함
source .venv/bin/activate  # macOS/Linux

# 의존성 재설치
pip install -r requirements.txt
```

### 문제 2: Gemini API 에러
**증상**:
```
google.api_core.exceptions.PermissionDenied: 403 API key not valid
```

**해결**:
1. [Google AI Studio](https://aistudio.google.com/app/apikey)에서 API 키 확인
2. API 키가 활성화되어 있는지 확인
3. `.env` 파일의 `GEMINI_API_KEY` 재확인

### 문제 3: RSS 피드 수집 실패
**증상**:
```
Error fetching feed: Timeout
```

**해결**:
1. 인터넷 연결 확인
2. 방화벽 설정 확인
3. `config.py`에서 `NEWS_SOURCES` 일부 제거 후 재시도

### 문제 4: 마크다운 파일 저장 실패
**증상**:
```
Error saving markdown file: Permission denied
```

**해결**:
1. `004_News_paper` 폴더 권한 확인
2. 디스크 용량 확인
3. 상대 경로 문제: `001_code` 디렉토리에서 실행했는지 확인

### 문제 5: 스케줄링이 작동하지 않음
**증상**: 프로그램이 바로 종료됨

**해결**:
- `main.py`의 `run()` 함수 확인
- 스케줄링은 무한 루프로 동작하므로 백그라운드 실행 필요

---

## 고급 설정

### 1. 실행 시간 변경

`config.py` 수정:
```python
# Scheduling
POSTING_TIME = "09:00"  # HH:MM 형식 (예: "14:30")
```

### 2. 뉴스 개수 조정

`config.py` 수정:
```python
# Bot Settings
MAX_NEWS_COUNT = 10  # 원하는 개수 (예: 5, 15, 20)
```

### 3. 요약 길이 조정

`config.py` 수정:
```python
# Bot Settings
SUMMARY_MAX_LENGTH = 300  # 자 단위 (예: 200, 500)
```

### 4. RSS 소스 추가/제거

`config.py` 수정:
```python
NEWS_SOURCES = [
    'http://rss.cnn.com/rss/edition_world.rss',
    'https://feeds.bbci.co.uk/news/world/rss.xml',
    # 원하는 RSS 피드 추가
    'https://example.com/rss',
]
```

### 5. Gemini 모델 변경

`.env` 파일 수정:
```env
# Gemini 1.5 Pro로 변경 (더 높은 품질, 더 느림)
GEMINI_MODEL=gemini-1.5-pro

# Gemini 1.5 Flash (기본값, 빠르고 저렴)
GEMINI_MODEL=gemini-1.5-flash
```

### 6. systemd 서비스 설정 (Linux)

#### 6-1. 서비스 파일 생성
```bash
sudo nano /etc/systemd/system/newsbot.service
```

#### 6-2. 내용 입력
```ini
[Unit]
Description=Auto News Summary Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/006_auto_bot/001_code
ExecStart=/path/to/006_auto_bot/001_code/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 6-3. 서비스 활성화
```bash
sudo systemctl daemon-reload
sudo systemctl enable newsbot
sudo systemctl start newsbot
sudo systemctl status newsbot
```

### 7. 로그 확인

```bash
# 실행 로그 확인
tail -f output.log

# systemd 로그 확인
sudo journalctl -u newsbot -f
```

---

## 사용 팁

### 1. 테스트 시 주의사항
- 처음 실행 시 `MAX_NEWS_COUNT`를 1~2개로 설정하여 테스트
- API 할당량 확인 (Gemini: 월 150만 토큰)

### 2. 마크다운 포맷 커스터마이징
`markdown_writer.py`의 `_generate_markdown()` 함수에서 마크다운 템플릿 수정 가능

### 3. 출력 디렉토리 변경
`config.py`에서 `OUTPUT_DIR` 수정:
```python
# Output Settings
OUTPUT_DIR = '../004_News_paper'  # 원하는 경로로 변경
```

### 4. 에러 알림 설정
향후 확장: 에러 발생 시 이메일/슬랙 알림 기능 추가 가능

### 5. 백업
`.env` 파일과 `004_News_paper` 폴더 백업 권장

---

## 문의 및 지원

- **이슈 등록**: GitHub Issues
- **문서**: `002_doc/` 디렉토리 참조
- **프로젝트 개요**: `000_proposal/PROJECT_OVERVIEW.md`

---

**Happy Automating! 🤖**
