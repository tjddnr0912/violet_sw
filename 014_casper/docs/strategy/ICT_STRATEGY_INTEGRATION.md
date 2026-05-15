# Casper ICT 전략 통합 가이드 (Casper SMC ICT Mastery 기반)

> **목적**: 사용자가 정리한 "캐스퍼 ICT 매매법" 종합 자료 + Gemini로 깊이 분석한
> Casper SMC ICT Mastery Course 002 / 005 / 015 / Intra Day Strategy 영상 핵심을
> 기존 미장봇 코드(`src/`)에 통합 가능한 형태로 누적 정리한다.
>
> **작성일**: 2026-05-12  •  **베이스 문서**: `STRATEGY_REVIEW.md`(2026-03), `EXECUTION_PLAN.md`(2026-03), `INTRADAY_COMPARISON.md`(2026-05)
>
> **선행 조건**: 본 문서는 *코드 수정 방향성*을 정리한 설계 문서. 실제 코드 수정은
> 별도 PLAN 문서를 만들어 진행해야 한다(`DATA_COLLECTOR_PLAN.md` 패턴 참고).

---

## 0. 한 줄 요약

현재 미장봇은 ICT 매매법의 **첫 1/3만 구현**된 상태다.
ORB(15분 기준선) + Bullish FVG strict 까지는 ICT의 "External Liquidity Sweep + Displacement + FVG" 흐름의 부분 집합이지만,
**Liquidity 풀 정의, Displacement 검증, CHoCH 확인, OTE 진입, 양방향 매매, Killzone 시간 분리**가 모두 빠져있다.
이 문서는 그 갭을 채우는 4단계 통합 로드맵을 제시한다.

---

## 1. 신규 ICT 자료 핵심 추출 (Gemini 영상 deep-dive)

### 1.1 Liquidity (002 영상)

| 개념 | 정의 | 봇 구현 변수 |
|---|---|---|
| **BSL** (Buy-Side Liquidity) | 직전 고점들 위쪽, 공매도 stop loss 집중 구간 | `bsl_levels: List[float]` |
| **SSL** (Sell-Side Liquidity) | 직전 저점들 아래쪽, 매수 stop loss 집중 구간 | `ssl_levels: List[float]` |
| **ERL** (External Range Liquidity) | 현재 dealing range의 최외곽 swing high/low | `erl_high`, `erl_low` |
| **IRL** (Internal Range Liquidity) | dealing range 내부의 FVG | `irl_fvgs: List[FVG]` |
| **흐름 규칙** | 가격은 **ERL을 sweep 후 IRL(FVG)로 회귀**한다 | bias 결정 핵심 |

**유동성 풀 식별 규칙 (코드 직역)**

```
1. Swing Points (fractal): left=3, right=3 으로 swing high/low 추출
2. Equal Highs/Lows: 두 swing 가격 차이 < 0.05% → EQH/EQL (강력 풀)
3. Session Levels:
   - Asia    : 18:00 ~ 00:00 ET high/low
   - London  : 00:00 ~ 06:00 ET high/low
   - Premkt  : 06:00 ~ 09:30 ET high/low
4. Prior Day High/Low (PDH/PDL)  : 전일 RTH 09:30~16:00 ET high/low
```

**Liquidity Sweep 감지 (AND 조건)**

| 조건 | 임계값 |
|---|---|
| Wick rule | bar.high(또는 low)가 유동성 레벨 밖으로 ≥ 0.05% 이탈 |
| Close rule | 종가는 다시 유동성 레벨 **안쪽**에서 마감 |
| Pin bar | 꼬리 길이 / 전체 캔들 ≥ 60% |
| Body ratio | `\|close-open\| / (high-low) < 0.40` |

→ 단순 종가 돌파(BOS)와 명확히 구분되는 알고리즘.

### 1.2 Displacement (005 영상)

