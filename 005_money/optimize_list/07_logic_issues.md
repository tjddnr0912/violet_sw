# Logic Issues and Edge Cases

**Category**: Correctness & Bug Fixes
**Total Issues**: 6
**Date**: 2025-10-02
**Status**: Medium-High Priority

---

## Overview

This document identifies logic errors, edge cases, and potential bugs that could cause incorrect behavior or crashes. These issues should be addressed to ensure reliability and correctness.

---

## Issue #1: Division by Zero in Average Price Calculation

**Severity**: MEDIUM
**File**: `gui_trading_bot.py`
**Lines**: 136-158
**Impact**: MEDIUM - Could crash bot

### Problem

Average buy price calculation doesn't handle the case where no buy transactions exist.

```python
# gui_trading_bot.py:158
def calculate_avg_buy_price(self):
    total_amount = 0.0
    total_cost = 0.0
    for transaction in self.transaction_history.transactions:
        if transaction['action'] == 'BUY' and transaction['success']:
            total_amount += transaction['amount']
            total_cost += transaction['amount'] * transaction['price']

    return total_cost / total_amount  # ❌ Division by zero if no buys!
```

### Edge Cases
1. **No transactions yet**: `total_amount = 0` → `ZeroDivisionError`
2. **Only sell transactions**: `total_amount = 0` → `ZeroDivisionError`
3. **All buy transactions failed**: `total_amount = 0` → `ZeroDivisionError`

### Recommended Fix

```python
# gui_trading_bot.py:158
def calculate_avg_buy_price(self):
    total_amount = 0.0
    total_cost = 0.0

    for transaction in self.transaction_history.transactions:
        if transaction['action'] == 'BUY' and transaction['success']:
            total_amount += transaction['amount']
            total_cost += transaction['amount'] * transaction['price']

    # ✅ Handle division by zero
    if total_amount == 0:
        return 0.0  # Or None, depending on desired behavior

    return total_cost / total_amount
```

---

## Issue #2: Incorrect Profit Calculation for Partial Sells

**Severity**: HIGH
**File**: `gui_app.py`
**Lines**: 650-680
**Impact**: HIGH - Incorrect profit reporting

### Problem

Profit calculation doesn't properly handle partial sells with FIFO accounting.

```python
# Example scenario that breaks:
# BUY 1.0 BTC @ 50,000 KRW
# BUY 1.0 BTC @ 52,000 KRW
# SELL 1.5 BTC @ 55,000 KRW  # Should use FIFO: 1.0@50k + 0.5@52k

# Current code doesn't properly track which portions were sold
```

### Recommended Fix

**Implement Proper FIFO Queue**

```python
# gui_app.py:650
from collections import deque

def calculate_profit_fifo(self):
    """Proper FIFO profit calculation"""
    buy_queue = deque()  # Queue of (amount, price) tuples
    total_profit = 0.0
    total_fees = 0.0

    for tx in sorted(self.transactions, key=lambda x: x['timestamp']):
        if not tx['success']:
            continue

        if tx['action'] == 'BUY':
            buy_queue.append({
                'amount': tx['amount'],
                'price': tx['price'],
                'remaining': tx['amount']
            })

        elif tx['action'] == 'SELL':
            sell_amount = tx['amount']
            sell_price = tx['price']

            # Match against oldest buys (FIFO) ✅
            while sell_amount > 0 and buy_queue:
                oldest_buy = buy_queue[0]
                matched_amount = min(sell_amount, oldest_buy['remaining'])

                # Calculate profit for this portion
                cost_basis = matched_amount * oldest_buy['price']
                proceeds = matched_amount * sell_price
                profit = proceeds - cost_basis

                # Subtract fees
                fee = proceeds * tx.get('fee_rate', 0.0025)
                profit -= fee

                total_profit += profit
                total_fees += fee

                # Update remaining amounts
                sell_amount -= matched_amount
                oldest_buy['remaining'] -= matched_amount

                if oldest_buy['remaining'] == 0:
                    buy_queue.popleft()  # Fully consumed

            # If sell_amount > 0 here, selling more than bought (error!)
            if sell_amount > 0:
                self.logger.warning(f"Selling more than bought! Excess: {sell_amount}")

    return {
        'total_profit': total_profit,
        'total_fees': total_fees,
        'net_profit': total_profit - total_fees,
        'remaining_holdings': sum(b['remaining'] for b in buy_queue)
    }
```

---

## Issue #3: Race Condition in Price Monitoring

**Severity**: MEDIUM
**File**: `gui_trading_bot.py`
**Lines**: 50-65
**Impact**: MEDIUM - Could cause inconsistent state

### Problem

Price monitoring loop and main bot logic both access `current_price` without synchronization.

```python
# gui_trading_bot.py:50
def _price_monitor_loop(self):
    while self.monitoring:
        self.current_price = self.fetch_price()  # ❌ Race condition

# Meanwhile, in another thread:
def make_trading_decision(self):
    price = self.current_price  # ❌ Could read partial update
```

### Recommended Fix

**Use Thread-Safe Locking**

