# Unused Code and Dead Code Analysis

**Category**: Code Quality
**Total Issues**: 18
**Date**: 2025-10-02
**Status**: Medium Priority

---

## Overview

This document identifies unused variables, functions, imports, and dead code that can be safely removed to improve code maintainability and reduce codebase size by ~12%.

---

## Unused Imports

### Issue #1: Unused datetime import
**File**: `main.py`
**Line**: 3
**Severity**: LOW

```python
from datetime import datetime, timedelta  # ❌ timedelta never used
```

**Fix**:
```python
from datetime import datetime  # ✅
```

---

### Issue #2: Unused sys import
**File**: `bithumb_api.py`
**Line**: 2
**Severity**: LOW

```python
import sys  # ❌ Never used in file
import requests
import json
```

**Fix**: Remove the import

---

### Issue #3: Unused typing imports
**File**: `strategy.py`
**Line**: 5-6
**Severity**: LOW

```python
from typing import Dict, Any, Tuple, List, Optional  # ❌ List and Optional never used
```

**Fix**:
```python
from typing import Dict, Any, Tuple  # ✅
```

---

### Issue #4: Unused matplotlib import
**File**: `gui_trading_bot.py`
**Line**: 8
**Severity**: LOW

```python
import matplotlib.pyplot as plt  # ❌ Never used (only in chart_widget)
```

**Fix**: Remove the import

---

## Unused Variables

### Issue #5: Unused auto_refresh_counter
**File**: `gui_app.py`
**Line**: 884
**Severity**: LOW

```python
def __init__(self):
    # ...
    self.auto_refresh_counter = 0  # ❌ Set but never read
```

**Analysis**: Variable is incremented but never used for decision-making.

**Fix**: Remove if truly unused, or implement the intended auto-refresh logic.

---

### Issue #6: Unused return value in report generation
**File**: `main.py`
**Line**: 541
**Severity**: LOW

```python
def run_scheduled_task(self):
    # ...
    report = self.generate_comprehensive_report()  # ❌ Return value never used
    # No logging or processing of report
```

**Fix**:
```python
report = self.generate_comprehensive_report()
self.logger.info(f"Generated report: {report['summary']}")  # ✅ Use the report
```

---

### Issue #7: Unused last_update_time
**File**: `gui_app.py`
**Line**: 120
**Severity**: LOW

```python
self.last_update_time = None  # ❌ Set but never checked
```

**Fix**: Either use it for throttling or remove it.

---

### Issue #8: Unused config backup
**File**: `config_manager.py`
**Line**: 45
**Severity**: LOW

```python
def update_config(self, new_config):
    old_config = self.config.copy()  # ❌ Backup never used
    self.config.update(new_config)
```

**Fix**: Either implement rollback functionality or remove the backup.

---

## Unused Functions

### Issue #9: Unused validation function
**File**: `bithumb_api.py`
**Lines**: 64-79
**Severity**: MEDIUM

```python
def _validate_secret_key(self, secret_key):
    """Validates the secret key format"""
    # 16 lines of validation logic
    # ❌ Function defined but never called
```

**Impact**: Dead code adds 16 lines

**Fix**: Either call it in `__init__` or remove it.

```python
# If you want to use it:
def __init__(self, connect_key, secret_key):
    self._validate_secret_key(secret_key)  # ✅ Use it
    self.secret_key = secret_key
```

---

### Issue #10: Unused decide_action wrapper
**File**: `strategy.py`
**Lines**: 945-951
**Severity**: MEDIUM

```python
def decide_action(self, analysis):
    """Wrapper function that's never called"""
    # ❌ Replaced by generate_weighted_signals but not removed
    confidence = analysis.get('confidence', 0)
    if confidence > 0.6:
        return 'buy'
    elif confidence < -0.6:
        return 'sell'
    return 'hold'
```

**Impact**: 7 lines of dead code

**Fix**: Remove the function entirely (logic moved to `generate_weighted_signals`)

---

### Issue #11: Unused format_currency helper
**File**: `gui_app.py`
**Lines**: 1200-1205
**Severity**: LOW

```python
def format_currency(self, amount):
    """Formats currency - but never called"""
    # ❌ All formatting done inline with f-strings instead
    return f"₩{amount:,.0f}"
```

**Fix**: Either use it consistently or remove it and keep inline formatting.

---

### Issue #12: Unused calculate_sharpe_ratio
**File**: `strategy.py`
**Lines**: 850-865
**Severity**: MEDIUM

```python
def calculate_sharpe_ratio(self, returns, risk_free_rate=0.02):
    """Calculate Sharpe ratio - never called"""
    # ❌ 15 lines of statistical calculations
    # May have been planned feature
```

**Fix**: Remove if not planning to use, or implement in portfolio analysis.

---

## Dead Code Branches

### Issue #13: Unreachable code after return
**File**: `trading_bot.py`
**Lines**: 280-285
**Severity**: LOW

```python
def execute_trade(self, action):
    if action == 'buy':
        result = self.buy_coin()
        return result  # ❌ Returns here

    # ❌ Following lines unreachable if dry_run is True
    if self.config.get('dry_run'):
        self.logger.info("Dry run mode")
        return {'success': False}
```