| 조건 | 임계값 (Python pandas 즉시 변환 가능) |
|---|---|
| Body size | `abs(close-open) > 1.0 * ATR(14)` (엄격 모드 1.5×) |
| Range vs 직전 | `range > 2.0 * prev_range_mean(N=5)` |
| Wick ratio | `wick_len / (high-low) < 0.50` |
| Volume spike | `volume > 1.5 * SMA(volume, 20)` (옵션) |
| Body close | 종가가 캔들 high/low의 10% 이내 마감 |
| Follow-through | 같은 방향 캔들 2~3개 연속 (뉴스 스파이크 거름) |

**핵심**: **유효 FVG는 반드시 Displacement에 의해 생성된 것만 인정**.
displacement 없이 생긴 FVG는 단순 갭 → 무효.

**CHoCH (Change of Character) 정밀 정의**:
- Strong Swing High/Low = 좌우 각 2개씩 총 5개 캔들(2-1-2)의 극값
- 종가 기준 swing point 돌파 (꼬리만 스치는 건 X)

### 1.3 Daily Bias (015 영상)

```
PDH sweep → bearish bias 가능성 ↑
PDL sweep → bullish bias 가능성 ↑

Midnight Open (00:00 ET) = True Open
  - 가격이 midnight open 위  → Premium 영역 (매도 우위)
  - 가격이 midnight open 아래 → Discount 영역 (매수 우위)

08:30 ET (지표 발표 직전) = 두 번째 기준선

Judas Swing:
  - 자정 후 하방 sweep → 상승 = Bullish
  - 자정 후 상방 sweep → 하락 = Bearish
```

### 1.4 Intra Day Strategy (007 영상) — "First Candle Rule"

```
1. 09:30~09:35 첫 5분봉의 High/Low 마킹
2. 5분봉 body가 그 범위 밖으로 종가 마감 → 돌파 확정
3. 돌파 level로 retest 발생 시 진입
4. SL = 첫 5분봉의 중간값 (50% midpoint)
5. TP = 고정 R:R 2:1 또는 3:1
6. Window: 09:30 ~ 10:30 ET
```

이게 캐스퍼 영상의 단순화 버전. 사용자가 가진 차트고릴라 자료의 **9:30 15분봉**과 일맥상통하지만,
원본 ICT는 **5분봉 첫 캔들 + 30분 윈도우**로 더 빠른 진입을 권장한다.

### 1.5 Power of 3 (AMD) — 별도 모델

```
Accumulation (축적/박스권) → 아시아 세션 18:00 ~ 00:00 ET
   ↓ 박스권 high/low 기록
Manipulation (조작/Judas Swing) → 런던 또는 NY 오픈 직후
   ↓ 박스권 반대 방향으로 sweep
Distribution (분배/추세) → CHoCH + Displacement 발생
   ↓ 진짜 방향으로 강한 추세
```

→ 미장봇이 NY RTH만 운용 중이라 **아시아 박스권은 기록만 가능 (KIS 미국주식 시간 외 시세 제약)**. 5.2절에서 상세.

---

## 2. 현재 미장봇 vs ICT 매칭 갭

### 2.1 매칭표 (코드 위치 + 갭 분석)

