# Code Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CODE_AUDIT_2026-04-11.md에서 식별된 CRITICAL 3건, HIGH 2건, MEDIUM 3건, LOW 3건 총 11건의 실질 수정 항목을 TDD로 구현한다.

**Architecture:** 기존 모듈 구조를 유지하면서 각 파일의 해당 함수만 수정한다. 새 파일은 `scripts/update_holidays.py` 1개만 생성한다. 모든 수정은 기존 270개 테스트를 깨뜨리지 않아야 한다.

**Tech Stack:** Python 3.14, pytest, unittest.mock

**참조:** `docs/CODE_AUDIT_2026-04-11.md`

---

## File Map

| 파일 | 변경 | Task |
|------|------|------|
| `src/data/market_data.py` | 수정: `_yf_with_timeout`, 예외 처리 | 1, 9 |
| `src/bot.py` | 수정: `_execute_entry`, `_close_and_record`, `_reconcile_with_broker` | 2, 3, 5 |
| `src/core/risk.py` | 수정: `CircuitBreaker`에 `correct_last_trade` 추가 | 5 |
| `src/api/kis_order.py` | 수정: `buy_market`, `sell_market` 슬리피지 설정화 | 4 |
| `src/utils/config.py` | 수정: `load_strategy_params`에 검증 추가 | 6 |
| `config/strategy_params.json` | 수정: `order` 섹션 추가 | 4 |
| `src/utils/time_utils.py` | 수정: 공휴일 로딩 경고 | 10 |
| `run_casper.sh` | 수정: `.env` 로딩, `flock` | 7, 8 |
| `scripts/update_holidays.py` | 생성 | 11 |
| `tests/test_market_data.py` | 수정: timeout 테스트 추가 | 1, 9 |
| `tests/test_bot_states.py` | 수정: partial fill, capital, reconcile 테스트 | 2, 3, 5 |
| `tests/test_kis_order.py` | 수정: configurable slippage 테스트 | 4 |
| `tests/test_config.py` | 수정: validation 테스트 | 6 |
| `tests/test_risk.py` | 수정: correct_last_trade 테스트 | 5 |
| `tests/test_time_utils.py` | 수정: holiday warning 테스트 | 10 |

---

## Task 1: ThreadPoolExecutor 스레드 누수 수정 (CRITICAL #1)

**Files:**
- Modify: `src/data/market_data.py:40-44`
- Test: `tests/test_market_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_data.py — TestYfTimeout 클래스에 추가

class TestYfWithTimeout:
    @patch("src.data.market_data._YF_TIMEOUT", 0.1)
    def test_timeout_does_not_block(self):
        """Timeout should return quickly, not block waiting for thread."""
        import time

        def slow_func():
            time.sleep(10)
            return "never"

        from src.data.market_data import _yf_with_timeout
        from concurrent.futures import TimeoutError as FuturesTimeout
        start = time.time()
        with pytest.raises(FuturesTimeout):
            _yf_with_timeout(slow_func)
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Blocked for {elapsed:.1f}s (should be <2s)"

    def test_normal_call_returns_result(self):
        from src.data.market_data import _yf_with_timeout
        result = _yf_with_timeout(lambda: 42)
        assert result == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_market_data.py::TestYfWithTimeout -v`
Expected: `test_timeout_does_not_block` FAIL (blocks for ~10s or timeout)

- [ ] **Step 3: Implement the fix**

`src/data/market_data.py` — 모듈 레벨 executor + cancel 패턴:

```python
# 기존 (삭제):
# def _yf_with_timeout(func, *args, **kwargs):
#     with ThreadPoolExecutor(max_workers=1) as pool:
#         future = pool.submit(func, *args, **kwargs)
#         return future.result(timeout=_YF_TIMEOUT)

# 변경:
_yf_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yf")


def _yf_with_timeout(func, *args, **kwargs):
    """Run a yfinance call with a timeout to prevent indefinite blocking."""
    future = _yf_executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=_YF_TIMEOUT)
    except FuturesTimeout:
        future.cancel()
        raise
```

