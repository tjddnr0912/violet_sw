# Casper 설정

## 환경변수 (`.env`)

| 이름 | 필수 | 기본값 | 범위/타입 | 설명 |
|------|------|------|---------|------|
| `KIS_APP_KEY` | ✅ | — | string | 한국투자증권 실전투자 앱키 |
| `KIS_APP_SECRET` | ✅ | — | string (base64) | 실전투자 시크릿 (trailing `=` padding 주의) |
| `KIS_ACCOUNT_NO` | ✅ | — | 8자리 숫자 | 종합계좌번호 |
| `TRADING_MODE` | ✅ | `paper` | `paper` \| `live` | 거래 모드 |
| `TEST_MODE` | ❌ | `off` | `on` \| `off` | live지만 1주 고정 (실거래 최소화 검증용) |
| `TELEGRAM_BOT_TOKEN` | ❌ | — | string | 008과 동일 토큰 (모든 프로젝트 알림 통합) |
| `TELEGRAM_CHAT_ID` | ❌ | — | string | 008과 동일 chat_id |

### ICT phase env overrides (`.env`)

모든 default OFF. 켜진 채로 JSON에 기록되어도 env가 `off`/`false`/`0`이면 그것이 우선한다.

| 이름 | 기본 | 의미 |
|------|:---:|------|
| `ICT_KILLZONE_ENABLED` | off | Killzone 시간 필터 |
| `ICT_ALLOWED_KILLZONES` | `AM_MACRO` | CSV — 허용 Killzone 목록 |
| `ICT_REQUIRE_DISPLACEMENT` | off | 5분봉 displacement 필수화 |
| `ICT_DISP_ATR_MULT` / `ICT_DISP_MAX_WICK` / `ICT_DISP_PREV_MULT` | 1.0 / 0.50 / 1.5 | displacement 임계값 |
| `ICT_REQUIRE_SWEEP_CHOCH` | off | Sweep + CHoCH 게이트 |
| `ICT_SWEEP_LOOKBACK` / `ICT_CHOCH_LOOKBACK` | 6 / 6 | lookback |
| `ICT_SWEEP_MIN_BREACH_PCT` / `ICT_SWEEP_MIN_WICK_RATIO` | 0.0005 / 0.60 | sweep 임계값 |
| `ICT_BEAR_FVG_FOR_SQQQ` | off | QQQ bear FVG → SQQQ Long 매핑 |
| `ICT_BULL_FVG_FOR_TQQQ` | off | QQQ bull FVG → TQQQ Long 매핑 |
| `ICT_DAILY_BIAS_SKIP_NEUTRAL` | off | Daily bias가 neutral인 날 매매 skip |
| `ICT_USE_MULTI_TF_SL` / `ICT_MTF_LOOKBACK_MIN` | off / 15 | 1분봉 swing으로 SL 단축 |
| `ICT_USE_OTE` / `ICT_FIB_LEVEL` | off / 0.705 | OTE 진입 사용 + 피보 레벨 |
| `ICT_REQUIRE_UNICORN` | off | Breaker ∩ FVG 검증 |
| `ICT_USE_POWER_OF_3` | off | NQ futures Judas Swing 가산 |
| `ICT_QQQ_PRIMARY` | off | **P2 (2026-05-12)** — QQQ를 single signal source로, dual_scan 무시 |

### 시크릿 마스킹 정책

- 로그·스택트레이스에 `KIS_APP_SECRET` 직접 노출 금지
- 디버깅 시 길이만 출력: `echo "SEC_LEN=${#KIS_APP_SECRET}"`
- `.env` 파일은 절대 git commit 금지 (`.gitignore`에 등재됨)

### `.env` 로드 경로

1. `run_casper.sh`가 bash로 export (IFS 안전 패턴 사용 — [TROUBLESHOOTING.md](TROUBLESHOOTING.md) 참고)
2. Python 측 `src/utils/config.py::load_env`가 `load_dotenv(env_path, override=True)`로 재읽어 덮어쓰기 (이중 방어)
3. `.env` 파일이 단일 source of truth

## 파라미터 dict (`params`)

`src/utils/config.py`가 다음 구조로 메모리에 로드. 모든 모듈은 `bot.params` 통해 참조.

