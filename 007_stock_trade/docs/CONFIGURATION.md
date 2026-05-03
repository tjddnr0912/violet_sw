# 007_stock_trade 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 설명 |
|------|------|------|------|
| `KIS_APP_KEY` | ✅ | — | KIS Open API 앱키 |
| `KIS_APP_SECRET` | ✅ | — | KIS Open API 시크릿 |
| `KIS_ACCOUNT_NO` | ✅ | — | 종합계좌번호 (`12345678-01` 형식, 8자리 + 상품코드) |
| `TRADING_MODE` | ✅ | `VIRTUAL` | `VIRTUAL` (모의투자) \| `REAL` (실전) |
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | ✅ | — | Telegram chat ID |

## 설정 파일 (`config/`)

| 파일 | 용도 |
|------|------|
| `config/system_config.json` | 시스템 설정 (텔레그램 명령으로 변경됨) |
| `config/optimal_weights.json` | 팩터 가중치 (`factor_weights`: V/M/Q/Vol, `signal_weights`: 모니터링용) |

`config/optimal_weights.json::factor_weights`가 **Single Source of Truth**. 다른 곳에서 가중치 하드코딩 금지.

## 데이터 파일 (`data/quant/`)

| 파일 | 용도 |
|------|------|
| `data/quant/engine_state.json` | 포지션, 주문 상태, 리밸런싱 추적 |
| `data/quant/daily_history.json` | 일별 자산 스냅샷 (2026-02 추가) |
| `data/quant/transaction_journal.json` | 전체 거래 일지 (2026-02 추가) |
| `logs/daemon_YYYYMMDD.log` | 일별 로그 |

### `engine_state.json` 주요 필드

```json
{
  "positions": [...],
  "last_rebalance_month": "2026-01",
  "last_urgent_rebalance_month": "2026-01",
  "last_screening_date": "2026-01-27T08:30:00"
}
```

리밸런싱 추적 변수:

| 유형 | 추적 변수 | 제한 |
|------|----------|------|
| 월초 리밸런싱 | `last_rebalance_month` | 월 1회 |
| 긴급 리밸런싱 | `last_urgent_rebalance_month` | 월 1회 (2026-01-27 추가) |

## 핵심 의존성

```
pykrx>=1.2.3       # ⚠️ 1.0.x 호환성 문제, 1.2.3 미만 금지
pandas>=2.0.0
numpy>=1.24.0
requests>=2.28.0
python-dotenv>=1.0.0
python-telegram-bot>=20.0
schedule>=1.2.0
```

⚠️ **pykrx 버전 주의**: 1.0.x는 KRX API 변경으로 실패. Python 3.14에서는 pykrx 1.2.x도 호환성 문제 (네이버 금융 fallback으로 우회).

## API Rate Limit 모드별 설정

```python
# src/quant_modules/order_executor.py
API_DELAY_VIRTUAL = 500   # ms — 모의투자 (5건/초)
API_DELAY_REAL    = 100   # ms — 실전 (20건/초)
```

여러 종목 처리 루프 시 자동 적용:

```python
for i, code in enumerate(codes):
    if i > 0:
        time.sleep(0.15)  # API Rate Limit 방지
    result = api.call(code)
```

## 시크릿 마스킹 정책

- 로그·스택트레이스에 `KIS_APP_SECRET`, `TELEGRAM_BOT_TOKEN` 직접 노출 금지
- `.env`는 절대 git commit 금지 (`.gitignore` 등재됨)
- KIS 토큰은 `data/auth/token.json`에 캐시 (자동 갱신)

## 텔레그램 알림 설정

008(미국주식 퀀트), 014(casper)와 **다른 토큰** 사용. 한국주식 봇 전용.

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
