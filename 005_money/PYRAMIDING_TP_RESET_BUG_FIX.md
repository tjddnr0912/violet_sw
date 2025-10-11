# 추가매수 후 익절 미발동 버그 수정

**날짜**: 2025-10-11 18:45
**심각도**: 🔴 HIGH (수익 기회 손실)
**영향**: 추가매수 후 TP1/TP2가 영구적으로 작동하지 않음

---

## 🐛 버그 설명

### 발생 시나리오

1. **Entry #1**: XRP 매수 @ 3,665 KRW
2. **TP1 도달**: 가격 상승 → 50% 매도 @ ~3,763 KRW
   - `first_target_hit = true`
   - `position_pct = 50%`
3. **Entry #2 (추가매수)**: XRP 추가 매수 @ 3,750 KRW
   - `position_pct`는 100%로 복구됨 ✅
   - **하지만 `first_target_hit`는 여전히 `true`** ❌
4. **TP1 조건 재충족**: 평균 매수가 3,707 KRW 기준으로 다시 +1.5% 달성
   - 현재가: 3,795 KRW (TP1 = 3,763 KRW 초과)
   - **익절 발동 안됨!** ❌

### 근본 원인

**`portfolio_manager_v3.py:357`**:
```python
if not first_target_hit and first_target > 0 and current_price >= first_target:
    # TP1 체크
```

**문제점**:
- `first_target_hit == true`이면 **영구적으로 TP1 체크를 건너뜀**
- 추가매수로 포지션이 100%로 복구되어도 플래그는 리셋되지 않음
- 결과: **추가매수 후 절대 TP1이 발동할 수 없음**

---

## ✅ 수정 내용

### 1. 추가매수 시 TP 플래그 리셋

**파일**: `live_executor_v3.py:427-434`

**수정 전**:
```python
if ticker in self.positions:
    # Pyramiding - add to existing position
    pos = self.positions[ticker]
    # ... 평균가 업데이트 ...

    # Track pyramid entry
    pos.entry_count += 1
    pos.entry_prices.append(price)
    pos.entry_times.append(datetime.now())
    pos.entry_sizes.append(units)

    # ← TP 플래그 리셋 없음! 버그!
```

**수정 후**:
```python
if ticker in self.positions:
    # Pyramiding - add to existing position
    pos = self.positions[ticker]
    # ... 평균가 업데이트 ...

    # Track pyramid entry
    pos.entry_count += 1
    pos.entry_prices.append(price)
    pos.entry_times.append(datetime.now())
    pos.entry_sizes.append(units)

    # IMPORTANT: Reset profit target flags when pyramiding
    # This allows TP1/TP2 to trigger again for the increased position
    if pos.first_target_hit:
        pos.first_target_hit = False
        pos.position_pct = 100.0  # Reset to full position
        self.logger.logger.info(
            f"PYRAMID: Resetting TP flags for {ticker} - position now 100%"
        )
```

### 2. 현재 XRP 포지션 수동 수정

**파일**: `logs/positions_v3.json`

```json
"XRP": {
  "position_pct": 100.0,           // 50.0 → 100.0
  "first_target_hit": false,       // true → false
  "profit_target_mode": "percentage_based"  // bb_based → percentage_based
}
```

**변경 이유**:
- 추가매수 완료 상태를 반영
- 다음 사이클에 TP1 체크가 다시 작동하도록 설정
- 퍼센테이지 모드로 변경 (사용자 설정 반영)

---

## 📊 수정 후 예상 동작

### 다음 사이클 (15분 후)

**XRP 상태**:
- 평균 매수가: 3,707 KRW
- 현재 포지션: 13.49 XRP (100%)
- TP1: 3,763 KRW (1.5%)
- TP2: 3,800 KRW (2.5%)

**현재가가 3,795 KRW라면**:
```
✅ TP1 조건 체크:
   - first_target_hit = false ✅
   - current_price (3,795) >= TP1 (3,763) ✅
   → 🎯 TP1 발동! 50% 매도 (6.75 XRP)

남은 포지션: 6.74 XRP (50%)
first_target_hit = true
position_pct = 50.0%
```

**만약 가격이 계속 상승하여 3,800 KRW 도달**:
```
✅ TP2 조건 체크:
   - first_target_hit = true ✅
   - second_target_hit = false ✅
   - current_price (3,800) >= TP2 (3,800) ✅
   → 🎯 TP2 발동! 남은 100% 매도 (6.74 XRP)

포지션 완전 청산
```

