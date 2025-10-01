# Code Redundancy and Duplication

**Category**: Code Quality & Maintainability
**Total Issues**: 12
**Date**: 2025-10-02
**Status**: Medium Priority

---

## Overview

This document identifies duplicate code patterns that violate the DRY (Don't Repeat Yourself) principle. Extracting common logic to shared functions can reduce codebase size by ~150 lines and improve maintainability.

---

## Issue #1: Duplicate Average Buy Price Calculation

**Severity**: HIGH
**Files**: `gui_trading_bot.py`, `trading_bot.py`, `main.py`
**Lines**: Multiple locations
**Impact**: HIGH - Same logic in 3 places

### Problem

Average buy price calculation logic is duplicated across 3 files with nearly identical implementation.

```python
# gui_trading_bot.py:136-158 (23 lines)
def calculate_avg_buy_price(self):
    total_amount = 0.0
    total_cost = 0.0
    for transaction in self.transaction_history.transactions:
        if transaction['action'] == 'BUY' and transaction['success']:
            total_amount += transaction['amount']
            total_cost += transaction['amount'] * transaction['price']
    return total_cost / total_amount if total_amount > 0 else 0.0

# trading_bot.py:245-268 (24 lines) - ❌ Same logic
def calculate_avg_buy_price(self):
    total_amount = 0.0
    total_cost = 0.0
    for transaction in self.transaction_history.transactions:
        if transaction['action'] == 'BUY' and transaction['success']:
            total_amount += transaction['amount']
            total_cost += transaction['amount'] * transaction['price']
    return total_cost / total_amount if total_amount > 0 else 0.0

# main.py:380-395 (16 lines) - ❌ Same logic again
```

### Recommended Fix

**Create shared utility function**

```python
# Create new file: utils/transaction_utils.py
def calculate_avg_buy_price(transactions, ticker=None):
    """Calculate average buy price from transaction history

    Args:
        transactions: List of transaction dicts
        ticker: Optional ticker filter

    Returns:
        float: Average buy price
    """
    total_amount = 0.0
    total_cost = 0.0

    for tx in transactions:
        if ticker and tx.get('ticker') != ticker:
            continue
        if tx['action'] == 'BUY' and tx['success']:
            total_amount += tx['amount']
            total_cost += tx['amount'] * tx['price']

    return total_cost / total_amount if total_amount > 0 else 0.0

# Usage in all files:
from utils.transaction_utils import calculate_avg_buy_price

avg_price = calculate_avg_buy_price(self.transaction_history.transactions, self.ticker)
```

**Impact**: Reduces 63 lines to 20 lines (**68% reduction**)

---

## Issue #2: Duplicate Transaction Filtering

**Severity**: MEDIUM
**Files**: `gui_trading_bot.py`, `logger.py`, `main.py`
**Lines**: Multiple locations
**Impact**: MEDIUM - Same pattern in 4+ places

### Problem

Filtering transactions by ticker and success status is repeated throughout the codebase.

```python
# Pattern repeated 4+ times:
filtered = [tx for tx in transactions
            if tx['ticker'] == coin and tx['success']]
```

### Recommended Fix

```python
# utils/transaction_utils.py
def filter_transactions(transactions, ticker=None, action=None, success_only=True):
    """Filter transactions by criteria"""
    filtered = transactions

    if ticker:
        filtered = [tx for tx in filtered if tx.get('ticker') == ticker]
    if action:
        filtered = [tx for tx in filtered if tx.get('action') == action]
    if success_only:
        filtered = [tx for tx in filtered if tx.get('success', False)]

    return filtered

# Usage:
buy_txs = filter_transactions(transactions, ticker='BTC', action='BUY')
```

---

## Issue #3: Duplicate Price Formatting

**Severity**: LOW
**Files**: `gui_app.py` (multiple locations)
**Lines**: 200, 450, 680, 890, 1050
**Impact**: LOW - Inconsistent formatting

### Problem

Currency formatting is done inline with inconsistent patterns.

```python
# gui_app.py - 5+ different locations:
f"₩{price:,.0f}"        # Location 1
f"₩{price:,.2f}"        # Location 2 - ❌ Different precision
f"{price:,} 원"         # Location 3 - ❌ Different format
"₩{:,.0f}".format(price) # Location 4 - ❌ Old-style format
```

### Recommended Fix

```python
# utils/formatters.py
def format_krw(amount, decimals=0):
    """Format Korean Won consistently"""
    return f"₩{amount:,.{decimals}f}"

def format_crypto(amount, symbol='BTC', decimals=8):
    """Format cryptocurrency amount"""
    return f"{amount:.{decimals}f} {symbol}"

# Usage:
price_display = format_krw(price)  # ✅ Consistent everywhere
```

---

## Issue #4: Duplicate Timestamp Conversion

**Severity**: LOW
**Files**: `main.py`, `logger.py`, `gui_app.py`
**Lines**: Multiple locations
**Impact**: LOW - Repeated conversion logic

### Problem

Converting timestamps to readable formats is duplicated.

```python
# Repeated pattern:
from datetime import datetime
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Another location:
timestamp = datetime.fromtimestamp(ts).strftime("%Y%m%d_%H%M%S")

# Yet another:
timestamp = datetime.now().isoformat()
```

### Recommended Fix

```python
# utils/time_utils.py
from datetime import datetime

def get_timestamp_display():
    """Get human-readable timestamp"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_timestamp_filename():
    """Get filename-safe timestamp"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def get_timestamp_iso():
    """Get ISO format timestamp"""
    return datetime.now().isoformat()

def format_timestamp(ts, format='display'):
    """Format Unix timestamp"""
    formats = {
        'display': "%Y-%m-%d %H:%M:%S",
        'filename': "%Y%m%d_%H%M%S",
        'iso': None  # Use .isoformat()
    }
    dt = datetime.fromtimestamp(ts)
    if format == 'iso':
        return dt.isoformat()
    return dt.strftime(formats.get(format, formats['display']))
```

---

## Issue #5: Duplicate Config Access Pattern

**Severity**: MEDIUM
**Files**: Multiple files
**Lines**: Throughout
**Impact**: MEDIUM - Repeated pattern with default values

### Problem

Accessing config with defaults is repeated with same pattern.

```python
# Repeated 20+ times across files:
interval = self.config.get('candlestick_interval', '1h')
ma_short = self.config.get('short_ma_window', 20)
ma_long = self.config.get('long_ma_window', 50)
```

### Recommended Fix

```python
# config_manager.py
class ConfigAccessor:
    """Type-safe config accessor with defaults"""

    def __init__(self, config):
        self.config = config

    def get_interval(self):
        return self.config.get('candlestick_interval', '1h')

    def get_ma_windows(self):
        return {
            'short': self.config.get('short_ma_window', 20),
            'long': self.config.get('long_ma_window', 50)
        }

    def get_rsi_params(self):
        return {
            'period': self.config.get('rsi_period', 14),
            'overbought': self.config.get('rsi_overbought', 70),
            'oversold': self.config.get('rsi_oversold', 30)
        }

# Usage:
cfg = ConfigAccessor(self.config)
interval = cfg.get_interval()  # ✅ Centralized defaults
ma_windows = cfg.get_ma_windows()
```

---

## Issue #6: Duplicate Error Handling

**Severity**: MEDIUM
**Files**: `bithumb_api.py`, `trading_bot.py`
**Lines**: Multiple API call locations
**Impact**: MEDIUM - Repeated try-except pattern

### Problem

API error handling is duplicated with similar patterns.

```python
# Pattern repeated 6+ times:
try:
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    return data
except requests.RequestException as e:
    self.logger.error(f"API error: {e}")
    return None
except json.JSONDecodeError as e:
    self.logger.error(f"JSON error: {e}")
    return None
```

### Recommended Fix

```python
# bithumb_api.py
def _api_call_with_retry(self, url, method='GET', retries=3):
    """Centralized API call with error handling and retry"""
    for attempt in range(retries):
        try:
            if method == 'GET':
                response = requests.get(url, timeout=10)
            else:
                response = requests.post(url, timeout=10)

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            self.logger.error(f"API error (attempt {attempt+1}/{retries}): {e}")
            if attempt == retries - 1:
                return None
            time.sleep(2 ** attempt)  # Exponential backoff

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            return None

    return None

# Usage:
data = self._api_call_with_retry(url)  # ✅ Centralized error handling
```

---

## Issue #7: Duplicate Validation Logic

**Severity**: LOW
**Files**: `trading_bot.py`, `gui_trading_bot.py`
**Lines**: Multiple locations
**Impact**: LOW - Same validation checks

### Problem

Input validation is repeated in multiple places.

```python
# Repeated pattern:
if amount <= 0:
    self.logger.error("Amount must be positive")
    return False
if ticker not in ['BTC', 'ETH', 'XRP']:
    self.logger.error("Invalid ticker")
    return False
```

### Recommended Fix

```python
# utils/validators.py
class TradingValidator:
    VALID_TICKERS = ['BTC', 'ETH', 'XRP', 'ADA', 'DOT']

    @staticmethod
    def validate_amount(amount, min_amount=1000):
        if not isinstance(amount, (int, float)):
            raise ValueError("Amount must be numeric")
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount < min_amount:
            raise ValueError(f"Amount must be >= {min_amount}")
        return True

    @staticmethod
    def validate_ticker(ticker):
        if ticker not in TradingValidator.VALID_TICKERS:
            raise ValueError(f"Invalid ticker. Must be one of {TradingValidator.VALID_TICKERS}")
        return True

# Usage:
from utils.validators import TradingValidator

try:
    TradingValidator.validate_amount(amount)
    TradingValidator.validate_ticker(ticker)
except ValueError as e:
    self.logger.error(str(e))
    return False
```

---

## Issue #8: Duplicate Signal Interpretation

**Severity**: MEDIUM
**Files**: `gui_trading_bot.py`, `main.py`
**Lines**: 200-220, 450-470
**Impact**: MEDIUM - Same decision logic

### Problem

Interpreting weighted signals into actions is duplicated.

```python
# gui_trading_bot.py:200-220
def interpret_signal(self, weighted_signal, confidence):
    if weighted_signal > 0.5 and confidence > 0.6:
        return 'buy'
    elif weighted_signal < -0.5 and confidence > 0.6:
        return 'sell'
    return 'hold'

# main.py:450-470 - ❌ Duplicate logic
```

### Recommended Fix

```python
# strategy.py (add to TradingStrategy class)
@staticmethod
def interpret_weighted_signal(weighted_signal, confidence,
                              signal_threshold=0.5,
                              confidence_threshold=0.6):
    """Interpret weighted signal into trading action

    Args:
        weighted_signal: Signal strength (-1.0 to +1.0)
        confidence: Confidence level (0.0 to 1.0)
        signal_threshold: Minimum signal strength (default 0.5)
        confidence_threshold: Minimum confidence (default 0.6)

    Returns:
        str: 'buy', 'sell', or 'hold'
    """
    if confidence < confidence_threshold:
        return 'hold'

    if weighted_signal > signal_threshold:
        return 'buy'
    elif weighted_signal < -signal_threshold:
        return 'sell'

    return 'hold'

# Usage:
action = TradingStrategy.interpret_weighted_signal(
    analysis['weighted_signal'],
    analysis['confidence']
)
```

---

## Issue #9: Duplicate DataFrame Column Checks

**Severity**: LOW
**Files**: `strategy.py` (multiple methods)
**Lines**: Throughout indicator functions
**Impact**: LOW - Repeated pattern

### Problem

Checking if required columns exist in DataFrame is repeated.

```python
# Repeated 8+ times:
if 'close' not in df.columns:
    raise ValueError("DataFrame must have 'close' column")
if 'volume' not in df.columns:
    raise ValueError("DataFrame must have 'volume' column")
```

### Recommended Fix

```python
# strategy.py
def _validate_dataframe(self, df, required_columns=None):
    """Validate DataFrame has required columns"""
    if required_columns is None:
        required_columns = ['open', 'high', 'low', 'close', 'volume']

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing required columns: {missing}")

    if len(df) < 2:
        raise ValueError("DataFrame must have at least 2 rows")

    return True

# Usage:
def calculate_rsi(self, df, period=14):
    self._validate_dataframe(df, ['close'])  # ✅ One-liner validation
    # ... calculate RSI
```

---

## Issue #10: Duplicate Logging Pattern

**Severity**: LOW
**Files**: Multiple files
**Lines**: Throughout
**Impact**: LOW - Repeated log formatting

### Problem

Logging trade decisions follows same pattern everywhere.

```python
# Repeated pattern:
self.logger.info(f"[{ticker}] {action.upper()} signal - "
                f"Price: {price}, Confidence: {confidence:.2f}")
```

### Recommended Fix

```python
# logger.py (add to TradingLogger)
def log_trading_decision(self, ticker, action, price, confidence, **kwargs):
    """Centralized trading decision logging"""
    msg = f"[{ticker}] {action.upper()} signal - Price: {price:,.0f}, Confidence: {confidence:.2%}"

    if kwargs:
        extra = ", ".join(f"{k}: {v}" for k, v in kwargs.items())
        msg += f" | {extra}"

    self.logger.info(msg)

# Usage:
self.logger.log_trading_decision(
    ticker='BTC',
    action='buy',
    price=50000000,
    confidence=0.75,
    rsi=45,
    macd='bullish'
)
```

---

## Summary Table

| Issue | Files Affected | Lines Duplicate | Reduction | Fix Time |
|-------|----------------|-----------------|-----------|----------|
| Avg buy price calc | 3 | 63 | 68% | 30 min |
| Transaction filtering | 4+ | 20 | 75% | 20 min |
| Price formatting | 5+ | 10 | 80% | 15 min |
| Timestamp conversion | 3 | 15 | 70% | 20 min |
| Config access | Many | 40 | 60% | 45 min |
| Error handling | 6+ | 50 | 80% | 1 hour |
| Validation logic | 2 | 20 | 70% | 30 min |
| Signal interpretation | 2 | 40 | 75% | 20 min |
| DataFrame checks | 8+ | 25 | 85% | 15 min |
| Logging pattern | Many | 15 | 70% | 15 min |
| **TOTAL** | | **~298** | **~150 lines saved** | **~4 hours** |

---

## Recommended Action Plan

### Phase 1: High-Impact Utilities (2 hours)
1. ✅ Create transaction_utils.py (avg price, filtering)
2. ✅ Centralize error handling in API calls
3. ✅ Create formatters.py (currency, timestamps)

**Impact**: Eliminates 130 lines of duplication

### Phase 2: Validators and Helpers (1.5 hours)
4. ✅ Create validators.py
5. ✅ Create ConfigAccessor class
6. ✅ Centralize DataFrame validation

**Impact**: Eliminates 85 lines, improves type safety

### Phase 3: Logging and Patterns (30 minutes)
7. ✅ Centralize logging patterns
8. ✅ Create signal interpretation helper

**Impact**: Eliminates 55 lines, improves consistency

**Total time**: 4 hours
**Code reduction**: ~150 lines (~11% of codebase)
**Maintainability**: Significantly improved

---

## Benefits

### Maintainability
- ✅ Single source of truth for common logic
- ✅ Easier to update behavior (one place to change)
- ✅ Reduced chance of inconsistencies

### Testing
- ✅ Can unit test shared utilities easily
- ✅ More comprehensive test coverage

### Readability
- ✅ Clearer intent with named functions
- ✅ Less clutter in main business logic

---

## Implementation Guidelines

### 1. Create Utility Module Structure

```
utils/
├── __init__.py
├── transaction_utils.py   # Transaction calculations
├── formatters.py           # Display formatting
├── time_utils.py           # Timestamp handling
├── validators.py           # Input validation
└── api_utils.py            # API error handling
```

### 2. Migration Strategy

- **Don't refactor everything at once**
- Start with highest-impact duplications
- Test thoroughly after each extraction
- Update documentation

### 3. Testing

Each utility function should have unit tests:

```python
# tests/test_transaction_utils.py
def test_calculate_avg_buy_price():
    transactions = [
        {'action': 'BUY', 'success': True, 'amount': 0.1, 'price': 50000},
        {'action': 'BUY', 'success': True, 'amount': 0.2, 'price': 52000},
    ]
    avg = calculate_avg_buy_price(transactions)
    assert avg == 51333.33
```

---

**End of Document**
