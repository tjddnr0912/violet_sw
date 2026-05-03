# 005_money 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 설명 |
|------|------|------|------|
| `BITHUMB_API_KEY` | ✅ | — | 빗썸 API 키 |
| `BITHUMB_SECRET_KEY` | ✅ | — | 빗썸 시크릿 키 |
| `TELEGRAM_BOT_TOKEN` | ❌ | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | ❌ | — | Telegram chat ID |
| `TELEGRAM_NOTIFICATIONS_ENABLED` | ❌ | True | Telegram 알림 on/off |

## 주요 설정 파일

| 파일 | 용도 |
|------|------|
| `001_python_code/ver3/config_v3.py` | 전략 파라미터 (PORTFOLIO_CONFIG, INDICATOR_CONFIG, RISK_CONFIG) — 400줄 |
| `001_python_code/ver3/config_base.py` | 기본 상수 (공통) |
| `logs/positions_v3.json` | 현재 포지션 상태 |
| `logs/dynamic_factors_v3.json` | 동적 팩터 상태 |
| `logs/transaction_history.json` | 거래 기록 |
| `logs/performance_history_v3.json` | 성과 기록 |

## 핵심 파라미터

### PORTFOLIO_CONFIG

```python
{
    'coins': ['BTC', 'ETH', 'XRP'],   # 모니터링 코인
    'max_positions': 2,                # 최대 동시 포지션
    'check_interval': 900,             # 분석 주기 (초, 15분)
    'dry_run': True,                   # True=시뮬레이션, False=실전
}
```

### INDICATOR_CONFIG

```python
{
    'ema_short': 50,
    'ema_long': 200,
    'bb_period': 20,
    'bb_std': 2.0,
    'rsi_period': 14,
    'atr_period': 14,
    'stoch_k_period': 14,
    'stoch_d_period': 3,
}
```

### RISK_CONFIG

```python
{
    'chandelier_multiplier': 3.0,      # 손절 ATR 배수
    'max_daily_loss_pct': 3.0,         # 일일 최대 손실 3%
    'max_consecutive_losses': 3,        # 관찰 모드 진입 임계
}
```

## 시크릿 마스킹 정책

- 로그·스택트레이스에 `BITHUMB_SECRET_KEY` 직접 노출 금지
- `.env` 파일은 절대 git commit 금지 (`.gitignore` 등재됨)
- 디버깅 시 길이만 출력: `echo "LEN=${#BITHUMB_API_KEY}"`

## 핵심 의존성

```
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
requests>=2.28.0
schedule>=1.2.0
python-telegram-bot>=20.0
python-dotenv>=1.0.0
```

Python 3.13+ 필수.

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