| ICT 개념 | 캐스퍼 현재 구현 | 위치 | 상태 |
|---|---|---|---|
| 15분 ORB | ✅ `calculate_orb()` 9:30~9:44 | `src/core/orb.py:28` | 일치 |
| 5분봉 전환 | ✅ scan_window 09:45~10:55 | `src/bot.py:563` | 일치 |
| Bullish FVG | ✅ `detect_bullish_fvg()` | `src/core/fvg.py:29` | 일치 |
| Strict FVG (ORB 라인 가로지름) | ✅ `strict=True` 옵션 | `src/core/fvg.py:78` | 일치 |
| Pullback Entry | ✅ FVG 중간점 limit | `src/core/strategy.py:71` | 일치 |
| Fixed R:R | ✅ `rr_ratio=3.0` | `config/strategy_params.json:15` | 일치 |
| BE shift 11:00 | ✅ `move_stop_to_breakeven()` | `src/core/position.py` | 일치 (영상엔 없음) |
| Daily Bias (Trend filter) | △ QQQ 20MA 만 | `src/core/risk.py:74` | **부분만, ICT 기준 미흡** |
| **Liquidity Pools** (BSL/SSL/ERL/IRL) | ❌ 없음 | — | **누락** |
| **Liquidity Sweep** (wick+close+pin bar) | ❌ 없음 | — | **누락** |
| **Displacement** (ATR/wick/volume) | ❌ 없음. ORB 돌파 종가 양봉만 확인 | — | **누락** |
| **CHoCH** (2-1-2 swing point) | ❌ 없음 | — | **누락** |
| **OTE** (피보 0.705) | ❌ FVG 중간점 fix | — | **누락** |
| **Breaker Block / OB** | ❌ 없음 | — | **누락** |
| Bearish FVG (Short 진입) | ✅ QQQ→SQQQ Long 매핑 (PHASE3_QQQ_MAPPING) | `src/core/exec_mapper.py` | **2026-05-12 통합 완료** |
| Killzone 시간 분리 | △ 9:45~10:55만 사용 | `bot.py:567` | **단일 윈도우** |
| Multi-timeframe 확인 | ❌ 5분봉만 | — | **누락** |
| Midnight Open / PDH/PDL | ❌ 없음 | — | **누락** |

→ 캐스퍼는 **ICT 매매법의 첫 1/3** 만 구현. 핵심 누락은 **Liquidity / Displacement / CHoCH** 3축.

### 2.2 갭 우선순위 (구현 ROI 기준)

| 갭 | 구현 난이도 | 효과 (백테스트 영향) | 우선순위 |
|---|---|---|---|
| **Displacement 필터** (ATR/wick) | 낮음 (50줄) | ★★★ 가짜 FVG 80% 제거 | **P0** |
| PDH/PDL/PWH/PWL 레벨 추적 | 낮음 (40줄) | ★★ 진입 컨플루언스 확장 | **P0** |
| Liquidity Sweep 감지 | 중간 (120줄) | ★★★ 진입 정확도 ↑, fade 감지 | **P1** |
| CHoCH 감지 (2-1-2 swing) | 중간 (80줄) | ★★ Trend reversal 진입 | **P1** |
| Killzone 시간 분리 | 낮음 (30줄) | ★★ 노이즈 거름 | **P1** |
| OTE 진입 옵션 (피보 0.705) | 중간 (60줄) | ★ FVG 중간점 대안 | **P2** |
| Daily Bias 정밀화 | 중간 (100줄) | ★★ 양방향 매매 결정 | **P2** |
| Breaker Block | 높음 (150줄) | ★ Unicorn pattern | **P3** |
| Multi-TF 확인 (1분봉) | 높음 (200줄) | ★★ 진입 정밀도 | **P3** |

---

## 3. KIS API 데이터 가용성 점검

### 3.1 지원되는 데이터 (현재 + 즉시 사용 가능)

| 데이터 | KIS 지원 | 현재 사용? | 비고 |
|---|---|---|---|
| TQQQ/SQQQ/QQQ 5분봉 (RTH) | ✅ `HHDFS76950200` | ✅ | `kis_client.py:286` |
| 미국주식 1분봉 | ✅ `nmin=1, NREC=120` (최대 120개) | ❌ | 동일 endpoint, 파라미터만 |
| 미국주식 일봉 | ✅ `HHDFS76240000` | ✅ | 추세 필터용 |
| 미국주식 호가 (현재가) | ✅ `HHDFS00000300` | ✅ | 시세 조회 |
| Pre-market 시세 | △ EXCD=NASD 본장만 | ❌ | 시간외는 제한적 |

### 3.2 KIS 미지원 → 우회 필요