---

## 🎯 수정이 해결하는 문제들

### Before (버그 상태)

| 상황 | 동작 | 문제 |
|------|------|------|
| Entry #1 → TP1 발동 | 50% 매도 ✅ | - |
| Entry #2 (추가매수) | 포지션 100% 복구 ✅ | TP 플래그 리셋 안됨 ❌ |
| TP1 조건 재충족 | **체크 자체를 안함** ❌ | 수익 기회 손실! |
| TP2 조건 충족 | 체크는 하지만 의미 없음 | first_target_hit=true 필요 |

### After (수정 후)

| 상황 | 동작 | 결과 |
|------|------|------|
| Entry #1 → TP1 발동 | 50% 매도 ✅ | - |
| Entry #2 (추가매수) | 포지션 100% 복구 ✅ | **TP 플래그 리셋** ✅ |
| TP1 조건 재충족 | **정상 체크 및 발동** ✅ | 50% 매도 ✅ |
| TP2 조건 충족 | 정상 체크 및 발동 ✅ | 100% 청산 ✅ |

---

## 🧪 테스트 시나리오

### 시나리오 1: 추가매수 후 TP1 재발동

```
1. Entry #1: 50,000원 매수 @ 100,000원
2. TP1 도달: 50% 매도 @ 101,500원
3. Entry #2: 25,000원 추가매수 @ 102,000원
   → 평균 매수가 = 101,000원
   → TP1 = 102,515원
4. 가격 103,000원 도달
   → ✅ TP1 발동 (두 번째)
   → 50% 매도
```

### 시나리오 2: 여러 번 추가매수

```
1. Entry #1: 50,000원
2. TP1 도달: 50% 매도
3. Entry #2: 25,000원 (플래그 리셋)
4. TP1 도달: 50% 매도
5. Entry #3: 12,500원 (플래그 리셋)
6. TP1 도달: 50% 매도
   → 최대 3번까지 반복 가능
```

---

## ⚠️ 주의사항

### 1. 기존 포지션 처리

**현재 XRP처럼 이미 `first_target_hit=true` 상태인 포지션**:
- 수동으로 `positions_v3.json` 수정 필요
- 또는 포지션 청산 후 새로 시작

### 2. 향후 추가매수

**수정 적용 후 새로운 추가매수**:
- 자동으로 TP 플래그 리셋됨 ✅
- 로그에 "PYRAMID: Resetting TP flags..." 메시지 확인 가능

### 3. Stop-Loss 고려사항

추가매수 시 Stop-Loss도 업데이트됩니다:
- 평균 매수가 변경
- Chandelier Stop 재계산
- Breakeven 기준도 새 평균가로 변경

---

## 📝 관련 파일

| 파일 | 변경 사항 |
|------|-----------|
| `live_executor_v3.py` | TP 플래그 리셋 로직 추가 (line 427-434) |
| `logs/positions_v3.json` | XRP 포지션 수동 수정 (임시 조치) |
| `strategy_v3.py` | 퍼센테이지 모드 지원 추가 (이전 수정) |

---

## 🔄 업그레이드 경로

### 기존 사용자

1. **코드 업데이트**: `live_executor_v3.py` 수정 완료 ✅
2. **기존 포지션 확인**:
   ```bash
   cat logs/positions_v3.json
   ```
3. **first_target_hit=true인 포지션이 있다면**:
   - Option A: 수동으로 false로 변경 (위험: 즉시 TP1 발동 가능)
   - Option B: 청산 후 새로 시작 (안전)

### 새 포지션

- 자동으로 올바르게 작동 ✅
- 추가 조치 불필요

---

## 💡 개선 효과

### 1. 수익 기회 회복

**Before**: 추가매수 후 TP 영구 불가 → 수동 청산 필요
**After**: 추가매수 후에도 정상적으로 TP 작동 ✅

### 2. 전략 일관성

**Before**: 첫 매수와 추가매수의 동작이 다름
**After**: 모든 매수가 동일한 TP 로직 적용 ✅

### 3. 리스크 관리

**Before**: TP 미작동으로 수익 보호 실패
**After**: 계획된 수익 실현 가능 ✅

---

**수정 완료 시각**: 2025-10-11 18:45
**테스트 필요**: 다음 사이클(18:45)에 XRP TP1 발동 확인
**예상 결과**: 현재가 > 3,763 KRW라면 즉시 50% 매도
