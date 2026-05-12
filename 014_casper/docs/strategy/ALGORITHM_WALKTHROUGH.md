# Casper 알고리즘 흐름 해설 — 차트로 따라가는 가이드

> **목적**: 캐스퍼봇이 *어떤 시점*에 *어떤 차트의 무엇*을 보고 매매를 결정하는지,
> 차트를 옆에 놓고 흐름을 따라갈 수 있게 추상적으로 설명한다.
> 코드 세부는 다른 문서 참조. 본 문서는 **운용자의 머릿속 동선**에 집중.
>
> **선행 지식**: ICT 매매법 기본 개념 (ORB / FVG / Liquidity).
> 없어도 §2의 용어 박스로 충분.

---

## 0. 한눈에 보기 — 일과 (KST 서머타임 기준, 5월~10월)

```
┌──────────────────────────────────────────────────────────────┐
│  22:00 KST  Pre-market  → 봇이 VIX / QQQ trend / Daily Bias  │
│  22:30 KST  미국장 개장 → ORB 형성 시작                       │
│  22:45 KST  ORB 완성    → TQQQ / SQQQ / QQQ 각 ORB 확정       │
│  22:45 KST  스캔 시작   → AM_MACRO Killzone 시작              │
│  23:10 KST  AM_MACRO 끝  → 이 시간 이후 진입 불가             │
│  ※(이론상 23:55까지 진입 가능했으나 ICT 풀 ON으로 23:10까지) │
│  00:00 KST  BE shift    → 미청산 포지션의 SL을 손익분기로     │
│  04:50 KST  강제 청산   → 모든 포지션 시장가 종료             │
└──────────────────────────────────────────────────────────────┘

겨울 (11월~3월, 표준시): 모든 시각을 +1시간 (개장 23:30 KST)
```

차트 보면서 위 시각에 다음 단원의 박스가 형성되는지 추적하면 됩니다.

---

## 1. 무엇을 보는 차트인가?

| 차트 | 용도 | 봇이 매매하는 종목 |
|---|---|---|
| **QQQ 5분봉** | ICT 신호 추출 (SQQQ Long 결정 시 사용) | 직접 매매 X |
| **QQQ 일봉** | Daily Bias 계산 (전일 high/low, MA20/50) | 직접 매매 X |
| **TQQQ 5분봉** | TQQQ Long 진입가/SL/TP 계산 | ✅ TQQQ 매수 |
| **SQQQ 5분봉** | SQQQ Long 진입 시점의 가격 캡처 (가격 변환의 base) | ✅ SQQQ 매수 |
| **^VIX 일봉** | VIX 필터 (12~30 범위 외 진입 차단) | — |

→ **신호는 QQQ(또는 TQQQ)에서 보고, 실행은 TQQQ/SQQQ에서**.

---

## 2. 핵심 용어 박스 (3분이면 OK)

### 2.1 ORB (Opening Range Breakout)
- 09:30~09:44 ET (KST 22:30~22:44) **첫 3개 5분봉의 high/low**
- 차트에 두 개의 수평선 (high, low). 이게 그날의 "유동성 기준선"
- 가격이 high 위로 종가 돌파 = bullish breakout, low 아래로 종가 돌파 = bearish breakdown

### 2.2 FVG (Fair Value Gap)
- **3개 연속 캔들**에서 1번 캔들 high와 3번 캔들 low 사이에 *겹치지 않는 빈 공간*
- Bullish FVG: c1.High < c3.Low (가격이 위로 점프)
- Bearish FVG: c1.Low > c3.High (가격이 아래로 점프)
- 차트에 직사각형(box)으로 표시. 가격이 *나중에 그 box로 되돌아오면* 진입 후보

### 2.3 Strict FVG (캐스퍼만의 추가 조건)
- 단순 FVG가 아니라 **ORB 라인을 가로지르는 FVG**만 인정
  - bullish: `FVG zone`이 ORB high를 포함
  - bearish: `FVG zone`이 ORB low를 포함
- 차트에서 보면 ORB 수평선이 FVG box를 *관통*해야 함

### 2.4 Killzone (AM_MACRO)
- 09:30~10:10 ET (KST 22:30~23:10)
- **이 시간대에 발생한 setup만 진입 허용**
- 차트에 세로 회색 띠로 표시하면 직관적

### 2.5 Displacement candle (변위 봉)
- FVG를 만든 *중간 캔들*이 다음 조건 충족:
  - 몸통 ≥ ATR(14) × 1.0
  - 꼬리 비율 < 50%
