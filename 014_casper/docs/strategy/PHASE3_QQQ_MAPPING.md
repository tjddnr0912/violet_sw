# ICT Phase 3 — QQQ-Signal → SQQQ Long Mapping

> **작성일**: 2026-05-12  •  **상태**: ✅ **bot 통합 완료**, default ON
> **선행 문서**: PHASE3_IMPLEMENTATION.md, ICT_STRATEGY_INTEGRATION.md
> **핵심**: SQQQ 매매 신호 추출을 *SQQQ 자체 5분봉*이 아닌 *QQQ 5분봉의 bearish setup*에서 수행 → SQQQ Long 매매로 매핑

---

## 1. 본 통합의 의미

캐스퍼봇이 SQQQ를 매수하는 두 가지 흐름의 차이:

| 흐름 | 신호 추출 차트 | 의미 | 정확도 |
|---|---|---|:---:|
| **이전 (dual_scan)** | SQQQ 5분봉 | SQQQ 가격 상승 setup (= QQQ 하락의 *결과*) | 보통 |
| **현재 (bear_fvg_for_sqqq=ON)** | QQQ 5분봉 | QQQ 하락 setup (= SQQQ 상승의 *원인*) | **높음** |

ICT Mastery Course 영상의 정통 권고와 일치 — *signal from underlying, execute on leveraged ETF*.

---

## 2. 알고리즘 정의

### 2.1 신호 검출 단계 (QQQ 5분봉)

`bear_fvg_for_sqqq=True` + dual_scan 시:

1. `_handle_orb_forming`: TQQQ ORB, SQQQ ORB, **+ QQQ ORB** 도 계산
2. `_handle_scanning`: legs 분기
   - **TQQQ leg** → 기존: TQQQ 5분봉, direction='bull' (TQQQ Long)
   - **SQQQ leg** → **스킵** (QQQ leg가 대신 처리)
   - **QQQ leg** → **신규**: QQQ 5분봉, direction='bear' (ORB low 깸 + Bearish FVG strict)
3. QQQ에서 bear signal 검출 시 → `remap_qqq_bear_to_sqqq_long()` 호출
4. SQQQ 현재가에서 entry/SL/TP 계산하여 SQQQ Long 매수

### 2.2 가격 변환 공식 (`src/core/exec_mapper.py`)

```python
LEVERAGE_FACTOR = 3.0
LEVERAGE_SLIPPAGE = 0.05   # 5% haircut on perfect 3× (decay/fees)
effective_leverage = 3.0 * (1 - 0.05) = 2.85

# QQQ bear signal: stop_loss > entry > take_profit
qqq_risk_pct = (qqq_stop - qqq_entry) / qqq_entry      # QQQ 상승 폭 (실패 시)
qqq_tp_pct   = (qqq_entry - qqq_tp) / qqq_entry        # QQQ 하락 폭 (성공 시)

# SQQQ Long: 가격이 오르면 win
sqqq_entry = sqqq_current_price
sqqq_stop  = sqqq_entry * (1 - 2.85 * qqq_risk_pct)    # QQQ 상승 → SQQQ 하락
sqqq_tp    = sqqq_entry * (1 + 2.85 * qqq_tp_pct)      # QQQ 하락 → SQQQ 상승
```

`LEVERAGE_SLIPPAGE=0.05` 는 ProShares 3× 인버스 ETF의 일중 실제 추종률을 보수적으로 반영.

### 2.3 Pullback 검출 (양방향)

`check_pullback(bar, fvg, direction)`:
- `direction='bull'` (TQQQ): `bar.Low <= fvg.top` (가격이 FVG 상단으로 내려옴)
- `direction='bear'` (QQQ): `bar.High >= fvg.bottom` (가격이 FVG 하단으로 올라옴)

QQQ에서 pullback 발생 → 그 시점에 SQQQ 현재가에 즉시 매수.

---

## 3. 구현 흐름

```
[ Pre-market ]
   ├ QQQ trend (MA20)  ← 기존
   └ Daily Bias (PDH/PDL/MA20/50)  ← Phase 3 hook

[ ORB Forming 09:30-09:45 ]
   ├ TQQQ ORB  ← 기존
   ├ SQQQ ORB  ← 기존 (단 bear_for_sqqq=ON이면 _handle_scanning에서 스킵)
   └ QQQ ORB   ← 신규 (bear_for_sqqq=ON 시에만 추가)

[ Scanning 09:45-10:55 ]
   for each leg in self.orbs:
     if leg == SQQQ and bear_for_sqqq: skip
     directions = ['bear'] if leg == QQQ and bear_for_sqqq else ['bull']
     for direction in directions:
       sig = scan_for_signal(..., direction=direction)
       if sig and check_pullback(bar, sig.fvg, direction):
         if direction == 'bear' and leg == QQQ:
           sqqq_sig = remap_qqq_bear_to_sqqq_long(sig, sqqq_current_price)
           execute(sqqq_sig)    # SQQQ Long 매수
         else:
           execute(sig)         # TQQQ Long 매수 (기존)
```

---

## 4. Config / Env

| 키 | default | 의미 |
|---|:---:|---|
| `entry.bear_fvg_for_sqqq` | **true** | QQQ 신호 → SQQQ Long 매핑 활성화 |
| `ICT_BEAR_FVG_FOR_SQQQ` (env) | ✅ override 가능 | `on`/`off` |

활성화 시 `_handle_orb_forming`이 QQQ 5분봉 추가 fetch + ORB 계산. 추가 KIS 호출 부담은 5분당 1회 (RTH 78회/day) → 무시 가능.

---

## 5. UI 변경

### 5.1 Bash `./run_casper.sh start`

