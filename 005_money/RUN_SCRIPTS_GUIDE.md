# 🚀 실행 스크립트 가이드

## 개요

업데이트된 `run.py`와 `run.sh` 스크립트는 새로운 명령행 인수와 동적 설정을 완벽 지원합니다.

## 🔧 run.py (Python 스크립트)

### 기본 사용법
```bash
python run.py [run.py 옵션] [봇 옵션]
```

### run.py 전용 옵션
- `--setup-only`: 환경 설정만 하고 봇은 실행하지 않음
- `--skip-setup`: 환경 설정을 건너뛰고 봇만 실행
- `--examples`: 사용 예시 표시
- `--force-install`: 패키지 강제 재설치

### 사용 예시
```bash
# 사용 예시 보기
python run.py --examples

# 환경만 설정하고 종료
python run.py --setup-only

# 30초마다 체크, 이더리움 거래
python run.py --interval 30s --coin ETH

# 설정 건너뛰고 바로 실행
python run.py --skip-setup --show-config
```

## 🔧 run.sh (Bash 스크립트)

### 기본 사용법
```bash
./run.sh [run.sh 옵션] [봇 옵션]
```

### run.sh 전용 옵션
- `--setup-only`: 환경 설정만 하고 봇은 실행하지 않음
- `--skip-setup`: 환경 설정을 건너뛰고 봇만 실행
- `--examples`: 사용 예시 표시
- `--force-install`: 패키지 강제 재설치
- `--help`: 도움말 표시

### 사용 예시
```bash
# 도움말 보기
./run.sh --help

# 사용 예시 보기
./run.sh --examples

# 1분마다 체크, 5만원씩 거래
./run.sh --interval 1m --amount 50000

# 대화형 설정 모드
./run.sh --interactive
```

## 🎯 주요 개선사항

### 1. 명령행 인수 완벽 지원
- 모든 봇 옵션을 `run.py`/`run.sh`를 통해 전달 가능
- 자동으로 `main.py`로 전달됨

### 2. 지능적 사용자 확인
```bash
# 자동 실행 (확인 없음)
python run.py --show-config
python run.py --interactive
python run.py --help

# 확인 필요 (일반 거래 실행)
python run.py --interval 30s
```

### 3. 옵션 시각화
실행 시 설정된 옵션을 명확히 표시:
```
📋 설정된 옵션:
  ⏰ 체크 간격: 30s
  💰 거래 코인: ETH
  💵 거래 금액: 50000원
  ⚠️  모의 거래 모드
```

### 4. 색상 지원 (run.sh)
- 🔴 빨간색: 실제 거래 모드 경고
- 🟡 노란색: 모의 거래 모드
- 🟢 초록색: 성공 메시지
- 🔵 파란색: 제목 및 정보

## 🔄 워크플로우

### 첫 설치 및 실행
```bash
# 1. 전체 설정 + 기본 실행
python run.py

# 2. 또는 환경만 설정
python run.py --setup-only
```

### 일상적 사용
```bash
# 1. 빠른 실행 (설정 건너뛰기)
python run.py --skip-setup --interval 5m

# 2. 특정 설정으로 실행
./run.sh --coin ETH --amount 30000 --interval 1m
```

### 설정 실험
```bash
# 1. 대화형으로 설정 변경
python run.py --interactive

# 2. 현재 설정 확인
python run.py --show-config

# 3. 다양한 조합 테스트
python run.py --coin BTC --interval 30s --dry-run
```

## 🛡️ 안전 기능

### 1. 환경 검증
- Python 버전 자동 확인 (3.7 이상 필요)
- 필수 파일 존재 확인
- 의존성 패키지 자동 설치

### 2. 설정 보호
- API 키 설정 상태 자동 확인
- 모의 거래 모드 기본 활성화
- 실제 거래 시 명확한 경고

### 3. 사용자 경험
- 명확한 옵션 표시
- 색상으로 구분된 메시지
- 자동 완성 및 스마트 기본값

## 🎨 고급 활용

### 조건부 실행
```bash
# API 키가 설정된 경우만 실제 거래
if [[ "$API_CONFIGURED" == "True" ]]; then
    ./run.sh --live --interval 5m
else
    ./run.sh --dry-run --interval 30s
fi
```

### 배치 작업
```bash
# 여러 설정 테스트
for interval in 30s 1m 5m; do
    echo "Testing with $interval interval..."
    python run.py --setup-only
    python run.py --skip-setup --interval $interval --dry-run
done
```

### 설정 백업
```bash
# 현재 설정을 파일로 저장
python run.py --save-config backup_$(date +%Y%m%d).json

# 저장된 설정으로 실행
python run.py --config-file backup_20241201.json
```

## 🔧 문제 해결

### 패키지 문제
```bash
# 패키지 강제 재설치
python run.py --force-install --setup-only
```

### 환경 문제
```bash
# 가상환경 재생성
rm -rf .venv
python run.py --setup-only
```

### 설정 문제
```bash
# 설정 초기화
python run.py --reset-config
```

이제 `run.py`와 `run.sh` 모두 새로운 동적 설정 시스템을 완벽 지원합니다!