import 정리: `from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout` (기존과 동일)

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_market_data.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `python3 -m pytest tests/ -v --ignore=tests/test_remaining_fixes.py --ignore=tests/test_restore_verify.py --ignore=tests/test_strategy_review.py`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/data/market_data.py tests/test_market_data.py
git commit -m "Fix: ThreadPoolExecutor thread leak in yfinance timeout wrapper"
```

---

## Task 2: 부분 체결(Partial Fill) 감지 (CRITICAL #2)

**Files:**
- Modify: `src/bot.py:636-692` (`_close_and_record`)
- Test: `tests/test_bot_states.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bot_states.py — TestCloseAndRecord 클래스에 추가

class TestPartialFill:
    def test_partial_fill_retries_sell(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:50")
        bot.capital = 1000.0
        bot.trades_today = 0

        mock_order = MagicMock()
        mock_order.sell_market.return_value = {"order_no": "S001"}
        bot.kis_order = mock_order

        mock_client = MagicMock()
        # First call: 3 shares remaining after partial fill
        # Second call after retry: 0 shares
        mock_client.get_us_holdings.side_effect = [
            [{"symbol": "TQQQ", "qty": 3, "avg_price": 54.0}],
            [],
        ]
        mock_client.get_us_filled_price.return_value = None
        mock_client.get_us_today_executions.return_value = []
        bot.kis_client = mock_client

        with patch("src.bot.load_trades", return_value=[]):
            bot._close_and_record(55.0, "take_profit")

        # sell_market should be called twice: initial + retry for remaining 3
        assert mock_order.sell_market.call_count == 2
        retry_call = mock_order.sell_market.call_args_list[1]
        assert retry_call[0] == ("TQQQ", 3)

    def test_full_fill_no_retry(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:50")
        bot.capital = 1000.0

        mock_order = MagicMock()
        mock_order.sell_market.return_value = {"order_no": "S002"}
        bot.kis_order = mock_order

        mock_client = MagicMock()
        mock_client.get_us_holdings.return_value = []  # No remaining
        mock_client.get_us_filled_price.return_value = None
        mock_client.get_us_today_executions.return_value = []
        bot.kis_client = mock_client

        with patch("src.bot.load_trades", return_value=[]):
            bot._close_and_record(55.0, "take_profit")

        assert mock_order.sell_market.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bot_states.py::TestPartialFill -v`
Expected: FAIL (`sell_market` called only once)

- [ ] **Step 3: Implement the fix**

`src/bot.py` — `_close_and_record` 메서드 내부, `logger.info(f"SELL ORDER OK: #{order_no}")` 이후에 추가:

```python
            # Check for partial fill — retry if shares remain
            if self.kis_client:
                time.sleep(2)  # Allow settlement
                holdings = self.kis_client.get_us_holdings()
                if holdings is not None:
                    remaining = next(
                        (h for h in holdings if h["symbol"] == self.position.symbol),
                        None,
                    )
                    if remaining and remaining["qty"] > 0:
                        logger.warning(
                            f"PARTIAL FILL: {remaining['qty']} shares remaining — "
                            f"retrying sell"
                        )
                        self.kis_order.sell_market(
                            self.position.symbol, remaining["qty"]
                        )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_bot_states.py::TestPartialFill -v`
Expected: ALL PASS

- [ ] **Step 5: Full regression**

Run: `python3 -m pytest tests/ -v --ignore=tests/test_remaining_fixes.py --ignore=tests/test_restore_verify.py --ignore=tests/test_strategy_review.py`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/bot.py tests/test_bot_states.py
git commit -m "Fix: detect partial fill and retry sell for remaining shares"
```

---

## Task 3: 하드코딩 폴백 자본금 제거 (CRITICAL #3)

**Files:**
- Modify: `src/bot.py:498-516` (`_execute_entry`)
- Test: `tests/test_bot_states.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bot_states.py — TestExecuteEntry 클래스에 추가

class TestCapitalFallback:
    def test_capital_zero_skips_trade(self, tmp_path):
        """When capital sync fails, bot should skip — not use $1500 default."""
        bot = _make_bot(tmp_path=tmp_path)
        bot.signal = _make_signal()
        bot.capital = 0.0
        bot.test_mode = False
        bot.trades_today = 0
        bot.kis_client = MagicMock()
        bot.kis_client.get_us_balance.return_value = None  # API fails

        bot._execute_entry()

        assert bot.state == BotState.DONE_TODAY
        assert bot.position is None

    def test_capital_positive_proceeds(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.signal = _make_signal()
        bot.capital = 5000.0
        bot.test_mode = False
        bot.trades_today = 0
        bot.kis_order = None
        bot.kis_client = None

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        assert bot.position is not None
        assert bot.state == BotState.POSITION_OPEN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bot_states.py::TestCapitalFallback -v`
Expected: `test_capital_zero_skips_trade` FAIL (bot uses $1500 fallback)

- [ ] **Step 3: Implement the fix**

`src/bot.py` — `_execute_entry` 내부, 기존 코드:

```python
# 기존 (삭제):
#     if self.capital <= 0:
#         self._sync_capital()
#         if self.capital <= 0:
#             self.capital = 1500.0
#             logger.warning(f"Using default capital: ${self.capital:.2f}")

# 변경:
            if self.capital <= 0:
                self._sync_capital()
                if self.capital <= 0:
                    self._transition(
                        BotState.DONE_TODAY,
                        "Capital sync failed — skipping today"
                    )
                    return
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_bot_states.py::TestCapitalFallback -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/bot.py tests/test_bot_states.py
git commit -m "Fix: skip trade when capital sync fails instead of $1500 fallback"
```

---

## Task 4: 슬리피지 버퍼 설정화 (HIGH #4)

**Files:**
- Modify: `config/strategy_params.json`
- Modify: `src/api/kis_order.py:29-78`
- Test: `tests/test_kis_order.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_kis_order.py — TestSlippageConfig 클래스 추가

class TestSlippageConfig:
    def test_custom_slippage_buy(self, mock_client):
        order = KISOrder(mock_client, "live", buy_slippage=0.02, sell_slippage=0.02)
        with patch.object(KISClient, "get_us_price", return_value={"price": 100.0}):
            with patch.object(KISClient, "_request", return_value={"output": {"ODNO": "X"}, "rt_cd": "0"}) as mock_req:
                order.buy_market("TQQQ", 1)
                _, kwargs = mock_req.call_args
                body = kwargs["json_body"]
                # 100 * 1.02 = 102.0
                assert float(body["OVRS_ORD_UNPR"]) == 102.0

    def test_custom_slippage_sell(self, mock_client):
        order = KISOrder(mock_client, "live", buy_slippage=0.02, sell_slippage=0.02)
        with patch.object(KISClient, "get_us_price", return_value={"price": 100.0}):
            with patch.object(KISClient, "_request", return_value={"output": {"ODNO": "X"}, "rt_cd": "0"}) as mock_req:
                order.sell_market("TQQQ", 1)
                _, kwargs = mock_req.call_args
                body = kwargs["json_body"]
                # 100 * 0.98 = 98.0
                assert float(body["OVRS_ORD_UNPR"]) == 98.0

    def test_default_slippage_unchanged(self, mock_client):
        """Default 0.5% backwards compatibility."""
        order = KISOrder(mock_client, "live")
        with patch.object(KISClient, "get_us_price", return_value={"price": 100.0}):
            with patch.object(KISClient, "_request", return_value={"output": {"ODNO": "X"}, "rt_cd": "0"}) as mock_req:
                order.buy_market("TQQQ", 1)
                _, kwargs = mock_req.call_args
                body = kwargs["json_body"]
                assert float(body["OVRS_ORD_UNPR"]) == 100.5  # 100 * 1.005
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_kis_order.py::TestSlippageConfig -v`
Expected: FAIL (`__init__` doesn't accept slippage params)

- [ ] **Step 3: Implement the fix**

`src/api/kis_order.py`:

```python
class KISOrder:
    def __init__(self, client: KISClient, trading_mode: str = "paper",
                 buy_slippage: float = 0.005, sell_slippage: float = 0.005):
        self.client = client
        self.trading_mode = trading_mode
        self.buy_slippage = buy_slippage
        self.sell_slippage = sell_slippage
        # ... tr_id 설정은 동일
```

`buy_market`:
```python
        limit_price = round(price * (1 + self.buy_slippage), 2)
```

`sell_market`:
```python
        limit_price = round(price * (1 - self.sell_slippage), 2)
```

`config/strategy_params.json`에 추가:
```json
    "order": {
        "buy_slippage_pct": 0.01,
        "sell_slippage_pct": 0.01
    }
```

`src/bot.py` — `_init_kis`에서 params 전달:
```python
            order_params = self.params.get("order", {})
            self.kis_order = KISOrder(
                client, mode,
                buy_slippage=order_params.get("buy_slippage_pct", 0.005),
                sell_slippage=order_params.get("sell_slippage_pct", 0.005),
            )
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_kis_order.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/kis_order.py src/bot.py config/strategy_params.json tests/test_kis_order.py
git commit -m "Update: configurable slippage buffer for buy/sell orders"
```

---

## Task 5: CB reconcile 보정 (HIGH #6)

**Files:**
- Modify: `src/core/risk.py` (`CircuitBreaker.correct_last_trade`)
- Modify: `src/bot.py:694-729` (`_reconcile_with_broker`)
- Test: `tests/test_risk.py`, `tests/test_bot_states.py`

- [ ] **Step 1: Write the failing test for CircuitBreaker.correct_last_trade**

```python
# tests/test_risk.py — TestCircuitBreaker 클래스에 추가

class TestCorrectLastTrade:
    def test_corrects_weekly_loss(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=5.0)
        cb.reset_if_new_week(1, 1000.0)
        # Record a loss of $30 (estimated)
        cb.record_trade("LOSS", -30.0, 970.0)
        assert cb._weekly_loss == 30.0
        assert cb._consecutive_losses == 1

        # Correct: actual loss was $20
        cb.correct_last_trade("LOSS", -30.0, -20.0)
        assert cb._weekly_loss == 20.0
        assert cb._consecutive_losses == 1  # Still a loss

    def test_correct_loss_to_win(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=5.0)
        cb.reset_if_new_week(1, 1000.0)
        cb.record_trade("LOSS", -10.0, 990.0)
        assert cb._consecutive_losses == 1

        # Correct: actually was a win
        cb.correct_last_trade("LOSS", -10.0, 5.0)
        assert cb._weekly_loss == 0.0
        assert cb._consecutive_losses == 0

    def test_no_correction_needed(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=5.0)
        cb.reset_if_new_week(1, 1000.0)
        cb.record_trade("WIN", 20.0, 1020.0)

        # Correct with same-direction result
        cb.correct_last_trade("WIN", 20.0, 25.0)
        assert cb._consecutive_losses == 0

    def test_deactivates_cb_if_correction_removes_trigger(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=3.0)
        cb.reset_if_new_week(1, 1000.0)
        cb.record_trade("LOSS", -10.0, 990.0)
        cb.record_trade("LOSS", -10.0, 980.0)
        cb.record_trade("LOSS", -11.0, 969.0)
        assert cb.is_active  # 3 consecutive + 3.1% weekly

        # Correct last trade: actually was a win
        cb.correct_last_trade("LOSS", -11.0, 5.0)
        assert cb._consecutive_losses == 0
        assert not cb.is_active
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_risk.py::TestCorrectLastTrade -v`
Expected: FAIL (`correct_last_trade` not found)

- [ ] **Step 3: Implement CircuitBreaker.correct_last_trade**

`src/core/risk.py` — `CircuitBreaker` 클래스에 메서드 추가:

```python
    def correct_last_trade(self, old_result: str, old_pnl: float, actual_pnl: float) -> None:
        """Correct the last trade's impact on CB state after broker reconciliation.

        Args:
            old_result: Original result ("WIN", "LOSS", "BE").
            old_pnl: Originally recorded net PnL.
            actual_pnl: Actual net PnL from broker.
        """
        actual_result = "LOSS" if actual_pnl < -0.01 else ("WIN" if actual_pnl > 0.01 else "BE")

        # Reverse old impact
        if old_result == "LOSS":
            self._weekly_loss -= abs(old_pnl)
            if self._weekly_loss < 0:
                self._weekly_loss = 0.0
            self._consecutive_losses = max(0, self._consecutive_losses - 1)

        # Apply actual impact
        if actual_result == "LOSS":
            self._weekly_loss += abs(actual_pnl)
            self._consecutive_losses += 1
        # WIN/BE: consecutive losses stays reduced (already decremented above)

        # Re-evaluate CB activation
        triggered = False
        if self._consecutive_losses >= self.max_consecutive_losses:
            triggered = True
        base = self._week_start_capital if self._week_start_capital > 0 else 1.0
        if (self._weekly_loss / base) * 100 >= self.max_weekly_loss_pct:
            triggered = True
        self._active = triggered

        if not triggered and old_result != actual_result:
            logger.info(
                f"CB CORRECTED: {old_result} PnL=${old_pnl:+.2f} → "
                f"{actual_result} PnL=${actual_pnl:+.2f}"
            )
```

- [ ] **Step 4: Run test to verify pass**

Run: `python3 -m pytest tests/test_risk.py::TestCorrectLastTrade -v`
Expected: ALL PASS

- [ ] **Step 5: Wire into _reconcile_with_broker**

`src/bot.py` — `_reconcile_with_broker` 메서드 내부, `update_last_trade(updates)` 이후에 추가:

```python
            # Correct circuit breaker with actual PnL
            if broker_gross_pnl is not None and self.position:
                actual_pnl = broker_gross_pnl - self.position.commission
                old_pnl = self.position.net_pnl
                if abs(actual_pnl - old_pnl) > 0.01:
                    self.circuit_breaker.correct_last_trade(
                        self.position.result, old_pnl, actual_pnl
                    )
```

- [ ] **Step 6: Run full test suite**

Run: `python3 -m pytest tests/ -v --ignore=tests/test_remaining_fixes.py --ignore=tests/test_restore_verify.py --ignore=tests/test_strategy_review.py`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/core/risk.py src/bot.py tests/test_risk.py
git commit -m "Fix: reconcile broker fill price into circuit breaker state"
```

---

## Task 6: 설정 파일 스키마 검증 (MEDIUM #9)

**Files:**
- Modify: `src/utils/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py — TestValidation 클래스 추가

class TestParamsValidation:
    def test_valid_config_passes(self):
        from src.utils.config import _validate_params
        params = {
            "symbols": {"bull": "TQQQ", "bear": "SQQQ", "trend_filter": "QQQ"},
            "entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
            "filters": {"vix_low": 12.0, "vix_high": 30.0, "ma_period": 20, "orb_atr_max_ratio": 1.5},
            "risk": {"max_shares": 200, "max_trades_per_day": 1, "circuit_breaker_losses": 3,
                     "max_weekly_loss_pct": 3.0, "max_position_pct": 1.0},
            "commission": {"rate_per_side": 0.0009},
        }
        _validate_params(params)  # Should not raise

    def test_negative_rr_ratio_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": -1.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 12, "vix_high": 30},
                  "risk": {"max_shares": 200, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="rr_ratio"):
            _validate_params(params)

    def test_vix_range_inverted_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 50, "vix_high": 10},
                  "risk": {"max_shares": 200, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="vix"):
            _validate_params(params)

    def test_zero_max_shares_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 12, "vix_high": 30},
                  "risk": {"max_shares": 0, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="max_shares"):
            _validate_params(params)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py::TestParamsValidation -v`
Expected: FAIL (`_validate_params` not found)

- [ ] **Step 3: Implement the fix**

`src/utils/config.py` — 함수 추가 + `load_strategy_params`에서 호출:

```python
def _validate_params(params: dict) -> None:
    """Validate strategy parameters at startup."""
    entry = params.get("entry", {})
    filters = params.get("filters", {})
    risk = params.get("risk", {})

    if entry.get("rr_ratio", 0) <= 0:
        raise ValueError(f"rr_ratio must be positive, got {entry.get('rr_ratio')}")
    if filters.get("vix_low", 0) >= filters.get("vix_high", 0):
        raise ValueError(
            f"vix_low ({filters.get('vix_low')}) must be < vix_high ({filters.get('vix_high')})"
        )
    if risk.get("max_shares", 0) <= 0:
        raise ValueError(f"max_shares must be positive, got {risk.get('max_shares')}")
    if risk.get("max_trades_per_day", 0) <= 0:
        raise ValueError(f"max_trades_per_day must be positive")
```

`load_strategy_params` 마지막에 호출 추가:

```python
def load_strategy_params() -> dict:
    # ... 기존 코드 ...
    _validate_params(_config_cache)
    return _config_cache
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/config.py tests/test_config.py
git commit -m "Add: strategy params validation at startup"
```

---

## Task 7: run_casper.sh .env 안전 로딩 (MEDIUM #7)

**Files:**
- Modify: `run_casper.sh:29-38`

- [ ] **Step 1: Implement the fix**

`run_casper.sh` — `load_env` 함수 교체:

```bash
# 기존 (삭제):
# load_env() {
#     if [ -f ".env" ]; then
#         set -a
#         source .env
#         set +a
#     else ...

# 변경:
load_env() {
    if [ -f ".env" ]; then
        while IFS='=' read -r key value; do
            # Skip comments and empty lines
            [[ "$key" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$key" ]] && continue
            # Trim whitespace
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | xargs)
            # Remove surrounding quotes from value
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"
            export "$key=$value"
        done < .env
    else
        echo -e "${RED}[ERROR]${NC} .env 파일이 없습니다. .env.example을 참고하세요."
        exit 1
    fi
}
```

- [ ] **Step 2: Verify .env loading works**

Run: `cd /Users/seongwookjang/project/git/violet_sw/014_casper && bash -c 'source run_casper.sh; load_env; echo $TRADING_MODE'`
Expected: .env의 TRADING_MODE 값 출력

- [ ] **Step 3: Commit**

```bash
git add run_casper.sh
git commit -m "Fix: safe .env loading without shell command injection"
```

---

## Task 8: PID 파일 경쟁 조건 수정 (MEDIUM #11)

**Files:**
- Modify: `run_casper.sh:72-85`

- [ ] **Step 1: Implement the fix**

`run_casper.sh` — `check_running` 함수 뒤에 `lock_instance` 함수 추가:

```bash
# 파일 잠금 기반 중복 실행 방지
LOCK_FILE="$SCRIPT_DIR/.casper.lock"

lock_instance() {
    exec 200>"$LOCK_FILE"
    if ! flock -n 200; then
        echo -e "${YELLOW}[WARN]${NC} Casper Bot이 이미 실행 중입니다"
        echo "       종료하려면: $0 stop"
        exit 1
    fi
}
```

`start_bot` 함수에서 `check_running` 호출을 `lock_instance`로 교체:

```bash
start_bot() {
    print_logo
    load_env
    activate_venv
    check_deps
    check_api_keys
    lock_instance       # check_running 대신 flock 사용
    # ... 나머지 동일
```

`start_daemon`도 동일하게 `lock_instance` 사용.

기존 `check_running`은 `stop_bot`에서 PID 확인용으로 유지.

- [ ] **Step 2: Verify lock works**

Run: `flock -n /Users/seongwookjang/project/git/violet_sw/014_casper/.casper.lock echo "lock OK"`
Expected: "lock OK" 출력 (잠금이 없을 때)

- [ ] **Step 3: Commit**

```bash
git add run_casper.sh
git commit -m "Fix: use flock for reliable duplicate instance prevention"
```

---

## Task 9: 예외 처리 중복 수정 (LOW #12)

**Files:**
- Modify: `src/data/market_data.py:113-127`
- Test: `tests/test_market_data.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_market_data.py — TestCacheRecovery 클래스에 추가

class TestCacheRecovery:
    @patch("src.data.market_data._fetch_vix", side_effect=Exception("generic error"))
    def test_generic_exception_returns_none(self, mock_fetch):
        assert get_vix_close() is None

    @patch("src.data.market_data._fetch_vix")
    def test_sqlite_error_triggers_cache_reset(self, mock_fetch):
        """SQLite error should trigger cache reset and retry."""
        class FakeSQLiteError(Exception):
            pass
        FakeSQLiteError.__name__ = "OperationalError"
        mock_fetch.side_effect = [FakeSQLiteError("unable to open database"), 18.5]

        with patch("src.data.market_data._reset_yf_cache", return_value=True):
            result = get_vix_close()
        assert result == 18.5
```

- [ ] **Step 2: Implement the fix**

`src/data/market_data.py` — `_yf_fetch_with_cache_recovery`:

```python
# 기존 (삭제):
#     except (FuturesTimeout, Exception) as e:

# 변경:
    except Exception as e:
```

- [ ] **Step 3: Run tests to verify pass**

Run: `python3 -m pytest tests/test_market_data.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/data/market_data.py tests/test_market_data.py
git commit -m "Fix: remove redundant FuturesTimeout in exception handling"
```

---

## Task 10: 공휴일 파일 누락 경고 (LOW #14)

**Files:**
- Modify: `src/utils/time_utils.py:21-30`
- Test: `tests/test_time_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_time_utils.py — TestHolidays 클래스에 추가

class TestHolidayWarning:
    def test_missing_file_logs_warning(self, tmp_path):
        import src.utils.time_utils as tu
        old_file = tu._HOLIDAYS_FILE
        old_holidays = tu._us_holidays
        try:
            tu._HOLIDAYS_FILE = str(tmp_path / "nonexistent.json")
            tu._us_holidays = set()  # Force reload
            with patch("src.utils.time_utils.logger") as mock_logger:
                tu._load_holidays()
                mock_logger.warning.assert_called_once()
                assert "holiday" in mock_logger.warning.call_args[0][0].lower()
        finally:
            tu._HOLIDAYS_FILE = old_file
            tu._us_holidays = old_holidays

    def test_valid_file_no_warning(self, tmp_path):
        import src.utils.time_utils as tu
        holidays_file = tmp_path / "holidays.json"
        holidays_file.write_text('{"2026": ["2026-01-01"]}')

        old_file = tu._HOLIDAYS_FILE
        old_holidays = tu._us_holidays
        try:
            tu._HOLIDAYS_FILE = str(holidays_file)
            tu._us_holidays = set()
            with patch("src.utils.time_utils.logger") as mock_logger:
                result = tu._load_holidays()
                mock_logger.warning.assert_not_called()
                assert "2026-01-01" in result
        finally:
            tu._HOLIDAYS_FILE = old_file
            tu._us_holidays = old_holidays
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_time_utils.py::TestHolidayWarning -v`
Expected: `test_missing_file_logs_warning` FAIL (no warning called)

- [ ] **Step 3: Implement the fix**

`src/utils/time_utils.py` — `_load_holidays` 수정:

```python
def _load_holidays() -> set:
    """Load US holiday dates from config file."""
    global _us_holidays
    if _us_holidays:
        return _us_holidays
    try:
        with open(_HOLIDAYS_FILE, "r") as f:
            data = json.load(f)
        for year_key, dates in data.items():
            if year_key.startswith("_"):
                continue
            for d in dates:
                _us_holidays.add(d)
    except FileNotFoundError:
        logger.warning(f"Holiday file not found: {_HOLIDAYS_FILE} — weekday-only fallback")
    except json.JSONDecodeError as e:
        logger.warning(f"Holiday file parse error: {e} — weekday-only fallback")
    return _us_holidays
```

import 확인: `logging`은 이미 time_utils에서 사용하지 않으므로 추가 필요:

```python
import logging
logger = logging.getLogger("casper")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/test_time_utils.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/utils/time_utils.py tests/test_time_utils.py
git commit -m "Add: warning log when holiday file is missing or invalid"
```

---

## Task 11: 공휴일 갱신 스크립트 (LOW #15)

**Files:**
- Create: `scripts/update_holidays.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Update US market holidays in config/us_holidays.json.

Fetches NYSE holiday calendar using exchange_calendars library.
Run once per year (e.g., at the start of each new year).

Usage:
    python scripts/update_holidays.py          # Add next year
    python scripts/update_holidays.py 2028     # Add specific year
    python scripts/update_holidays.py 2028 2029  # Add multiple years

Requirements (script only, not needed for bot runtime):
    pip install exchange_calendars pandas
"""

import json
import os
import sys

import exchange_calendars as xcals
import pandas as pd


def get_holidays(year: int) -> list:
    """Get NYSE holiday dates for a given year."""
    cal = xcals.get_calendar("XNYS")
    all_weekdays = pd.bdate_range(f"{year}-01-01", f"{year}-12-31")
    sessions = cal.sessions_in_range(f"{year}-01-01", f"{year}-12-31")
    holidays = sorted(
        set(all_weekdays.strftime("%Y-%m-%d")) - set(sessions.strftime("%Y-%m-%d"))
    )
    return holidays


def main():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "us_holidays.json"
    )

    # Parse years from args, default to next year
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    else:
        years = [pd.Timestamp.now().year + 1]

    # Load existing
    with open(config_path) as f:
        data = json.load(f)

    for year in years:
        holidays = get_holidays(year)
        data[str(year)] = holidays
        print(f"{year}: {len(holidays)} holidays added")

    # Write back
    with open(config_path, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Updated: {config_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script runs (dry check)**

Run: `python3 -c "import exchange_calendars" 2>&1 || echo "SKIP: exchange_calendars not installed (optional dependency)"`

- [ ] **Step 3: Commit**

```bash
git add scripts/update_holidays.py
git commit -m "Add: holiday update script using exchange_calendars (yearly maintenance)"
```

---

## Task 12: 최종 회귀 테스트 + 정리

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v --ignore=tests/test_remaining_fixes.py --ignore=tests/test_restore_verify.py --ignore=tests/test_strategy_review.py`
Expected: ALL PASS, 기존 테스트 + 새 테스트 모두 통과

- [ ] **Step 2: Verify test count increased**

기존 ~270개 → 새 테스트 추가로 증가 확인

- [ ] **Step 3: Update audit report**

`docs/CODE_AUDIT_2026-04-11.md` 요약 테이블에 수정 완료 상태 반영

- [ ] **Step 4: Final commit**

```bash
git add docs/CODE_AUDIT_2026-04-11.md
git commit -m "Update: mark audit items as fixed in CODE_AUDIT report"
```