```python
# gui_trading_bot.py
import threading

class GUITradingBot:
    def __init__(self):
        self._price_lock = threading.Lock()
        self._current_price = None

    @property
    def current_price(self):
        """Thread-safe price getter"""
        with self._price_lock:
            return self._current_price

    @current_price.setter
    def current_price(self, value):
        """Thread-safe price setter"""
        with self._price_lock:
            self._current_price = value

    def _price_monitor_loop(self):
        while self.monitoring:
            new_price = self.fetch_price()
            self.current_price = new_price  # ✅ Thread-safe
```

---

## Issue #4: NaN/Inf Handling in Indicators

**Severity**: MEDIUM
**File**: `strategy.py`
**Lines**: Multiple indicator functions
**Impact**: MEDIUM - Could cause invalid signals

### Problem

Indicator calculations can produce NaN or Inf values, which aren't handled.

```python
# strategy.py
def calculate_rsi(self, df, period=14):
    # ...
    rs = avg_gain / avg_loss  # ❌ Could be Inf if avg_loss = 0
    rsi = 100 - (100 / (1 + rs))  # ❌ Could be NaN
    return rsi  # Returns NaN/Inf without handling
```

### Recommended Fix

**Handle NaN/Inf Explicitly**

```python
# strategy.py
def calculate_rsi(self, df, period=14):
    # ... calculation ...

    # Handle edge cases ✅
    rs = avg_gain / avg_loss.replace(0, 1e-10)  # Avoid division by zero
    rsi = 100 - (100 / (1 + rs))

    # Clip to valid range ✅
    rsi = rsi.clip(0, 100)

    # Replace remaining NaNs with neutral value ✅
    rsi = rsi.fillna(50)  # Neutral RSI

    return rsi

# Apply to all indicators:
def _validate_indicator(self, series, min_val=None, max_val=None, fill_value=0):
    """Validate and clean indicator values"""
    # Remove inf
    series = series.replace([np.inf, -np.inf], np.nan)

    # Clip to range if specified
    if min_val is not None or max_val is not None:
        series = series.clip(min_val, max_val)

    # Fill NaN
    series = series.fillna(fill_value)

    return series
```

---

## Issue #5: Incorrect Confidence Calculation

**Severity**: MEDIUM
**File**: `strategy.py`
**Lines**: 700-750
**Impact**: MEDIUM - Could overestimate confidence

### Problem

Confidence calculation doesn't properly normalize when indicators disagree.

```python
# strategy.py:700
def calculate_confidence(self, signals):
    # ❌ This logic doesn't account for conflicting signals properly
    total_confidence = 0
    for indicator, signal in signals.items():
        if signal['direction'] in ['buy', 'sell']:
            total_confidence += signal['strength']

    return total_confidence / len(signals)  # ❌ Wrong normalization
```

### Example Issue
```python
# Scenario:
signals = {
    'rsi': {'direction': 'buy', 'strength': 0.9},
    'macd': {'direction': 'sell', 'strength': 0.9},  # Opposite!
}
# Current: confidence = (0.9 + 0.9) / 2 = 0.9 ❌ (high confidence for conflicting signals!)
# Should be: Low confidence when signals conflict
```

### Recommended Fix

```python
# strategy.py:700
def calculate_confidence(self, signals):
    """Calculate confidence considering signal agreement"""
    buy_strength = 0
    sell_strength = 0
    total_indicators = 0

    for indicator, signal in signals.items():
        if signal['direction'] == 'buy':
            buy_strength += signal['strength']
            total_indicators += 1
        elif signal['direction'] == 'sell':
            sell_strength += signal['strength']
            total_indicators += 1

    if total_indicators == 0:
        return 0.0

    # Calculate agreement ✅
    total_strength = buy_strength + sell_strength
    agreement = abs(buy_strength - sell_strength) / total_strength

    # Confidence is high when signals agree ✅
    return agreement
```

---

## Issue #6: Missing Input Validation in Config

**Severity**: MEDIUM
**File**: `config_manager.py`
**Lines**: 30-50
**Impact**: MEDIUM - Invalid config could crash bot

### Problem

Configuration values aren't validated before use.

```python
# config_manager.py:30
def update_config(self, new_config):
    self.config.update(new_config)  # ❌ No validation!

    # Could lead to:
    # - Negative trade amounts
    # - Invalid time intervals
    # - Signal weights that don't sum to 1.0
    # - Invalid API keys
```

### Recommended Fix

**Add Configuration Validation**