**Fix**: Reorder logic so all branches are reachable.

---

### Issue #14: Commented-out old implementation
**File**: `strategy.py`
**Lines**: 500-550
**Severity**: LOW

```python
# ❌ 50 lines of commented-out code from old strategy
# def old_signal_generation(...):
#     # Old binary voting system
#     # ...
```

**Fix**: Remove commented code (use git history if needed).

---

### Issue #15: Unused debug print statements
**File**: Multiple files
**Severity**: LOW

```python
# Scattered throughout codebase
# print(f"Debug: {variable}")  # ❌ Commented debug prints
# print("HERE")  # ❌
```

**Fix**: Remove all commented debug prints.

---

## Unused Configuration Options

### Issue #16: Unused config keys
**File**: `config.py`
**Lines**: Various
**Severity**: LOW

```python
TRADING_CONFIG = {
    'enable_trailing_stop': False,  # ❌ Never checked in code
    'trailing_stop_percent': 2.0,   # ❌ Never used
}
```

**Analysis**: These options were defined but never implemented.

**Fix**: Either implement the features or remove unused config keys.

---

## Unused Class Methods

### Issue #17: Unused portfolio methods
**File**: `portfolio_manager.py`
**Lines**: 100-150
**Severity**: MEDIUM

```python
class PortfolioManager:
    def calculate_portfolio_variance(self):
        """Never called - 20 lines"""
        # ❌ Advanced portfolio metrics not used

    def rebalance_portfolio(self):
        """Never called - 30 lines"""
        # ❌ Rebalancing logic not used
```

**Impact**: 50 lines of dead code

**Fix**: Remove if not planning multi-coin trading soon.

---

## Unused Constants

### Issue #18: Unused constants
**File**: `config.py`
**Lines**: Top of file
**Severity**: LOW

```python
# ❌ Constants defined but never referenced
MAX_API_RETRIES = 3  # Never used (no retry logic implemented)
API_TIMEOUT = 10     # Never passed to requests
```

**Fix**: Either use them or remove them.

```python
# If you want to use them:
response = requests.get(url, timeout=API_TIMEOUT)  # ✅
```

---

## Summary Statistics

| Category | Count | Lines | Fix Time |
|----------|-------|-------|----------|
| Unused imports | 4 | 4 | 5 min |
| Unused variables | 4 | 4 | 10 min |
| Unused functions | 4 | 53 | 15 min |
| Dead code branches | 2 | 55 | 20 min |
| Unused configs | 1 | 2 | 5 min |
| Unused class methods | 1 | 50 | 10 min |
| Unused constants | 1 | 2 | 5 min |
| **TOTAL** | **17** | **~170** | **70 min** |

---

## Impact Analysis

### Code Reduction
- **Current codebase**: ~1,400 lines (excluding comments)
- **Unused code**: ~170 lines
- **Potential reduction**: **12% smaller codebase**

### Benefits
- ✅ Easier to read and understand
- ✅ Faster grep/search results
- ✅ Less maintenance burden
- ✅ Clearer intent (no confusion about unused code)

### Risks
- ⚠️ Some "unused" code might be planned features
- ⚠️ Verify thoroughly before removing

---

## Recommended Action Plan

### Phase 1: Safe Removals (30 minutes)
1. ✅ Remove unused imports (5 min)
2. ✅ Remove commented-out code (10 min)
3. ✅ Remove debug print statements (5 min)
4. ✅ Remove truly unused variables (10 min)

**Risk**: Low - These are clearly unused

### Phase 2: Function Cleanup (30 minutes)
5. ✅ Remove validated dead functions (15 min)
6. ✅ Remove unreachable code branches (10 min)
7. ✅ Document functions to keep for future use (5 min)

**Risk**: Low-Medium - Verify no dynamic calls

### Phase 3: Architectural Cleanup (10 minutes)
8. ✅ Remove unused config options (5 min)
9. ✅ Remove unused constants (5 min)

**Risk**: Low

**Total time**: 70 minutes
**Code reduction**: 170 lines (12%)

---

## Verification Checklist

Before removing any code:

- [ ] Search entire codebase for function name (grep/IDE)
- [ ] Check for dynamic calls (getattr, eval, etc.)
- [ ] Verify not used in config files (string references)
- [ ] Check if it's part of planned features (ask team)
- [ ] Run all tests after removal
- [ ] Test GUI functionality
- [ ] Test CLI functionality

---

## Tool-Assisted Detection

You can automate detection with:

```bash
# Find unused imports (requires pylint)
pylint --disable=all --enable=unused-import *.py

# Find unused variables
pylint --disable=all --enable=unused-variable *.py

# Find dead code (requires vulture)
pip install vulture
vulture 005_money/ --min-confidence 80
```

---

## False Positives to Watch

Some code may appear unused but is actually needed:

1. **@property decorators**: May appear unused but accessed as attributes
2. **Magic methods**: `__str__`, `__repr__`, etc. - called implicitly
3. **Event handlers**: Connected via string names in GUI
4. **Config options**: May be used in string-based lookups
5. **Future features**: Deliberately added for upcoming functionality

Always verify manually before removing!

---

**End of Document**
