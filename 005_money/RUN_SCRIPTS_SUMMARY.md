# 🚀 실행 스크립트 완전 가이드

## 📋 업데이트된 실행 스크립트들

### 🎯 주요 실행 파일

| 파일명 | 타입 | 용도 | 추천도 |
|--------|------|------|--------|
| `./gui` | Bash | **GUI 전용 실행파일** | ⭐⭐⭐⭐⭐ |
| `./run.sh` | Bash | CLI 실행 + GUI 옵션 | ⭐⭐⭐⭐ |
| `run.py` | Python | CLI 실행 + GUI 옵션 | ⭐⭐⭐ |
| `run_gui.py` | Python | GUI 실행 (기존) | ⭐⭐ |
| `run_gui.sh` | Bash | GUI 실행 (기존) | ⭐⭐ |

## 🏆 최고 추천: `./gui`

### 특징
- ✅ **실행파일 형태**로 가장 사용하기 쉬움
- ✅ **포괄적인 시스템 검사** 및 환경 설정
- ✅ **아름다운 UI**와 상세한 안내
- ✅ **자동 오류 처리** 및 복구 기능

### 사용법
```bash
# 기본 GUI 실행
./gui

# 시스템 요구사항만 확인
./gui --check

# 환경 설정만 실행
./gui --setup-only

# 패키지 강제 재설치
./gui --force-install

# 도움말
./gui --help
```

## 🔧 CLI 모드: `./run.sh`

### 특징
- ✅ **CLI와 GUI 모드** 모두 지원
- ✅ **향상된 로고** 및 사용자 인터페이스
- ✅ **통합된 도움말** 시스템
- ✅ **자동 실행 조건** 처리

### 사용법
```bash
# 기본 CLI 실행
./run.sh

# GUI 모드로 전환
./run.sh --gui

# 대화형 설정
./run.sh --interactive

# 30초 간격으로 ETH 거래
./run.sh --coin ETH --interval 30s

# 사용 예시 보기
./run.sh --examples

# 도움말
./run.sh --help
```

## 🐍 Python 버전: `run.py`

### 특징
- ✅ **Python 기반** 실행 스크립트
- ✅ **GUI 지원** 추가
- ✅ **크로스 플랫폼** 호환성

### 사용법
```bash
# 기본 실행
python run.py

# GUI 모드
python run.py --gui

# 사용 예시
python run.py --examples
```

## 📊 기능 비교표

| 기능 | ./gui | ./run.sh | run.py | run_gui.py |
|------|-------|----------|--------|------------|
| GUI 실행 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| CLI 실행 | ❌ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ |
| 시스템 검사 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| 오류 처리 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| 사용자 친화성 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

## 🎮 GUI 사용 시나리오

### 시나리오 1: 첫 사용자 (권장)
```bash
./gui
```

### 시나리오 2: 빠른 GUI 실행
```bash
./run.sh --gui
```

### 시나리오 3: Python 선호자
```bash
python run.py --gui
```

## 🖥️ CLI 사용 시나리오

### 시나리오 1: 기본 CLI 실행
```bash
./run.sh
```

### 시나리오 2: 빠른 설정과 실행
```bash
./run.sh --coin ETH --amount 50000 --interval 1m
```

### 시나리오 3: 대화형 설정
```bash
./run.sh --interactive
```

## 🔧 환경 설정 시나리오

### 시나리오 1: 완전 자동 설정 (권장)
```bash
./gui --setup-only
```

### 시나리오 2: 강제 재설치
```bash
./gui --force-install
```

### 시나리오 3: 시스템 검사만
```bash
./gui --check
```

## 📱 모든 스크립트 공통 기능

### ✅ 공통 지원사항
- **가상환경 자동 생성** 및 활성화
- **의존성 자동 설치** (pandas, requests, schedule, numpy)
- **tkinter 호환성 검사**
- **Python 버전 확인** (3.7+)
- **설정 파일 검증**
- **안전한 종료** (Ctrl+C)

### ⚙️ 공통 옵션들
```bash
--setup-only      # 환경 설정만 실행
--skip-setup      # 환경 설정 건너뛰기
--force-install   # 패키지 강제 재설치
--help           # 도움말 표시
--examples       # 사용 예시 (./run.sh, run.py만)
```

## 🎯 권장 사용 순서

1. **처음 사용**: `./gui --check` (시스템 검사)
2. **환경 설정**: `./gui --setup-only` (환경 구성)
3. **GUI 실행**: `./gui` (기본 실행)
4. **CLI 필요시**: `./run.sh` (명령줄 실행)

## 🔍 문제 해결

### tkinter 오류 시
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# CentOS/RHEL
sudo yum install tkinter

# macOS
brew install python-tk

# 설치 후 확인
./gui --check
```

### 패키지 오류 시
```bash
# 강제 재설치
./gui --force-install

# 또는
./run.sh --force-install
```

### 권한 오류 시
```bash
# 실행 권한 부여
chmod +x gui run.sh run_gui.sh
```

## 💡 팁과 트릭

### 🚀 가장 빠른 실행 방법
```bash
./gui  # GUI가 필요할 때
./run.sh --interactive  # CLI 설정이 필요할 때
```

### 🎮 고급 사용법
```bash
# 특정 설정으로 바로 시작
./run.sh --coin ETH --amount 100000 --interval 5m --dry-run

# 설정 저장 후 재사용
./run.sh --save-config my-eth-config.json
./run.sh --config-file my-eth-config.json
```

### 📊 실시간 모니터링
```bash
# GUI에서 실시간 차트와 수익 현황 확인
./gui

# CLI에서 로그 확인
./run.sh --interval 30s
```

---

**🎯 결론**: `./gui`를 주요 실행 방법으로 사용하고, CLI가 필요한 경우 `./run.sh`를 사용하는 것을 강력히 권장합니다!