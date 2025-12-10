# Cryptocurrency Trading Bot

Bithumb API를 사용한 암호화폐 자동매매 봇입니다.

## Quick Start

### 1. 환경 설정

```bash
cd 005_money

# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정 (.env.example 참고)
cp .env.example .env
# .env 파일에 API 키 설정
```

### 2. pybithumb 설치

```bash
# pybithumb이 없으면 자동으로 클론됨
git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git
```

## 실행 스크립트

모든 스크립트는 `scripts/` 폴더에 있습니다.

| 스크립트 | 설명 |
|----------|------|
| `run_v1_cli.sh` | Ver1 CLI 모드 (Elite 8-Indicator) |
| `run_v1_gui.sh` | Ver1 GUI 모드 |
| `run_v2_cli.sh` | Ver2 CLI 모드 (Backtrader) |
| `run_v2_gui.sh` | Ver2 GUI 모드 |
| `run_v3_cli.sh` | Ver3 CLI 모드 (Portfolio) |
| `run_v3_gui.sh` | Ver3 GUI 모드 |
| `close_position.sh` | 포지션 수동 청산 |
| `close_positions.sh` | 전체 포지션 청산 |

### 실행 예시

```bash
# Ver3 GUI 실행 (권장)
./scripts/run_v3_gui.sh

# Ver3 CLI 실행
./scripts/run_v3_cli.sh

# Ver1 CLI 실행
./scripts/run_v1_cli.sh
```

## 버전별 특징

### Ver1 - Elite 8-Indicator Strategy
- MA, RSI, Bollinger Bands, Volume, MACD, ATR, Stochastic, ADX
- 가중치 기반 신호 조합 시스템

### Ver2 - Backtrader Strategy
- Backtrader 프레임워크 기반
- 백테스팅 지원

### Ver3 - Portfolio Management
- 멀티 코인 포트폴리오 관리
- 피라미딩, 이익실현 자동화

## 프로젝트 구조

```
005_money/
├── 001_python_code/    # 메인 소스 코드
│   ├── ver1/           # Ver1 전략
│   ├── ver2/           # Ver2 전략
│   ├── ver3/           # Ver3 전략
│   └── lib/            # 공유 라이브러리
├── scripts/            # 실행 스크립트
├── tests/              # 테스트 코드
├── logs/               # 로그 파일
└── pybithumb/          # Bithumb API 라이브러리
```

## 주의사항

- 실제 거래 전 반드시 `dry_run: True` 설정으로 테스트하세요
- API 키는 환경 변수 또는 .env 파일로 관리하세요
- 투자 손실에 대한 책임은 사용자에게 있습니다