```python
# config_manager.py:30
class ConfigValidator:
    @staticmethod
    def validate_trading_config(config):
        """Validate trading configuration"""
        errors = []

        # Validate trade amount ✅
        if config.get('trade_amount_krw', 0) <= 0:
            errors.append("trade_amount_krw must be positive")

        if config.get('trade_amount_krw', 0) > config.get('max_trade_amount', float('inf')):
            errors.append("trade_amount_krw exceeds max_trade_amount")

        # Validate percentages ✅
        for key in ['stop_loss_percent', 'take_profit_percent']:
            value = config.get(key, 0)
            if not 0 <= value <= 100:
                errors.append(f"{key} must be between 0 and 100")

        return errors

    @staticmethod
    def validate_strategy_config(config):
        """Validate strategy configuration"""
        errors = []

        # Validate signal weights sum to 1.0 ✅
        weights = config.get('signal_weights', {})
        if weights:
            total = sum(weights.values())
            if not 0.99 <= total <= 1.01:  # Allow small float error
                errors.append(f"signal_weights must sum to 1.0 (got {total})")

        # Validate periods are positive ✅
        for key in ['rsi_period', 'macd_fast', 'macd_slow', 'atr_period']:
            value = config.get(key, 1)
            if value <= 0:
                errors.append(f"{key} must be positive")

        # Validate interval ✅
        valid_intervals = ['30m', '1h', '6h', '12h', '24h']
        interval = config.get('candlestick_interval')
        if interval not in valid_intervals:
            errors.append(f"candlestick_interval must be one of {valid_intervals}")

        return errors

def update_config(self, new_config):
    """Update configuration with validation"""
    # Validate before updating ✅
    errors = []
    errors.extend(ConfigValidator.validate_trading_config(new_config))
    errors.extend(ConfigValidator.validate_strategy_config(new_config))

    if errors:
        raise ValueError(f"Invalid configuration:\n" + "\n".join(errors))

    self.config.update(new_config)
    self.logger.info("Configuration updated successfully")
```

---

## Summary Table

| Issue | Severity | File | Impact | Fix Time |
|-------|----------|------|--------|----------|
| Division by zero | MEDIUM | gui_trading_bot.py:158 | Could crash | 10 min |
| Incorrect profit calc | HIGH | gui_app.py:650 | Wrong financials | 1 hour |
| Race condition | MEDIUM | gui_trading_bot.py:50 | Inconsistent state | 30 min |
| NaN/Inf handling | MEDIUM | strategy.py | Invalid signals | 30 min |
| Confidence calc | MEDIUM | strategy.py:700 | Misleading confidence | 45 min |
| Config validation | MEDIUM | config_manager.py:30 | Could crash | 1 hour |

---

## Recommended Action Plan

### Phase 1: Critical Fixes (2 hours)
1. ✅ Fix profit calculation with FIFO (1 hour)
2. ✅ Add config validation (1 hour)

**Risk**: High - Financial calculations must be correct

### Phase 2: Stability Fixes (1.5 hours)
3. ✅ Add NaN/Inf handling in indicators (30 min)
4. ✅ Fix confidence calculation (45 min)
5. ✅ Add division by zero protection (15 min)

**Risk**: Medium - Prevents crashes and incorrect signals

### Phase 3: Thread Safety (30 minutes)
6. ✅ Add thread-safe locking (30 min)

**Risk**: Low-Medium - Prevents rare race conditions

**Total time**: 4 hours
**Expected results**: **Correct behavior, no crashes, accurate financials**

---

## Testing Checklist

### Profit Calculation Tests
- [ ] Test with single buy/sell
- [ ] Test with multiple buys, single sell
- [ ] Test with multiple buys, partial sell
- [ ] Test with no transactions
- [ ] Test with failed transactions
- [ ] Verify FIFO ordering

### Edge Case Tests
- [ ] Test with empty transaction history
- [ ] Test with all NaN indicators
- [ ] Test with conflicting signals
- [ ] Test with zero volume candles
- [ ] Test with invalid config values

### Thread Safety Tests
- [ ] Run concurrent price updates
- [ ] Verify no race conditions
- [ ] Test under high load

---

## Validation Tests to Add

```python
# tests/test_logic_fixes.py

def test_avg_buy_price_no_transactions():
    """Test average buy price with no transactions"""
    bot = GUITradingBot()
    avg = bot.calculate_avg_buy_price()
    assert avg == 0.0  # Should not crash

def test_profit_calc_fifo():
    """Test FIFO profit calculation"""
    transactions = [
        {'action': 'BUY', 'amount': 1.0, 'price': 50000, 'success': True},
        {'action': 'BUY', 'amount': 1.0, 'price': 52000, 'success': True},
        {'action': 'SELL', 'amount': 1.5, 'price': 55000, 'success': True},
    ]
    profit = calculate_profit_fifo(transactions)
    # Should use 1.0@50k + 0.5@52k = 76,000 cost
    # Proceeds: 1.5 × 55,000 = 82,500
    # Profit: 82,500 - 76,000 = 6,500 (before fees)
    assert abs(profit['total_profit'] - 6500) < 100  # Allow for fees

def test_indicator_nan_handling():
    """Test NaN handling in indicators"""
    df = pd.DataFrame({'close': [100, 100, 100]})  # No change → RSI NaN
    rsi = calculate_rsi(df, period=14)
    assert not rsi.isna().any()  # No NaN values
    assert (rsi >= 0).all() and (rsi <= 100).all()  # Valid range

def test_config_validation():
    """Test configuration validation"""
    invalid_config = {'trade_amount_krw': -1000}  # Negative!
    with pytest.raises(ValueError):
        update_config(invalid_config)
```

---

**End of Document**