- 차트에서 보면 "굵고 시원한 양봉/음봉"

### 2.6 Liquidity Sweep
- 가격이 prior swing low(또는 high)를 wick으로 *살짝 깨고 다시 안으로 들어오는* pin bar
- "stop hunt" — 기관이 stop loss 물량 모으는 흔적

### 2.7 CHoCH (Change of Character)
- sweep 직후 *반대 방향*으로 강하게 진행하면서 prior swing을 종가로 깨는 봉
- 추세 전환의 첫 신호

### 2.8 Daily Bias
- QQQ 일봉으로 계산한 그날의 방향 추정
- PDH(전일고)/PDL(전일저)/PWH(주간고)/PWL(주간저) + MA20/50 점수 합산
- score > 0 → bull, < 0 → bear, == 0 → **neutral (그날 매매 X)**

---

## 3. 일과 흐름 (KST 기준, 봇이 보는 것 그대로)

### 3.1 ~22:00 KST — 대기 (WAITING)

- 봇은 잠자고 있음. 메인 루프는 60초마다 시간 확인.
- 차트 봐도 변화 X.

### 3.2 22:00~22:30 KST — Pre-market (PRE_MARKET)

```
[봇 행동]
1. VIX 일봉 종가 fetch → 12~30 범위?
2. QQQ 일봉 fetch (60일) → close, MA20, MA50, PDH/PDL/PWH/PWL
3. Daily Bias 계산:
   score = (close vs MA20) ± 1
        + (close vs MA50) ± 1
        + (close vs PDH/PDL) ± 1
        + (close vs PWH/PWL) ± 1

[결정 분기]
- VIX < 12 또는 > 30 → 그날 매매 안 함 (DONE_TODAY)
- score == 0 (neutral) → 그날 매매 안 함  ← ICT 신규
- 그 외 → ORB_FORMING 상태로 전환
```

**차트 추적**: QQQ 일봉에서 가장 최근 봉이 MA20 위/아래인지, 전일 high/low를 깼는지 본다. 어제 close가 PDH 위면 +1, PDL 아래면 −1. 머릿속으로 score 계산해보면 봇과 같은 결론에 도달.

### 3.3 22:30~22:45 KST — ORB 형성 (ORB_FORMING)

```
[봇 행동]
1. 09:30~09:44 ET (KST 22:30~22:44) 5분봉 3개 fetch — TQQQ + SQQQ + QQQ
2. 각 종목 ORB high/low 계산
3. ORB 너비 > 일평균 변동 × 1.5 → 그 leg 제외 (너무 wide)
4. 매매 윈도우(SCANNING) 상태로 전환
```

**차트 추적**: 22:30 첫 5분봉 → 22:35 두 번째 → 22:40 세 번째. 이 3개의 highest/lowest 두 점을 수평선으로 그어두면 그게 ORB. 그날 *모든* 봇 결정의 기준선.

### 3.4 22:45~23:10 KST — 신호 스캔 (SCANNING, AM_MACRO Killzone)

이게 *진짜 매매가 결정되는 시간*. 25분 윈도우.

```
[봇 행동, 매 5분봉마다]
A. TQQQ 5분봉 1봉 확정
   - TQQQ Close > TQQQ ORB high + bullish 봉인가? (bull setup)
   - 직전 봉(c1) / 현재 봉(c2) / 다음 봉(c3) 사이에 Bullish FVG 형성?
   - strict: FVG box가 TQQQ ORB high를 가로지름?
   - c2가 Displacement (body ≥ ATR, wick < 50%)?
   - sweep+CHoCH 시퀀스가 직전 6봉 안에 있었나?

B. QQQ 5분봉 1봉 확정 (SQQQ Long 신호 추출용)
   - QQQ Close < QQQ ORB low + bearish 봉인가? (bear setup)
   - Bearish FVG (c1.Low > c3.High) 형성?
   - strict: FVG box가 QQQ ORB low를 가로지름?
   - c2가 Displacement (bearish)?
   - sweep+CHoCH (반대 방향)?

C. 신호 발견 후 pullback 대기
   - TQQQ bull: 가격이 FVG top까지 *내려와야* 진입
   - QQQ bear:  가격이 FVG bottom까지 *올라와야* 진입

D. Pullback 발생 → 즉시 진입
   - TQQQ bull → TQQQ Long 매수
   - QQQ bear → 그 시점의 SQQQ 현재가에 매수
     · SL = SQQQ 현재가 × (1 − 2.85 × QQQ_risk%)
     · TP = SQQQ 현재가 × (1 + 2.85 × QQQ_TP%)
```

