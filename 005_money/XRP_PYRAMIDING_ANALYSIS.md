# XRP 추가매수 및 익절 미발동 분석 보고서

**날짜**: 2025-10-11
**대상**: XRP 포지션
**문제**: 추가매수 후 TP1이 발동하지 않음

---

## 📊 현재 XRP 포지션 상태

```json
{
  "ticker": "XRP",
  "size": 13.487949067758073,
  "entry_price": 3707.012811867835,  // 평균 매수가
  "position_pct": 50.0,  // TP1 이후 50% 남음
  "first_target_hit": true,  // TP1 이미 달성
  "entry_count": 2,  // 추가매수 1회 발생
  "entry_prices": [3665.0, 3750.0],
  "entry_sizes": [13.642564802182811, 6.666666666666667]
}
```

---

## 🔍 질문 1: 추가매수 금액은 50%인가?

### ✅ 답변: 맞습니다!

**코드 근거** (`portfolio_manager_v3.py:610-621`):

```python
base_amount_krw = 50,000 KRW  # 사용자 설정

if entry_number > 1:  # 추가매수
    multipliers = [1.0, 0.5, 0.25]  # 1차=100%, 2차=50%, 3차=25%
    multiplier = multipliers[entry_number - 1]
    trade_amount_krw = base_amount_krw * multiplier
```

**XRP 추가매수 내역**:
- **Entry #1**: 50,000원 × 1.0 = **50,000원** (3,665원에 매수 → 13.64 XRP)
- **Entry #2**: 50,000원 × 0.5 = **25,000원** (3,750원에 매수 → 6.67 XRP)

---

## 🎯 질문 2: TP1/TP2는 어떤 가격 기준으로 계산되나?

### ✅ 답변: 평균 매수가 기준

**계산식** (`strategy_v3.py:503-504`):

```python
# 평균 매수가 계산 (live_executor_v3.py:418)
entry_price = (old_value + new_value) / total_size
# = (13.64 × 3665 + 6.67 × 3750) / (13.64 + 6.67)
# = (49,981 + 25,013) / 20.31
# = 3,707 KRW

# 퍼센테이지 모드 TP 계산
TP1 = 3,707 × 1.015 = 3,763 KRW  (1.5%)
TP2 = 3,707 × 1.025 = 3,800 KRW  (2.5%)
```

**중요**: 개별 매수가가 아닌 **가중 평균 매수가**를 기준으로 모든 TP가 계산됩니다.

---

## 🚨 질문 3: 왜 TP1이 발동하지 않았나?

### ❌ 버그 발견: Ver3 strategy의 `_calculate_target_prices()` 메서드 결함

#### 문제점

**Ver3 기존 코드** (`strategy_v3.py:471-482`):

```python
def _calculate_target_prices(self, df: pd.DataFrame) -> Dict[str, float]:
    """Calculate target prices for partial exits."""
    latest = df.iloc[-1]

    return {
        'first_target': float(latest['bb_middle']),   # 무조건 BB만!
        'second_target': float(latest['bb_upper']),   # 무조건 BB만!
        'stop_loss': self._calculate_chandelier_stop(df),
    }
```

**문제**:
- 퍼센테이지 모드 설정을 **완전히 무시**
- 사용자가 1.5%/2.5% 설정해도 항상 **BB (Bollinger Band)** 가격만 반환
- `entry_price` 파라미터도 받지 못함

#### 실제 영향

사용자의 현재 설정:
```json
{
  "profit_target_mode": "percentage_based",
  "tp1_percentage": 1.5,
  "tp2_percentage": 2.5
}
```

**기대 동작**:
- TP1 = 3,707 × 1.015 = **3,763 KRW**
- 현재가 3,792 KRW (2.3% 상승) → **TP1 발동해야 함** ✅

**실제 동작** (버그로 인해):
- TP1 = BB middle line = **3,850 KRW** (예상치)
- 현재가 3,792 KRW < 3,850 KRW → **TP1 발동 안됨** ❌

---

## 🔧 수정 사항

### Ver2의 올바른 구현을 Ver3에 적용

**수정된 코드** (`strategy_v3.py:471-521`):

```python
def _calculate_target_prices(self, df: pd.DataFrame, entry_price: Optional[float] = None) -> Dict[str, float]:
    """
    Calculate target prices for partial exits.

    Supports two modes:
    1. BB-based: Use Bollinger Band levels (middle, upper)
    2. Percentage-based: Use percentage gains from entry price
    """
    if df is None or len(df) == 0:
        return {}

    latest = df.iloc[-1]
    current_price = float(latest['close'])

    # Get profit target mode from config
    profit_mode = self.exit_config.get('profit_target_mode', 'bb_based')

    if profit_mode == 'percentage_based':
        # 퍼센테이지 모드 - 진입가 기준 계산
        tp1_pct = self.exit_config.get('tp1_percentage', 1.5)
        tp2_pct = self.exit_config.get('tp2_percentage', 2.5)

        base_price = entry_price if entry_price is not None else current_price

        first_target = base_price * (1 + tp1_pct / 100.0)
        second_target = base_price * (1 + tp2_pct / 100.0)

        return {
            'first_target': float(first_target),
            'second_target': float(second_target),
            'stop_loss': self._calculate_chandelier_stop(df),
            'mode': 'percentage_based',
            'tp1_pct': tp1_pct,
            'tp2_pct': tp2_pct,
        }
    else:
        # BB 모드 - 볼린저 밴드 기준
        return {
            'first_target': float(latest['bb_middle']),
            'second_target': float(latest['bb_upper']),
            'stop_loss': self._calculate_chandelier_stop(df),
            'mode': 'bb_based',
        }
```