| 데이터 | KIS 가능 | 우회 소스 | 캐스퍼 영향 |
|---|---|---|---|
| **DXY (달러 인덱스)** | ❌ | yfinance `DX-Y.NYB` 또는 `^DXY` | 외환 안 쓰면 불필요 |
| **^VIX 분봉** | ❌ | yfinance `^VIX` 5m 60d | 일봉은 KIS 가능, 분봉만 yfinance |
| **NQ/ES futures 분봉** | △ 해외선물 계좌 필요 (`product_code 08`) | yfinance `NQ=F`, `ES=F` (15m 이상) | **ICT 신호용** |
| **아시아 세션 (18:00~00:00 ET) 시세** | ❌ | yfinance NQ futures 24h | Power of 3 모델 핵심 |
| **PDH/PDL** | ✅ (일봉 high/low 직접 계산) | — | 즉시 사용 가능 |
| **선물 호가** | ❌ | polygon.io ($79/월) | 옵션 |

### 3.3 권장 데이터 소스 매트릭스

```
1순위 RTH 분봉      : KIS API (현재 그대로)
2순위 시간외/지수    : yfinance (NQ=F, ES=F, ^VIX, ^DXY) + 캐싱
3순위 휴면 종목 백필 : yfinance 60d ← (이미 DataCollector로 구축됨)
```

→ **현재 캐스퍼는 1+3은 갖춤. 2번 (NQ futures + ^DXY)은 신규 추가 필요**.

---

## 4. 종목 선정 분석 — TQQQ/SQQQ 유지 vs 변경

### 4.1 ICT 영상 권장 vs 현재 운용

| 차원 | ICT/Casper SMC 권장 | 미장봇 현재 |
|---|---|---|
| Primary 자산 | NQ / ES futures, EUR/USD, BTC | **TQQQ / SQQQ** |
| 데이터/신호 추출 | NQ 차트 (24h, 정확) | TQQQ/SQQQ 5분봉 (RTH만) |
| 매매 실행 | 동일 자산 (futures) | TQQQ Long / SQQQ Long (인버스 우회) |
| 양방향 매매 | Long + Short 양쪽 | Long Only (SQQQ로 우회) |

### 4.2 평가

**TQQQ/SQQQ 유지의 정당화 (강함)**:
1. **KIS API에서 즉시 가능, 한국 계좌로 PDT 규칙 비적용** → 운용 인프라 그대로
2. **소형 자본($1,500)으로 충분히 매매 가능** — 단가 $40 수준, futures는 마진 ~$15,000+
3. **거래량 1억주+** — slippage 극소
4. **NQ 신호와 0.998 상관관계** — TQQQ는 3×QQQ의 인트라데이 추종 거의 정확

**개선 필요 (ICT 권장에 따라)**:
1. **신호 추출은 QQQ 차트, 실행만 TQQQ/SQQQ** → 레버리지 decay/wick 왜곡 회피
   - 현재 캐스퍼는 TQQQ/SQQQ 각자 ORB 계산 — 위양성 가능
   - 권장: QQQ 5분봉으로 ORB + 유동성 풀 계산 → 신호 발생 시 TQQQ(상승)/SQQQ(하락) 매수
2. **양방향**: 현재 dual_scan은 TQQQ/SQQQ 둘 다 Long 시도 — Bullish FVG만 사용해서 SQQQ는 실은 "QQQ 하락 → SQQQ 상승" 흐름 한정. Bearish FVG도 추가하면 SQQQ Long의 정밀도 ↑

### 4.3 추가 종목 검토

| 종목 | 추가 가치 | 추가 비용 |
|---|---|---|
| **QQQ** (신호 추출용) | ★★★ ICT 정통 흐름 | $0 (KIS 지원, 이미 수집 중) |
| **SPY/SPXL/SPXS** (S&P 500) | ★★ 분산, but 캐스퍼 1 trade/day 룰과 중복 | $0 |
| **NQ futures** | ★★★ 24h 데이터, ICT 정통 | 해외선물 계좌 + 마진 | 
| **BTC/ETH** | ★ 24/7 시장, 캐스퍼 시간 윈도우와 어긋남 | 별도 거래소 |
| **EUR/USD** | ★ ICT 정통 자산 | KIS 외환 미지원 |