**차트 추적 (TQQQ Long 시나리오)**:
1. 22:45 이후 TQQQ 5분봉이 ORB high를 양봉으로 깬다 → 차트에 빨간 화살표
2. 직전·현재·다음 봉 사이에 위쪽으로 빈 공간(FVG box)이 생기고, 그 box를 ORB high 선이 *관통*
3. 다음 한두 봉이 *내려와* FVG box top을 터치
4. 그 순간 봇이 TQQQ 매수 — 차트에 매수 마크

**차트 추적 (SQQQ Long via QQQ 시나리오)**:
1. QQQ 차트로 시점 전환
2. QQQ 5분봉이 ORB low를 음봉으로 깬다 → 빨간 화살표
3. 아래쪽 FVG box 형성, ORB low 관통
4. 다음 한두 봉이 *올라와* FVG box bottom 터치
5. 그 순간 봇이 SQQQ 현재가에 매수 — *SQQQ 차트* 진입 마크
   (가격은 SQQQ 시장가, SL/TP는 QQQ % move를 2.85× 환산)

### 3.5 신호 못 잡으면 — 23:10 KST 이후

```
[봇 행동]
- AM_MACRO Killzone(09:30~10:10 ET) 종료
- 추가 신호 검출 차단
- DONE_TODAY 상태로 전환
- Telegram에 "No signal today" 알림
```

→ 그날 *매매 0건* 으로 끝남. ICT 풀 ON 상태에서 흔한 결과.

### 3.6 포지션 보유 중 — 진입 후 ~04:50 KST

```
[봇 행동, 매 5초~15초마다]
1. 현재가 fetch
2. TQQQ Long 기준:
   - 현재가 ≤ SL → 손절 (StopLoss hit)
   - 현재가 ≥ TP → 익절 (TakeProfit hit)
3. SQQQ Long 기준 (역방향이라 같은 가격 비교지만 의미는 mirror)

[시간 기반 행동]
- 24:00 KST (ET 11:00) 도달 시: SL을 손익분기가로 이동 (BE shift)
  · 이후엔 손해 보지 않고 끝남 (그 위로 가면 익절)
- 04:50 KST (ET 15:50) 도달 시: 시장가 강제 청산
  · 오버나잇 리스크 0
```

**차트 추적**: TQQQ Long 진입 후 가격이 TP 도달하면 ✅ win. SL 먼저 도달하면 ❌ loss. 24:00 이후엔 SL이 entry × 1.006 수준으로 올라옴 → 그 위에서만 손해 없이 끝낼 수 있음. 04:50까지 어느 쪽도 도달 안 하면 시장가 청산.

### 3.7 청산 후 — DONE_TODAY

- Telegram에 청산 알림 (`🟢 EXIT TQQQ ...`)
- `data/trades/trades_2026.json`에 매매 기록 + ICT 메타 추가
- 그날 추가 매매 X (1 trade/day)
- 다음날 22:00 KST까지 대기

---

## 4. 의사결정 트리 (차트 보면서 머릿속으로 따라하기)

```
┌─────────────────────────────────┐
│ 22:00 KST — Pre-market 시작    │
└─────────────────────────────────┘
              │
              ▼
       VIX 12~30?
       ├ No → SKIP today
       └ Yes ▼
       Daily Bias score ≠ 0?
       ├ No (neutral) → SKIP today
       └ Yes ▼
┌─────────────────────────────────┐
│ 22:30 — ORB 형성 (3개 봉)        │
└─────────────────────────────────┘
              │
              ▼
       ORB 너비 ≤ ATR×1.5?
       ├ No → leg 제외
       └ Yes ▼
┌─────────────────────────────────┐
│ 22:45 — Scan 시작 (Killzone ON) │
└─────────────────────────────────┘
              │
              ▼
       ┌─────────────────────────────────┐
       │ 매 5분봉:                       │
       │ A) TQQQ Bull setup?            │ ─yes─► Pullback 대기 ─► TQQQ Long
       │ B) QQQ Bear setup?             │ ─yes─► Pullback 대기 ─► SQQQ Long
       │ C) 23:10 도달?                  │ ─yes─► DONE_TODAY
       └─────────────────────────────────┘
              │ (진입 후)
              ▼
       SL hit? / TP hit? / 24:00 BE shift / 04:50 강제청산?
              │
              ▼
       청산 → DONE_TODAY
```

