# 🚀 빠른 시작 가이드

## 5분 안에 시작하기

### 1️⃣ 의존성 설치

```bash
cd 006_auto_bot/001_code
pip install -r requirements.txt
```

### 2️⃣ 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (API 키 입력)
nano .env  # 또는 vi .env
```

필수 입력 항목:
- `TISTORY_ACCESS_TOKEN`: Tistory API 액세스 토큰
- `TISTORY_BLOG_NAME`: Tistory 블로그 이름
- `OPENAI_API_KEY`: OpenAI API 키

### 3️⃣ 테스트 실행

```bash
# 뉴스 수집 테스트 (포스팅 없음)
python main.py --test

# 또는 자동 실행 스크립트 사용
./run.sh test
```

### 4️⃣ 실제 실행

```bash
# 즉시 1회 실행
python main.py --mode once

# 또는
./run.sh once

# 매일 자동 실행 (스케줄링)
python main.py --mode scheduled

# 또는
./run.sh scheduled
```

## 📋 체크리스트

- [ ] Python 3.8+ 설치 확인
- [ ] pip 패키지 설치 완료
- [ ] `.env` 파일 생성 및 API 키 입력
- [ ] Tistory Access Token 발급
- [ ] OpenAI API 키 발급
- [ ] 테스트 모드 실행 성공
- [ ] 실제 포스팅 1회 성공

## 🔑 API 키 발급 (간단 버전)

### Tistory
1. https://www.tistory.com/guide/api/manage/register
2. 앱 등록 → Client ID, Secret 발급
3. OAuth 인증 → Access Token 획득

### OpenAI
1. https://platform.openai.com/api-keys
2. "Create new secret key" 클릭
3. 키 복사 → `.env`에 붙여넣기

## 💡 유용한 명령어

```bash
# 로그 확인
tail -f logs/news_bot_*.log

# 가상환경 활성화
source .venv/bin/activate

# 패키지 재설치
pip install -r requirements.txt --upgrade

# 뉴스 수집만 테스트
python ../003_test_code/test_news_fetch.py
```

## ⚠️ 주의사항

1. **API 요금**: OpenAI API는 사용량에 따라 과금됩니다
2. **테스트 먼저**: 실제 포스팅 전에 `--test` 모드로 먼저 테스트하세요
3. **Access Token 보안**: `.env` 파일은 절대 git에 커밋하지 마세요
4. **.gitignore 추가**: `.env` 파일을 `.gitignore`에 추가하세요

## 🆘 문제 해결

### "Configuration errors: TISTORY_ACCESS_TOKEN is not set"
→ `.env` 파일에 API 키를 올바르게 입력했는지 확인

### "ModuleNotFoundError"
→ `pip install -r requirements.txt` 실행

### "RSS feed error"
→ 인터넷 연결 확인

자세한 내용은 `README.md` 참조
