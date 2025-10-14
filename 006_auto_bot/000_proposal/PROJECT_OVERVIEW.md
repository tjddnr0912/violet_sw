# 자동 뉴스 요약 블로그 포스팅 봇 - 프로젝트 개요

## 📌 프로젝트 목표

매일 전세계 주요 뉴스를 자동으로 수집하고, AI를 활용하여 한국어로 요약한 후, Tistory 블로그에 자동으로 업로드하는 완전 자동화 시스템을 구축한다.

## 🎯 핵심 기능

### 1. 뉴스 수집 (News Aggregation)
- **입력**: 6개 글로벌 뉴스 RSS 피드 (CNN, BBC, Al Jazeera, The Guardian, Reuters, NYT)
- **처리**:
  - RSS 피드 파싱 및 최신 뉴스 수집
  - HTML 태그 제거 및 텍스트 정제
  - 중복 제거
- **출력**: 정제된 뉴스 아이템 리스트

### 2. 뉴스 선별 (News Selection)
- **입력**: 수집된 모든 뉴스 아이템
- **처리**:
  - 발행 시간 기준 최신성 평가
  - 소스 다양성 보장 (각 소스에서 균등하게 선택)
  - 중요도 평가 (향후 확장 가능)
- **출력**: TOP 10 뉴스 아이템

### 3. AI 요약 (AI Summarization)
- **입력**: 선별된 뉴스 아이템 (제목 + 본문)
- **처리**:
  - Google Gemini API 호출
  - 한국어 요약 생성 (300자 이내)
  - 핵심 내용 추출 및 객관적 문체 유지
- **출력**: 한국어 요약문

### 4. 블로그 포스트 생성 (Blog Post Generation)
- **입력**: 요약된 뉴스 10개
- **처리**:
  - HTML 템플릿 적용
  - 제목, 출처, 발행일, 요약문, 원문 링크 포함
  - 시각적 구조화 (번호, 구분선, 인용 블록)
- **출력**: 완성된 HTML 블로그 포스트

### 5. 자동 업로드 (Auto Upload)
- **입력**: 생성된 블로그 포스트
- **처리**:
  - Tistory API 인증
  - 포스트 메타데이터 설정 (제목, 태그, 공개 여부)
  - API 호출 및 업로드
- **출력**: 발행된 블로그 포스트 URL

### 6. 스케줄링 (Scheduling)
- **기능**: 매일 정해진 시간에 자동 실행
- **설정**: 기본값 09:00 (사용자 설정 가능)

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│                   (Orchestrator & Scheduler)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ├─────────────────┐
                              ↓                 ↓
                    ┌──────────────────┐  ┌─────────────────┐
                    │ news_aggregator  │  │   ai_summarizer │
                    │     .py          │  │       .py       │
                    └──────────────────┘  └─────────────────┘
                              │                 │
                              ↓                 ↓
                    ┌──────────────────┐  ┌─────────────────┐
                    │   RSS Feeds      │  │  Gemini API     │
                    │   (6 sources)    │  │  (1.5-flash)    │
                    └──────────────────┘  └─────────────────┘
                              │                 │
                              └────────┬────────┘
                                       ↓
                              ┌─────────────────┐
                              │ tistory_uploader│
                              │      .py        │
                              └─────────────────┘
                                       │
                                       ↓
                              ┌─────────────────┐
                              │  Tistory API    │
                              │  (Blog Post)    │
                              └─────────────────┘
```

## 🔄 워크플로우

```
[Start] → [뉴스 수집] → [TOP 10 선별] → [AI 요약] → [블로그 생성] → [업로드] → [End]
   ↓           ↓              ↓            ↓            ↓            ↓
 09:00      6개 소스      최신+다양성    Gemini API   HTML 포맷   Tistory API
            30개 수집       10개 선택     요약 생성    템플릿 적용   발행