**권고**:
- **QQQ는 즉시 추가** (신호 추출 정확도 ↑, 비용 0)
- **NQ futures는 보류** (해외선물 계좌·마진 부담, ROI 검증 필요)
- **SPY/SPXL은 옵션** (1 trade/day 정책 vs 종목 1개 매매 결정)
- **BTC/ETH는 별도 봇** (시간대 다름, 005_money에 이미 봇 있음)

---

## 5. 통합 로드맵 (4단계, 각 단계는 별도 PLAN 문서로 분해)

### Phase 1 (P0, 1~2주): Displacement + PDH/PDL 컨플루언스

**목표**: 현재 ORB+FVG strict 신호의 **품질** 검증 강화.

```
신규 모듈:
  src/core/displacement.py        : Displacement 캔들 감지
  src/core/levels.py              : PDH/PDL/PWH/PWL 추적

변경 모듈:
  src/core/fvg.py                 : displacement 필수화 옵션
  src/core/strategy.py            : FVG가 displacement에 의해 생성됐는지 검증
  config/strategy_params.json     : displacement.atr_multiplier=1.0,
                                    displacement.max_wick_ratio=0.50,
                                    require_displacement=true (default)
```

**산출물**: Displacement 미충족 FVG를 60일 백테스트에서 모두 reject했을 때
승률 변화 측정. 가짜 신호 80% 제거 가정 시 표본은 줄지만 **Profit Factor 상승** 기대.

### Phase 2 (P1, 2~3주): Liquidity Sweep + Killzone 시간 필터

**목표**: 진입 *타이밍* 정밀화.

```
신규 모듈:
  src/core/liquidity.py           : BSL/SSL/ERL/IRL 풀 식별 + sweep 감지
  src/core/sessions.py            : Killzone (AM Macro 09:30-10:10, etc.) 분리
  src/core/swing.py               : 2-1-2 fractal swing high/low + CHoCH

변경 모듈:
  src/bot.py                      : scan window 09:45~10:55 → killzone 분리
  src/core/strategy.py            : sweep + CHoCH + FVG combo 트리거
```

**산출물**: Killzone 별 승률 측정 (AM macro vs lunch vs PM).

### Phase 3 (P2, 3~4주): QQQ 신호 + 양방향 + Daily Bias 정밀화

**목표**: 종목 신호/실행 분리, Bearish FVG 활성화.

```
변경:
  config/strategy_params.json     : symbols.signal_source="QQQ"
                                    symbols.exec_bull="TQQQ"
                                    symbols.exec_bear="SQQQ"
  src/core/strategy.py            : Bearish FVG 추가 (현재는 bullish만)
  src/core/bias.py (신규)         : midnight open + PDH/PDL sweep 기반 daily bias
```

**산출물**: ICT 정통 흐름 (QQQ 신호 → TQQQ/SQQQ 실행) 적용.

### Phase 4 (P3, 4~6주): OTE / Breaker Block / Multi-TF (선택)

```
신규:
  src/core/ote.py                 : 피보나치 0.618 / 0.705 / 0.79 계산
  src/core/breaker_block.py       : OB → Breaker Block 변환
  src/core/multi_tf.py            : 1분봉 진입 정밀화
  src/data/futures.py             : yfinance NQ=F 시간외 데이터
```

이 phase는 ROI 검증 후 결정.

---

## 6. 코드 수정 방향성 (구체적 가이드)

### 6.1 의존성 원칙

기존 미장봇 안정성을 잃지 않기 위해:

1. **신규 모듈은 모두 옵션** — `config/strategy_params.json`에 명시적 토글
2. **기존 `strat_casper` 동작은 보존** — phase 1에서 default OFF 유지, A/B 비교 후 ON
3. **DataCollector는 신호 캐싱 인프라로 활용** — Phase 2의 Liquidity 풀은
   `data/marketdata/` parquet 기반으로 PDH/PDL 추적 (re-fetch 불필요)