### A·B·C에서 *모두 No*인 봉을 본다면?

- 캐스퍼는 그 5분봉에서 매매 안 함. 다음 봉으로 넘어감.
- 차트로 보면 거의 모든 봉이 그렇게 보일 것. ICT 풀 ON에서 한 setup 발견에 보통 20~30분 소요.

---

## 5. 시각적 체크리스트 — 차트에 직접 그릴 것

차트 도구(TradingView 등)에서 다음을 그어두면 봇의 시야와 같아집니다:

| 그릴 것 | 색/형태 | 어디서 |
|---|---|---|
| **ORB high / low** 수평선 (TQQQ) | 파랑 점선 | 22:30~22:44 5분봉 3개의 max/min |
| **ORB high / low** 수평선 (QQQ) | 보라 점선 | 같은 시간, QQQ 차트 |
| **AM_MACRO Killzone** 세로 띠 | 회색 음영 | 22:30~23:10 KST |
| **PDH / PDL** 수평선 (QQQ) | 노랑 점선 | 전일 RTH 09:30~16:00 max/min |
| **VIX 12 / 30** 수평선 (^VIX 일봉) | 빨강 점선 | 항상 |
| **Bullish FVG** 박스 | 초록 반투명 | 3봉 detect 시 (TQQQ에) |
| **Bearish FVG** 박스 | 빨강 반투명 | 3봉 detect 시 (QQQ에) |

→ 위 7개만 그어놓으면 봇이 "보는 정보"의 90%는 시각화됨.

---

## 6. 실제 매매 사례 (이전 실거래 11건 중 가장 명확)

### 2026-04-07 — SQQQ Long WIN +1.78R

- **개장 직전**: VIX 정상, QQQ trend bull(아마 score ≠ 0)
- **22:30~22:44 KST**: SQQQ ORB 형성 (high $77.57, low $76.52, range $1.05)
- **22:55 KST**: SQQQ에 강한 양봉 — ORB high $77.57을 몸통으로 가로지르며 close $77.85 (당시 ICT 풀 OFF였으니 SQQQ 자체 차트 기반)
- **22:55~23:00 사이**: 3봉 윈도우에 Bullish FVG 형성 [$77.975, $78.13]
- **23:00 KST**: SQQQ가 FVG mid $78.05로 pullback → **매수 진입**
- **23:08 KST**: TP $79.24 도달 → 청산 ✅ +$8.39 (8주)

차트로 그려보면:
1. SQQQ 5분봉에서 22:30~22:44 ORB box
2. 22:55 봉이 ORB 상단 위로 큰 양봉 (= Displacement)
3. 같은 시간대 FVG box (초록)
4. 23:00 봉이 FVG box로 내려와서 매수
5. 23:08 봉이 TP 위로 → 익절

이게 SQQQ Long의 정통 setup이고, 신규 QQQ→SQQQ 매핑 후엔 동일 패턴을 QQQ에서 *역방향*으로 검출.

---

## 7. ICT 풀 ON에서 매매가 *안* 잡힐 때 흔한 패턴

```
Case 1: ORB 형성 후 곧장 추세 일변도 (24% of 60일)
  - TQQQ가 ORB high를 깨고 *뒤도 안 돌아보고* 상승
  - FVG는 있지만 pullback이 안 일어남 → 매매 0건

Case 2: 박스권 횡보 (37% of 60일)
  - ORB high/low 사이에서 깨작깨작
  - 어느 쪽으로도 strict breakout 안 일어남 → 매매 0건

Case 3: Killzone 후 setup (Late)
  - 23:10 이후 ORB 돌파 + FVG 발생
  - Killzone 필터로 차단 → 매매 0건
  - (이 케이스가 가장 아쉬움 — 23:10~24:00 사이 좋은 setup 종종 발생)

Case 4: Daily Bias neutral
  - QQQ 일봉 score == 0 — choppy market
  - Pre-market에서 그날 자체를 skip → 매매 0건
```

→ ICT 풀 ON에서 매매 발생률이 60일에 0건이었던 이유. *quality > quantity* 철학.

---

## 8. 운용자 행동 가이드 (차트를 직접 보면서)

### 매일 22:30 KST 직전
1. TradingView로 TQQQ / QQQ / SQQQ 5분봉 차트 열기
2. ^VIX 5분봉도 한쪽에
3. QQQ 일봉에서 PDH/PDL/MA20 위치 확인