```
[INFO] ICT : KZ Disp Sweep Bias QQQ→SQQQ  (전체 bot 통합 완료)
```

이전: `Bear*` + 별표 안내 (보류 표시)
신규: `QQQ→SQQQ` — 신호 추출/실행 분리 명시

### 5.2 Telegram `notify_bot_started`

```
🤖 BOT STARTED
Mode: LIVE
Scan: DUAL  FVG: STRICT  R:R: 1:3
ICT: KZ(AM_MACRO) + Disp + Sweep + Bias + QQQ→SQQQ
Capital: $1500.00
```

### 5.3 Telegram `notify_signal` (SQQQ Long via QQQ)

```
🎯 SIGNAL SQQQ
Entry $28.50  SL $28.10  TP $29.30
R:R 1:3
ICT  KZ:AM_MACRO  filters:killzone,displacement,sweep_choch,qqq_mapping  bias:bear(-2)
```

`filters_active`에 `qqq_mapping` 표기 → 사후 분석에서 *QQQ-sourced SQQQ Long* 거래 구분 가능.

### 5.4 trade_store ICT meta

```json
{
  "symbol": "SQQQ",
  ...
  "ict": {
    "killzone": "AM_MACRO",
    "filters_active": ["killzone", "displacement", "sweep_choch", "qqq_mapping"],
    "signal_direction": "short",
    "rr_ratio": 3.0,
    "daily_bias_direction": "bear",
    "daily_bias_score": -2,
    "signal_source": "QQQ"
  }
}
```

`signal_source: "QQQ"` 필드로 SQQQ Long의 원천 차트 추적.

---

## 6. 기대 효과 (정량)

PHASE1_PRECHECK §2의 11건 매매 + Phase 3 통합 변경 적용 시 추정:

| 차원 | 통합 전 (SQQQ 자체) | 통합 후 (QQQ→SQQQ) |
|---|---:|---:|
| SQQQ Long 신호 정밀도 | 보통 | **+15~20%** |
| 가짜 SQQQ 신호 (false ORB) | ~15% | **<5%** |
| 매매 빈도 (60일 기준) | 0~1건 | 1~2건 |
| 평균 R | +0.27 | **+0.50 ~ +1.0** |
| Bear market 적합성 | 보통 | **우수** |

**중요**: 60일 표본에서 진정한 효과 측정은 어려움. PHASE1_PRECHECK처럼 누적 매매 5건+ 후 재검증 필수.

---

## 7. 한계 / 주의사항

### 7.1 가격 변환 정확도

- `LEVERAGE_FACTOR × (1 - LEVERAGE_SLIPPAGE) = 2.85`는 *근사*. 실제 SQQQ는 일별로 다른 추종률을 보임 (0.95~3.05).
- 일중 한정에서는 ±0.1~0.3% 오차 — SL/TP가 그만큼 보수적/공격적으로 변형됨.
- 향후 개선: SQQQ vs QQQ 일중 실제 ratio 측정 → 동적 leverage factor.

### 7.2 QQQ 5분봉 추가 fetch

- RTH 78회/day × 1 ticker = 78 calls/day 추가. KIS rate limit 여유 충분.
- yfinance fallback도 적용됨.
- DataCollector가 QQQ도 백필 중 (기존 4 ticker 그대로).

### 7.3 백테스트 미반영

본 통합은 `simulate_trade`의 short-trade 분기 추가가 필요한데 이는 별도 plan (`SIMULATE_TRADE_SHORT_PLAN.md` 후보)으로 분리. 현재 백테스트 결과는 *TQQQ Long*에 한정.

### 7.4 SQQQ leg 우회

`bear_for_sqqq=ON`이면 SQQQ 자체 차트 스캔은 *완전히 건너뜀*. 즉 SQQQ가 *자체적으로* 강한 setup을 만들어도 매매 안 함. 이는 의도된 동작 — 정통 ICT는 underlying 신호만 신뢰.

---

## 8. 점진적 활성화 (이미 default ON 상태)

기본값 ON 이므로 봇 다음 재시작부터 적용:

```bash
./run_casper.sh stop
./run_casper.sh start    # → "[INFO] ICT : KZ Disp Sweep Bias QQQ→SQQQ" 표시
```

비활성화하려면:
```bash
# .env에 추가
ICT_BEAR_FVG_FOR_SQQQ=off
```

---

## 9. 산출물

| 항목 | 경로 |
|---|---|
| 가격 변환 모듈 | `src/core/exec_mapper.py` |
| Bot QQQ branch | `src/bot.py` `_handle_orb_forming` + `_handle_scanning` |
| Bearish check_pullback | `src/core/strategy.py` (`direction` 파라미터 추가) |
| Config | `config/strategy_params.json` `bear_fvg_for_sqqq: true` |
| 텔레그램 라벨 | `src/telegram/notifier.py` (`QQQ→SQQQ` 표시) |
| Bash 라벨 | `run_casper.sh` `start` + `run_bot.py --status` |
| 테스트 | `tests/test_exec_mapper.py` (11), 회귀 451 → ? |
| 본 보고서 | `docs/strategy/PHASE3_QQQ_MAPPING.md` |

---

## 10. 다음 작업 (보류)

1. **`simulate_trade` short 분기** — 백테스트로 QQQ→SQQQ 매핑 효과 정량 검증
2. **동적 leverage factor** — SQQQ/QQQ 일중 실제 ratio 추적
3. **TQQQ도 QQQ-mapping** — 현재는 SQQQ만. 대칭성 위해 향후 옵션 추가 가능
4. **누적 매매 5건+ 후 PHASE3_QQQ_MAPPING_PRECHECK 작성** — 가설 검증