```

## 🛠️ 기술 스택

### 언어
- Python 3.8+

### 주요 라이브러리
- `feedparser`: RSS 피드 파싱
- `requests`: HTTP 요청 (Tistory API)
- `google-generativeai`: Google Gemini API 클라이언트
- `beautifulsoup4`: HTML 파싱 및 정제
- `schedule`: 작업 스케줄링
- `python-dotenv`: 환경 변수 관리

### 외부 API
- **Google Gemini API**: Gemini 1.5 Flash 모델을 사용한 요약
- **Tistory API**: 블로그 포스트 업로드 및 관리

### 데이터 소스
- CNN World News RSS
- BBC World News RSS
- Al Jazeera RSS
- The Guardian World News RSS
- Reuters World News RSS
- New York Times World News RSS

## 📊 데이터 흐름

### 1. 입력 데이터
```
RSS Feed Entry {
  title: string
  link: string
  description: string (HTML)
  published_date: datetime
}
```

### 2. 정제된 뉴스 아이템
```
News Item {
  title: string
  link: string
  description: string (plain text)
  published_date: datetime
  source: string
  source_url: string
}
```

### 3. 요약된 뉴스 아이템
```
Summarized News Item {
  ... (News Item의 모든 필드)
  summary: string (Korean, 300자 이내)
}
```

### 4. 블로그 포스트
```
Blog Post {
  title: string (예: "2025년 10월 5일 글로벌 주요 뉴스 TOP 10")
  content: HTML string
  tags: string (comma-separated)
  visibility: int (0=비공개, 1=보호, 3=발행)
}
```

## 🔐 보안 고려사항

### API 키 관리
- `.env` 파일에 저장 (git 추적 제외)
- 환경 변수로 로드
- 하드코딩 금지

### API 사용량 제한
- OpenAI API: 토큰 사용량 모니터링 필요
- Tistory API: Rate limit 확인

### 에러 처리
- API 호출 실패 시 재시도 로직
- 네트워크 오류 처리
- 로깅을 통한 문제 추적

## 📈 향후 확장 가능성

### 단기 (1-2주)
- [ ] 카테고리 자동 분류 (정치, 경제, 기술 등)
- [ ] 이미지 자동 첨부 (뉴스 썸네일)
- [ ] 다중 블로그 플랫폼 지원 (네이버, 티스토리, 브런치)

### 중기 (1-2개월)
- [ ] 감정 분석을 통한 뉴스 중요도 평가
- [ ] 키워드 추출 및 트렌드 분석
- [ ] 사용자 맞춤형 뉴스 필터링
- [ ] 웹 대시보드 구축 (Flask/FastAPI)

### 장기 (3개월+)
- [ ] 다국어 지원 (영어, 일본어, 중국어 요약)
- [ ] 뉴스 팩트 체크 기능
- [ ] 소셜 미디어 자동 공유
- [ ] 통계 및 분석 대시보드
- [ ] 커스텀 AI 모델 파인튜닝

## 💰 비용 예측

### Google Gemini API (Gemini 1.5 Flash 기준)
- 1일 10개 뉴스 × 평균 500 토큰 = 5,000 토큰/일
- 월간: 150,000 토큰
- **무료 할당량**: 월 150만 토큰 (충분히 무료로 사용 가능)
- 연간: **$0** (무료 범위 내)

### Tistory API
- 무료 (사용량 제한 내)

### 총 예상 비용
- **월 $0** (완전 무료)

## 📝 성공 지표

1. **안정성**: 30일 연속 무오류 실행
2. **정확성**: AI 요약 품질 평가 (수동 검토)
3. **효율성**: 전체 프로세스 실행 시간 < 5분
4. **다양성**: 6개 소스 모두에서 균등하게 뉴스 수집

## 🎓 학습 목표

이 프로젝트를 통해 다음을 학습합니다:

1. **API 통합**: Google Gemini, Tistory 등 외부 API 활용
2. **데이터 처리**: RSS 파싱, 텍스트 정제, HTML 생성
3. **AI 활용**: Gemini를 활용한 실제 문제 해결
4. **자동화**: 스케줄링 및 무인 운영 시스템 구축
5. **모듈화**: 재사용 가능한 코드 설계