4. **검증 우선**: 새 모듈마다 unit test + 60일 백테스트로 기존 대비 PF/MDD 변화 측정

### 6.2 신규 환경변수 (제안)

```bash
ICT_DISPLACEMENT_REQUIRED=on        # phase 1
ICT_USE_LIQUIDITY_SWEEP=off         # phase 2, default off
ICT_KILLZONE_FILTER=on              # phase 2
ICT_SIGNAL_SOURCE=QQQ               # phase 3, "QQQ" or "TQQQ"
ICT_USE_OTE=off                     # phase 4
```

### 6.3 백테스트 통합

`scripts/intraday_backtest_compare.py` (이미 존재)에 다음 전략 추가:

```
15_ICT_Displacement     : Casper + displacement filter
16_ICT_Sweep_FVG        : Liquidity sweep → CHoCH → FVG
17_ICT_OTE              : OTE 0.705 entry vs FVG 중간점
18_ICT_QQQ_Signal       : QQQ 신호 → TQQQ/SQQQ 실행
```

각 전략은 KIS 정밀 비용 모델(`brokerage 0.25% + slippage 차등`)을 동일하게 적용.

---

## 7. 필요한 추가 데이터 / 소스 매트릭스

| 데이터 | 필요 시점 | 소스 | 캐시 위치 |
|---|---|---|---|
| QQQ 5분봉 | Phase 1+ | KIS (이미 수집) | `data/marketdata/QQQ/` |
| PDH/PDL/PWH/PWL | Phase 1+ | KIS 일봉에서 계산 | 계산 시 메모리 |
| Displacement ATR(14) | Phase 1+ | 5분봉에서 자체 계산 | 계산 시 메모리 |
| Swing fractal points | Phase 2+ | 5분봉에서 자체 계산 | 메모리 + parquet 옵션 |
| ^VIX 5분봉 | Phase 2 (volatility filter) | yfinance | `data/marketdata/_VIX/` (이미 수집) |
| NQ futures 24h | Phase 3+ (Power of 3) | **yfinance `NQ=F`** | 신규 `data/marketdata/NQ_F/` |
| Midnight Open | Phase 3+ | NQ futures 24h | 메모리 |
| DXY | (옵션, 외환 안 함) | yfinance `^DXY` | 신규 (필요 시) |

→ **즉시 활성화 시 필요한 신규 외부 데이터는 0**. Phase 3+에서만 NQ futures 추가 필요.

---

## 8. 우려 사항 / 리스크

### 8.1 ICT 자체의 학술적 취약성

ICT 매매법은 **체계적 학술 검증이 거의 없음**. STRATEGY_REVIEW.md §2.2 에 명시.
Edgeful 같은 commercial backtest 회사 결과만 존재. **각 phase 도입 시 자체 백테스트로 검증 필수**.

### 8.2 추가 복잡도가 가져오는 over-fitting

신규 ICT 필터를 모두 켜면 60일 표본에서 신호가 **0~3건**으로 줄 가능성. INTRADAY_COMPARISON 보고서에서 본 그대로의 함정. 따라서:

- **최소 1년 데이터 (또는 매일 데이터 누적 후) 검증**
- 새 필터마다 PF·MDD·Sharpe 동시 보고
- 표면 PF 99.99(분모 0)는 무시

### 8.3 KIS 비용 모델은 그대로

INTRADAY_COMPARISON.md에서 확인된 결과: round-trip ~0.6% 비용 압박은 ICT 도입 후에도 동일.
**Holy Grail 함정(36회 매매 → -5% 비용 잠식)을 ICT 다회 신호로 반복하면 안 됨**.
ICT는 본래 "하루 1~2건의 고품질 셋업"을 추구하므로 캐스퍼 철학과 일치.

### 8.4 봇 안정성