```python
{
    "strategy": {
        "orb_minutes": 15,
        "scan_window": ("09:45", "10:55"),  # ET
        "force_close_at": "15:50",
        "ma_period": 20,                     # QQQ MA20 트렌드 기준
    },
    "entry": {
        "rr_ratio": 3.0,                     # R:R (2026-05-01 1:2 → 1:3)
        "fvg_min_size": 0.0015,
        "strict_fvg": True,                  # 2026-05-06: FVG가 ORB 라인 가로지를 때만 유효
    },
    "mode": {
        "dual_scan": True,                   # 2026-05-06: TQQQ+SQQQ 양쪽 동시 스캔 default
        "qqq_primary": False,                # 2026-05-12 P2: QQQ만 signal source로 일원화 (default off)
    },
    "risk": {
        "max_position_pct": 0.99,            # FX/정산 lag 안전 floor 1%
        "vix_min": 12.0,
        "vix_max": 30.0,
        "circuit_breaker": {
            "consecutive_losses": 3,
            "weekly_loss_pct": 0.03,
        },
    },
    "order": {
        "buy_slippage_pct": 0.01,            # 매수 limit = price × 1.01
        "sell_slippage_pct": 0.03,           # 매도 limit = price × 0.97 (fill buffer)
    },
    "commission": {
        "rate_per_side": 0.0025,             # 0.25% (2026-05-01 0.0009 → 0.0025)
    },
}
```

## R:R 1:3 + commission 0.25% 튜닝 (2026-05-01)

`commission.rate_per_side`를 0.0009 → 0.0025 (사용자 실계좌 기준), `entry.rr_ratio`를 2.0 → 3.0으로 동시 갱신.

### 문제

0.25% 왕복 수수료 환경에서 R:R 1:2의 1R win net이 commission 차감 후 거의 사라짐. 60일 백테스트에서 trend 모드 PF 2.64 / 수익률 6.25% — 마지노선.

### 수학

- 1R win net = 2R - round-trip commission
- 평균 trade에서 1R ≈ $17, comm ≈ $30 → 1:2에서 1 win net = +$4 (commission이 win의 88% 잠식)
- 1:3에선 1 win net = +$21 (5배 cushion)

### 검증 (60일, $500 시작, comm 0.25%/0.25%)

| | trend 1:2 | trend 1:3 | dual 1:2 | dual 1:3 |
|---|---:|---:|---:|---:|
| 거래 수 | 24 | 24 | 44 | 44 |
| 승률 | 45.83% | 25.00% | 38.64% | 20.45% |
| PF | 2.64 | **3.19** | 1.58 | 1.80 |
| 순손익 | $31.26 | **$41.91** | $32.95 | $46.31 |
| MDD | -1.57% | -2.18% | -4.18% | -5.18% |

### 1:3 효과

- 승률은 절반으로 떨어지지만 (TP가 더 멀어짐), BE 분류가 4건 → 11건으로 흡수 — 작은 손실/0손익으로 끝남
- 1 win이 cover 가능한 loss 수: 0.08 → 0.45 (5배)
- PF·MDD 비율은 거의 동일 (-1.57/6.25=0.25 vs -2.18/8.38=0.26)
- **dual 모드는 1:3에서도 marginal** — 추가 거래 PF 1.11. dual 도입 보류 유지.

### BE move 자동 영향

`Position.breakeven_price = entry × (1+r)/(1-r)`. r=0.0009 → r=0.0025로 갱신 → BE target이 entry × 1.00501로 상승 (이전 1.00180). 11:00 BE move 후 더 높은 곳에서 stop 발동 — 실 commission을 제대로 cover. r과 실수수료 mismatch 시 BE 거래가 마이너스로 흘렀던 잠재 버그 동시 수정.

### 재현

```bash
BT_BUY_RATE=0.0025 BT_SELL_RATE=0.0025 BT_RR_RATIO=3.0 \
    python scripts/backtest_compare_dual_scan.py
```

## 설정 파일

| 경로 | 용도 |
|------|------|
| `.env` | 시크릿 + 모드 (gitignored) |
| `config/token.json` | KIS OAuth 토큰 캐시 (자동 갱신) |
| `data/position_state.json` | 진행 중 포지션 상태 (크래시 복구용) |
| `data/trades/trades_YYYY.json` | 연도별 누적 거래 기록 |
| `data/casper.pid` | daemon 모드 PID 파일 |

## 변경 이력

상세는 [CHANGELOG.md](CHANGELOG.md).