### 22:30~23:10 KST
1. **봇 telegram 알림 대기** — 봇이 신호 발견 시 알림
2. 알림 없으면 차트 직접 보고 추적:
   - ORB box 그려졌나?
   - FVG box 그려졌나?
   - Pullback 발생했나?
3. 신호 발생인데 봇이 안 잡으면 → ICT 필터 어느 단계에서 잘렸는지 확인
   - `tail -f logs/casper.log` 로그에서 `Strategy:` 메시지 확인
   - "outside allowed killzones" / "fails displacement check" / "no sweep+CHoCH precursor" 등

### 진입 후
1. Telegram 알림 즉시 도착
2. 차트에 entry / SL / TP 마크
3. 24:00 KST 이후 BE shift 자동 (별도 알림)
4. 청산 알림 + 결과 (WIN/LOSS/BE)

### 23:10~04:50 사이 매매 없으면
- 그날은 그냥 *NO TRADE*. 캐스퍼는 강제로 매매 안 함.
- 차트로 그날 가격 추이를 보면서 "어떤 setup이 있었으면 좋았을지" 회고

---

## 9. ICT 풀 ON에서 매매 발생 가능성 추정 (일별)

| 시장 환경 | 60일 분포 | 매매 발생 추정 |
|---|---:|---:|
| TREND_UP (강한 상승) | 30% | TQQQ Long 1~2건/주 |
| TREND_DOWN (강한 하락) | 12% | SQQQ Long 1~2건/주 |
| RANGE (박스권) | 37% | 0건 (Daily Bias로 사전 차단) |
| MIXED (혼조) | 22% | 0건 (필터로 차단) |

월 매매 기대치: **4~8건**.

---

## 10. 빠른 진단 — 봇 매매 안 할 때

| 증상 | 가능한 원인 | 확인 방법 |
|---|---|---|
| 22:30 봇 안 깨어남 | VIX out of range | log: "RISK: VIX X.X < 12 (too low)" |
| ORB 안 그려짐 | KIS API 5분봉 fetch 실패 | log: "ORB: TQQQ unavailable" |
| 그날 자체 skip | Daily Bias neutral | log: "Daily Bias neutral (score=0)" |
| 23:10 직전 매매 안 함 | 신호는 있지만 필터에 막힘 | log: "Strategy: bar i fails displacement check" |
| 23:10 이후 setup인데 매매 X | Killzone 필터 | log: "outside allowed killzones [AM_MACRO]" |

`./run_casper.sh status`로 누적 통계 + ICT 매매 카운터 확인 가능.

---

## 11. 정리

| 차원 | 운용자가 봐야 할 것 |
|---|---|
| **시간** | KST 22:30~23:10 (서머타임), 그 외엔 봇 대기 또는 포지션 hold |
| **차트** | TQQQ 5m / QQQ 5m / SQQQ 5m / VIX / QQQ 일봉 |
| **결정 신호** | ORB 라인 + FVG box + Killzone band + Displacement candle |
| **진입 방향** | TQQQ Long (bullish setup) or SQQQ Long (QQQ bearish setup) |
| **청산** | TP 도달 or SL hit or 24:00 BE or 04:50 강제 |
| **출력 채널** | Telegram (즉시) + `logs/app/` (영구) + `run_casper.sh status` (요청 시) |

차트에 위 §5의 7개 라인을 그려두고 KST 22:30부터 1시간 정도 주시하면 봇의 시야 90%를 직접 따라갈 수 있습니다.

---

## 12. 더 깊이 들어가려면

| 주제 | 문서 |
|---|---|
| ICT 개념 정밀 정의 | [ICT_STRATEGY_INTEGRATION.md](ICT_STRATEGY_INTEGRATION.md) |
| 각 필터의 정량 임계값 + 사전 검증 | [PHASE1_PRECHECK.md](PHASE1_PRECHECK.md) |
| Sweep + CHoCH 알고리즘 | [PHASE2_IMPLEMENTATION.md](PHASE2_IMPLEMENTATION.md) |
| Daily Bias + QQQ→SQQQ 매핑 | [PHASE3_QQQ_MAPPING.md](PHASE3_QQQ_MAPPING.md) |
| KIS 비용 모델 백테스트 | [INTRADAY_COMPARISON.md](INTRADAY_COMPARISON.md), [BACKTEST_AFTER_ICT.md](BACKTEST_AFTER_ICT.md) |
| 캐스퍼 원전략 (Casper SMC 영상 기반) | [STRATEGY_REVIEW.md](STRATEGY_REVIEW.md) |