각 phase의 모듈 추가는 try/except로 격리. ICT 검증 실패 → fallback to 기존 ORB+FVG strict.
DataCollector와 동일한 default-OFF + env toggle 패턴 사용.

---

## 9. 즉시 가능한 검증 작업 (코드 변경 없이)

1. **Displacement 가설 검증** (Phase 1 사전 확인):
   - 백테스트에서 ORB+FVG 신호 시점에 displacement(ATR 1×, wick<50%) 동시 만족 여부 측정
   - 결과: displacement 만족하는 신호의 승률이 전체 승률보다 명확히 높으면 Phase 1 GO

2. **PDH/PDL 컨플루언스 측정** (Phase 1 사전):
   - 캐스퍼의 기존 23회 매매에서 진입가 vs PDH/PDL 거리 분포
   - 5% 이내인 매매의 승률이 전체보다 높으면 컨플루언스 가치 입증

3. **Killzone 분류** (Phase 2 사전):
   - 기존 23회 매매를 AM Macro(9:30-10:10), 외(10:10-10:55)로 분리
   - AM Macro 매매의 PF가 우월하면 Killzone 분리 가치 입증

이 3개 검증은 **이미 수집된 60일 + 41일 백필 데이터로 즉시 가능**.
다음 세션에서 사용자 요청 시 진행 가능.

---

## 10. 결론 / 즉시 결정 사항

### 사용자 결정 필요

1. **Phase 1 GO/NO-GO**: Displacement filter + PDH/PDL 컨플루언스 사전 검증부터 시작할지?
2. **QQQ 신호 분리 (Phase 3)**: 우선순위를 Phase 1보다 앞당길지? (구현 난이도 낮음)
3. **NQ futures 도입**: 해외선물 계좌 추가 의향이 있는지? (없으면 Phase 4 일부 보류)
4. **종목 확장**: SPY/SPXL/SPXS 추가 매매 의향? (1 trade/day 정책과 충돌 검토)

### 권장 다음 단계

1. **즉시**: §9의 사전 검증 3개를 데이터로 확인 (코드 변경 0)
2. **사전 검증 통과 시**: `docs/strategy/ICT_PHASE1_PLAN.md` 작성 후 코드 수정
3. **Phase 1 백테스트 완료 시**: PF·MDD·trades_per_day 비교 후 production 적용 결정
4. **각 Phase는 별도 PR / 별도 봇 재시작**: DataCollector 도입 패턴 그대로 적용

---

## 11. 참고 영상 / 출처

### 사용자 정리본 (한국어)
- 차트고릴라: https://youtu.be/b_Vq_pfDYKs
- Casper SMC ICT Mastery 1~15편

### Gemini deep-dive 결과 (본 문서 §1)
- 002 Liquidity: https://youtu.be/9WBT-ZIUqaM
- 005 Displacement: https://youtu.be/rveJV02kx4U
- 015 Daily Bias: https://youtu.be/7kttuHxdKMQ
- 007 Intra Day Strategy: https://youtu.be/BfikWPaXh3k

### 학술 / 백테스트
- Toby Crabel — Day Trading with Short Term Price Patterns (1990)
- Linda Raschke — Street Smarts (1995, Holy Grail / 80-20)
- Edgeful — FVG 통계 (YM 30분, Bullish 69% / Bearish 68%)
- Concretum — ORB academic study (NDX 5m, Sharpe 2.81, 2024)
- KIS Developers Portal — https://apiportal.koreainvestment.com/intro

### 기존 캐스퍼 문서 (베이스)
- [STRATEGY_REVIEW.md](STRATEGY_REVIEW.md) — 2026-03 원본 전략 검토
- [EXECUTION_PLAN.md](EXECUTION_PLAN.md) — 2026-03 실행 계획
- [INTRADAY_COMPARISON.md](INTRADAY_COMPARISON.md) — 2026-05 KIS 비용 백테스트
- [DATA_COLLECTOR_PLAN.md](DATA_COLLECTOR_PLAN.md) — 2026-05 데이터 수집 인프라