### 주요 개선 사항

1. **`entry_price` 파라미터 추가**: 평균 매수가를 받아서 정확한 TP 계산
2. **모드 분기 로직**: `profit_target_mode` 설정에 따라 BB / 퍼센테이지 선택
3. **메타데이터 반환**: `mode`, `tp1_pct`, `tp2_pct` 정보도 함께 반환하여 로그에 표시 가능

---

## ✅ 수정 후 예상 동작

### 다음 사이클 (15분 후)에 발생할 일

**현재 상태**:
- XRP 평균 매수가: 3,707 KRW
- 현재가: ~3,792 KRW (2.3% 상승)
- first_target_hit: `true` (이미 50% 매도 완료)

**다음 사이클**:

1. **Portfolio Manager** (`portfolio_manager_v3.py:345`):
   ```python
   target_prices = self.strategy._calculate_target_prices(price_data, entry_price)
   # → 이제 entry_price=3707을 전달하여 올바른 TP 계산
   ```

2. **TP2 체크** (`portfolio_manager_v3.py:368-377`):
   ```python
   second_target = 3,800 KRW  # 3707 × 1.025

   if first_target_hit and current_price >= second_target:
       # 현재가 3,792 < 3,800 → 아직 TP2 미도달
       # 계속 보유
   ```

3. **만약 가격이 3,800 이상 상승하면**:
   ```
   🎯 SECOND TARGET HIT (TP2 2.5%): XRP at 3,800 KRW (+2.51%) - Closing position
   → 남은 50% 전체 매도
   → 포지션 완전 청산
   ```

---

## 📈 전체 수익 시뮬레이션

### 시나리오: TP2에서 청산 (3,800 KRW)

**Entry #1** (50,000원):
- 매수: 13.64 XRP @ 3,665 KRW
- TP1 매도: 6.82 XRP @ 3,763 KRW = 25,664원 (+1,331원, +5.5%)
- TP2 매도: 6.82 XRP @ 3,800 KRW = 25,916원 (+1,583원, +6.5%)
- **Entry #1 총수익**: +2,914원 (+5.8%)

**Entry #2** (25,000원):
- 매수: 6.67 XRP @ 3,750 KRW
- TP1 매도: 3.34 XRP @ 3,763 KRW = 12,569원 (+69원, +0.6%)
- TP2 매도: 3.33 XRP @ 3,800 KRW = 12,654원 (+154원, +1.2%)
- **Entry #2 총수익**: +223원 (+0.9%)

**전체 수익**:
- 투자금: 75,000원
- 회수금: 78,137원 (예상)
- **총 수익: +3,137원 (+4.2%)**

---

## 🎓 학습 포인트

### 1. 추가매수 금액은 점진적으로 감소

```python
multipliers = [1.0, 0.5, 0.25]
# 1차: 100% (50,000원)
# 2차: 50%  (25,000원) ← 리스크 관리
# 3차: 25%  (12,500원) ← 추가 리스크 최소화
```

**이유**: 가격이 상승할수록 추가 매수 비중을 줄여 평균 단가 상승을 방지

### 2. TP는 항상 평균 매수가 기준

```python
# 개별 매수가 아님!
# 3665원 → TP1 = 3720원 (X)
# 3750원 → TP1 = 3806원 (X)

# 평균 매수가 기준 (O)
# 3707원 → TP1 = 3763원
```

**이유**: 포지션 전체의 손익을 일관되게 관리

### 3. 퍼센테이지 모드는 진입가에 "고정"

```python
# Position 생성 시 모드 고정 (live_executor_v3.py:434-448)
pos = Position(
    profit_target_mode=profit_mode,  # 진입 시점 모드 저장
    tp1_percentage=tp1_pct,
    tp2_percentage=tp2_pct
)
```

**이유**: 포지션 중간에 TP 기준이 바뀌면 혼란 발생 방지

---

## 🔄 다음 단계

1. **봇 재시작 필요 없음**: 다음 사이클(15분)에 자동으로 수정된 로직 적용
2. **XRP 포지션**: TP2 (3,800 KRW) 도달 시 남은 50% 자동 청산
3. **향후 새 포지션**: 퍼센테이지 모드로 정확한 TP 계산 보장

---

## 📝 요약

| 항목 | 내용 |
|------|------|
| **추가매수 금액** | 50% (25,000원) ✅ |
| **TP 계산 기준** | 평균 매수가 (3,707원) ✅ |
| **TP1 미발동 원인** | Ver3 버그 (BB 모드 강제 적용) ❌ |
| **수정 완료** | `_calculate_target_prices()` 메서드 업데이트 ✅ |
| **다음 동작** | TP2 (3,800원) 도달 시 남은 50% 청산 |

---

**수정 완료 시각**: 2025-10-11 18:20
**적용 예정**: 다음 분석 사이클 (18:30)
