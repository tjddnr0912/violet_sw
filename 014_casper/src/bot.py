"""Casper Trading Bot - Main state machine and event loop.

Runs 24/7 in terminal. Cycles through states:
WAITING → PRE_MARKET → ORB_FORMING → SCANNING → POSITION_OPEN → DONE_TODAY
"""

import json
import logging
import math
import os
import signal
import time
from enum import Enum
from typing import Optional

from src.utils.config import load_env, load_strategy_params, get_kis_urls
from src.api.kis_auth import KISAuth
from src.api.kis_client import KISClient
from src.api.kis_order import KISOrder
from src.utils.logger import setup_logger
from src.utils import time_utils
from src.core.orb import calculate_orb, is_orb_too_wide, OpeningRange
from src.core.strategy import scan_for_signal, check_pullback, TradeSignal
from src.core.position import (
    Position, create_position, check_exit,
    move_stop_to_breakeven, close_position,
)
from src.core.risk import (
    check_vix_filter, determine_trend, CircuitBreaker, TrendState,
)
from src.data.market_data import (
    get_vix_close, get_qqq_trend_data, get_intraday_bars,
    get_avg_daily_range, get_current_price,
)
from src.data.trade_store import (
    load_trades, save_trade, trade_from_position, get_cumulative_stats,
)
from src.telegram.notifier import TelegramNotifier

logger = logging.getLogger("casper")


class BotState(Enum):
    WAITING = "WAITING"
    PRE_MARKET = "PRE_MARKET"
    ORB_FORMING = "ORB_FORMING"
    SCANNING = "SCANNING"
    POSITION_OPEN = "POSITION_OPEN"
    DONE_TODAY = "DONE_TODAY"


class CasperBot:
    """Main trading bot orchestrator."""

    def __init__(self):
        self.env = load_env()
        self.params = load_strategy_params()
        self.logger = setup_logger("casper", self.env["log_level"])

        # State
        self.state = BotState.WAITING
        self.today_date: Optional[str] = None
        self.trend: Optional[TrendState] = None
        self.orb: Optional[OpeningRange] = None
        self.signal: Optional[TradeSignal] = None
        self.position: Optional[Position] = None
        self.capital = 0.0
        self.trades_today = 0
        self._sell_retry_count = 0

        # Test mode (live but 1 share only)
        self.test_mode = self.env.get("test_mode", False)

        # Circuit breaker
        cb_params = self.params["risk"]
        self.circuit_breaker = CircuitBreaker(
            max_consecutive_losses=cb_params["circuit_breaker_losses"],
            max_weekly_loss_pct=cb_params["max_weekly_loss_pct"],
        )

        # Telegram (disabled)
        self.notifier = TelegramNotifier()

        # KIS API (order execution)
        self._init_kis()

        # Position state file for crash recovery
        self._position_state_file = os.path.join(
            os.path.dirname(__file__), "..", "data", "position_state.json"
        )
        self._done_today_logged = False

        # Load trade history
        self._init_from_history()

    def _init_kis(self):
        """Initialize KIS API clients for order execution."""
        key = self.env.get("kis_app_key", "")
        secret = self.env.get("kis_app_secret", "")
        account = self.env.get("kis_account_no", "")
        mode = self.env.get("trading_mode", "paper")
        urls = get_kis_urls(mode)

        if key and secret:
            auth = KISAuth(key, secret, urls["base"])
            client = KISClient(auth, account)
            self.kis_order = KISOrder(client, mode)
            self.kis_client = client
            logger.info(f"KIS API initialized ({mode})")
        else:
            self.kis_order = None
            self.kis_client = None
            logger.warning("KIS API not configured (no app_key/secret)")

    def _init_from_history(self):
        """Restore state from saved trades."""
        trades = load_trades()
        if trades:
            stats = get_cumulative_stats(trades)
            logger.info(f"History: {stats['total_trades']} trades, "
                        f"PnL ${stats['total_pnl']:+.2f}, WR {stats['win_rate']}%")
            self.circuit_breaker.load_from_trades(trades, time_utils.get_week_number())

        # Crash recovery: restore open position
        self._restore_position()

    def _save_position_state(self):
        """Persist open position to disk for crash recovery."""
        if self.position and self.position.is_open:
            state = {
                "symbol": self.position.symbol,
                "direction": self.position.direction,
                "entry_price": self.position.entry_price,
                "stop_loss": self.position.stop_loss,
                "take_profit": self.position.take_profit,
                "shares": self.position.shares,
                "risk_per_share": self.position.risk_per_share,
                "commission_rate": self.position.commission_rate,
                "entry_time": self.position.entry_time,
                "original_stop": self.position.original_stop,
                "be_stop_moved": self.position.be_stop_moved,
                "capital": self.capital,
            }
            try:
                os.makedirs(os.path.dirname(self._position_state_file), exist_ok=True)
                tmp = self._position_state_file + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp, self._position_state_file)
            except IOError as e:
                logger.error(f"Failed to save position state: {e}")
        else:
            self._clear_position_state()

    def _clear_position_state(self):
        """Remove position state file after close."""
        try:
            if os.path.exists(self._position_state_file):
                os.remove(self._position_state_file)
        except IOError:
            pass

    def _restore_position(self):
        """Restore open position from crash recovery file."""
        if not os.path.exists(self._position_state_file):
            return
        try:
            with open(self._position_state_file, "r") as f:
                state = json.load(f)
            logger.warning(f"CRASH RECOVERY: Found open position {state['symbol']} "
                          f"@ ${state['entry_price']:.2f}")
            # Reconstruct a minimal position for monitoring
            # We need a TradeSignal stub for position creation
            from src.core.orb import OpeningRange
            from src.core.fvg import FairValueGap
            from src.core.strategy import TradeSignal
            stub_orb = OpeningRange(high=0, low=0, range_size=0, date="")
            stub_fvg = FairValueGap(top=0, bottom=0, size=0, timestamp="")
            stub_signal = TradeSignal(
                symbol=state["symbol"], direction=state["direction"],
                entry_price=state["entry_price"], stop_loss=state["stop_loss"],
                take_profit=state["take_profit"], risk_per_share=state["risk_per_share"],
                rr_ratio=2.0, fvg=stub_fvg, orb=stub_orb, signal_time="",
            )
            self.position = Position(
                symbol=state["symbol"], direction=state["direction"],
                entry_price=state["entry_price"], stop_loss=state["stop_loss"],
                take_profit=state["take_profit"], shares=state["shares"],
                risk_per_share=state["risk_per_share"],
                commission_rate=state["commission_rate"],
                entry_time=state["entry_time"], signal=stub_signal,
            )
            self.position.original_stop = state.get("original_stop", state["stop_loss"])
            self.position.be_stop_moved = state.get("be_stop_moved", False)
            self.capital = state.get("capital", 0.0)
            self.state = BotState.POSITION_OPEN
            logger.warning("CRASH RECOVERY: Resuming position monitoring")
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"Failed to restore position state: {e}")
            self._clear_position_state()

    def run(self):
        """Main event loop. Runs until interrupted."""
        logger.info("=" * 50)
        logger.info("Casper Trading Bot Started")
        mode_str = self.env['trading_mode'].upper()
        if self.test_mode:
            mode_str += " (TEST: 1 share)"
        logger.info(f"Mode: {mode_str}")
        logger.info("=" * 50)
        self.notifier.notify_status("BOT STARTED", f"Mode: {self.env['trading_mode']}")

        # Handle SIGTERM for graceful daemon shutdown
        def _sigterm_handler(signum, frame):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, _sigterm_handler)

        try:
            while True:
                try:
                    self._tick()
                except (KeyboardInterrupt, SystemExit):
                    raise
                except Exception as e:
                    logger.exception(f"Unhandled error in tick: {e}")
                    self.notifier.notify_error(f"Tick error: {e}")
                    time.sleep(30)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped")
            self._save_position_state()
            self.notifier.notify_status("BOT STOPPED", "Graceful shutdown")

    def _tick(self):
        """Single iteration of the event loop."""
        now = time_utils.now_et()
        today = now.strftime("%Y-%m-%d")

        # Day change detection → reset daily state
        if today != self.today_date:
            self._reset_day(today)

        # State machine dispatch
        if self.state == BotState.WAITING:
            self._handle_waiting()
        elif self.state == BotState.PRE_MARKET:
            self._handle_pre_market()
        elif self.state == BotState.ORB_FORMING:
            self._handle_orb_forming()
        elif self.state == BotState.SCANNING:
            self._handle_scanning()
        elif self.state == BotState.POSITION_OPEN:
            self._handle_position_open()
        elif self.state == BotState.DONE_TODAY:
            self._handle_done_today()

    def _transition(self, new_state: BotState, reason: str = ""):
        """Transition to a new state with logging."""
        old = self.state
        self.state = new_state
        msg = f"STATE: {old.value} → {new_state.value}"
        if reason:
            msg += f" ({reason})"
        logger.info(msg)

    def _reset_day(self, today: str):
        """Reset daily state for a new trading day."""
        self.today_date = today
        self.trend = None
        self.orb = None
        self.signal = None
        self.position = None
        self.trades_today = 0
        self.state = BotState.WAITING
        self._done_today_logged = False
        self.circuit_breaker.reset_if_new_week(time_utils.get_week_number(), self.capital)
        logger.info(f"=== New Day: {today} ===")

    # ─── State Handlers ───

    def _handle_waiting(self):
        """Wait until pre-market window."""
        if not time_utils.is_weekday():
            time.sleep(300)  # 5min on weekends
            return

        if time_utils.is_pre_market():
            self._transition(BotState.PRE_MARKET)
            return

        if time_utils.is_orb_forming():
            self._transition(BotState.ORB_FORMING, "Joined during ORB")
            return

        time.sleep(60)

    def _handle_pre_market(self):
        """Run pre-market filters (Layer 1 & 2)."""
        # Circuit breaker check
        if self.circuit_breaker.is_active:
            self._transition(BotState.DONE_TODAY, "Circuit breaker active")
            self.notifier.notify_skip("Circuit breaker active this week")
            return

        # VIX filter
        vix = get_vix_close()
        if vix is None:
            logger.warning("VIX data unavailable, retrying in 5min")
            time.sleep(300)
            return

        filt = self.params["filters"]
        skip = check_vix_filter(vix, filt["vix_low"], filt["vix_high"])
        if skip:
            self._transition(BotState.DONE_TODAY, skip)
            self.notifier.notify_skip(skip)
            return

        # QQQ trend filter
        qqq_close, qqq_ma20 = get_qqq_trend_data(filt["ma_period"])
        if qqq_close is None:
            logger.warning("QQQ data unavailable, retrying in 5min")
            time.sleep(300)
            return

        syms = self.params["symbols"]
        self.trend = determine_trend(qqq_close, qqq_ma20, syms["bull"], syms["bear"])

        logger.info(f"Pre-market complete: {self.trend.direction.upper()} → {self.trend.symbol}")

        # Wait for ORB
        if time_utils.is_orb_forming():
            self._transition(BotState.ORB_FORMING)
        else:
            secs = time_utils.seconds_until(time_utils.dtime(9, 30))
            if secs > 0:
                logger.info(f"Waiting {secs/60:.0f}min for ORB window")
                time.sleep(min(secs, 60))

    def _handle_orb_forming(self):
        """Collect ORB data during 9:30-9:45."""
        if self.trend is None:
            # Missed pre-market, do quick check
            self._handle_pre_market()
            return

        if not time_utils.is_orb_forming():
            # ORB period ended, calculate ORB
            symbol = self.trend.symbol
            bars = get_intraday_bars(symbol, period="1d", interval="5m")
            if bars is None:
                self._transition(BotState.DONE_TODAY, "No intraday data")
                return

            self.orb = calculate_orb(bars)
            if self.orb is None:
                self._transition(BotState.DONE_TODAY, "ORB calculation failed")
                return

            # ORB too wide check
            adr = get_avg_daily_range(symbol)
            if adr and is_orb_too_wide(self.orb, adr, self.params["filters"]["orb_atr_max_ratio"]):
                self._transition(BotState.DONE_TODAY, "ORB too wide")
                self.notifier.notify_skip(f"ORB too wide ({self.orb.range_size:.2f})")
                return

            self._transition(BotState.SCANNING)
            return

        time.sleep(30)  # Check every 30s during ORB formation

    def _handle_scanning(self):
        """Scan for entry signals in 9:45-10:55 window."""
        if not time_utils.is_scan_window():
            self._transition(BotState.DONE_TODAY, "Scan window closed, no signal")
            self.notifier.notify_skip("No signal today")
            return

        if self.trend is None:
            self._transition(BotState.DONE_TODAY, "No trend data available")
            return

        symbol = self.trend.symbol
        bars = get_intraday_bars(symbol, period="1d", interval="5m")
        if bars is None:
            time.sleep(60)
            return

        # Filter to scan window only
        scan_bars = bars.between_time("09:45", "10:55")
        entry_params = self.params["entry"]

        self.signal = scan_for_signal(
            scan_bars, self.orb, symbol,
            rr_ratio=entry_params["rr_ratio"],
            min_risk=entry_params["min_risk_dollar"],
        )

        if self.signal is None:
            time.sleep(30)  # Check again in 30s
            return

        # Check pullback on latest bar
        if len(scan_bars) > 0:
            latest_bar = scan_bars.iloc[-1]
            if check_pullback(latest_bar, self.signal.fvg):
                self._execute_entry()
                return

        time.sleep(15)

    def _execute_entry(self):
        """Execute trade entry."""
        max_trades = self.params.get("risk", {}).get("max_trades_per_day", 1)
        if self.trades_today >= max_trades:
            self._transition(BotState.DONE_TODAY, f"Max trades reached ({max_trades})")
            return

        # Determine capital and shares
        price = self.signal.entry_price
        comm_rate = self.params["commission"]["rate_per_side"]

        # For paper mode, use yfinance price; for live, use KIS
        current = get_current_price(self.signal.symbol)
        if current:
            price = current  # Use real-time price if available

        # Calculate shares
        if self.test_mode:
            shares = 1
            logger.info("TEST MODE: shares fixed to 1")
        else:
            if self.capital <= 0:
                # Try to fetch real account balance
                if self.kis_client:
                    balance = self.kis_client.get_us_balance(self.signal.symbol)
                    if balance and balance.get("available_cash", 0) > 0:
                        self.capital = balance["available_cash"]
                        logger.info(f"Capital from KIS balance: ${self.capital:.2f}")
                if self.capital <= 0:
                    self.capital = 1500.0  # Default fallback
                    logger.warning(f"Using default capital: ${self.capital:.2f}")
            shares = int(self.capital / price) if price > 0 else 0
            # Apply position size cap
            risk_params = self.params.get("risk", {})
            max_shares = risk_params.get("max_shares", 200)
            max_pct = risk_params.get("max_position_pct", 1.0)
            max_by_pct = int(self.capital * max_pct / price) if price > 0 else 0
            shares = min(shares, max_shares, max_by_pct)
            if shares < 1:
                self._transition(BotState.DONE_TODAY, "Insufficient capital for 1 share")
                return

        entry_time = time_utils.now_et().strftime("%H:%M")
        self.position = create_position(self.signal, shares, comm_rate, entry_time)

        # Execute buy order via KIS API
        if self.kis_order:
            order_result = self.kis_order.buy_market(self.position.symbol, shares)
            if order_result is None:
                logger.error("BUY ORDER FAILED — aborting entry")
                self.position = None
                self._transition(BotState.DONE_TODAY, "Order execution failed")
                return
            order_no = order_result.get("order_no", "")
            logger.info(f"BUY ORDER OK: #{order_no}")

            # Query actual fill price and update position entry
            if self.kis_client and order_no:
                fill_price = self.kis_client.get_us_filled_price(
                    order_no, self.position.symbol
                )
                if fill_price and fill_price != self.position.entry_price:
                    old_price = self.position.entry_price
                    risk = fill_price - self.position.signal.stop_loss
                    if risk > 0:
                        self.position.entry_price = fill_price
                        self.position.risk_per_share = round(risk, 2)
                        self.position.take_profit = fill_price + risk * self.position.signal.rr_ratio
                        logger.info(f"Entry adjusted to fill: ${old_price:.2f} → ${fill_price:.2f}, "
                                   f"TP ${self.position.take_profit:.2f}")

        self.notifier.notify_entry(
            self.position.symbol, self.position.entry_price,
            self.position.shares, self.position.stop_loss,
            self.position.take_profit, self.position.risk_per_share,
        )
        self._save_position_state()
        self._transition(BotState.POSITION_OPEN)

    def _handle_position_open(self):
        """Monitor open position for exit conditions."""
        if self.position is None or not self.position.is_open:
            self._transition(BotState.DONE_TODAY)
            return

        # 11:00 BE move
        if time_utils.is_past_be_time():
            move_stop_to_breakeven(self.position)

        # 15:50 force close
        if time_utils.is_force_close_time():
            current = get_current_price(self.position.symbol)
            if current is None and self.kis_client:
                # Try KIS API price as fallback
                kis_price = self.kis_client.get_us_price(self.position.symbol)
                if kis_price and kis_price.get("price", 0) > 0:
                    current = kis_price["price"]
                    logger.info(f"Force close: using KIS price ${current:.2f}")
            if current is None:
                logger.warning("Force close: all price sources failed, using entry price")
                current = self.position.entry_price
            self._close_and_record(current, "time_force")
            return

        # Check current price
        current = get_current_price(self.position.symbol)
        if current is None:
            time.sleep(15)
            return

        # Simulate bar with current price as high/low/close approximation
        exit_reason = check_exit(self.position, current, current, current)
        if exit_reason:
            exit_price = (self.position.stop_loss if "stop" in exit_reason
                          else self.position.take_profit if exit_reason == "take_profit"
                          else current)
            self._close_and_record(exit_price, exit_reason)
            return

        time.sleep(15)

    def _close_and_record(self, price: float, reason: str):
        """Close position and save to trade store."""
        # Execute sell order via KIS API
        if self.kis_order:
            sell_result = self.kis_order.sell_market(
                self.position.symbol, self.position.shares
            )
            if sell_result is None:
                self._sell_retry_count += 1
                logger.error(
                    f"SELL ORDER FAILED — attempt #{self._sell_retry_count}, "
                    f"will retry next tick ({self.position.symbol} x{self.position.shares})"
                )
                return
            self._sell_retry_count = 0
            order_no = sell_result.get("order_no", "")
            logger.info(f"SELL ORDER OK: #{order_no}")

            # Query actual fill price from broker
            if self.kis_client and order_no:
                fill_price = self.kis_client.get_us_filled_price(
                    order_no, self.position.symbol
                )
                if fill_price:
                    logger.info(f"Using fill price ${fill_price:.2f} "
                               f"(was ${price:.2f})")
                    price = fill_price

        exit_time = time_utils.now_et().strftime("%H:%M")
        close_position(self.position, price, reason, exit_time)

        self.capital += self.position.net_pnl
        self.trades_today += 1

        # Save trade
        trade = trade_from_position(self.position)
        trade["capital_after"] = round(self.capital, 2)
        save_trade(trade)

        # Clear position state file
        self._clear_position_state()

        # Update circuit breaker
        self.circuit_breaker.record_trade(
            self.position.result, self.position.net_pnl, self.capital
        )

        # Notify
        self.notifier.notify_exit(
            self.position.symbol, self.position.entry_price,
            self.position.exit_price, reason,
            self.position.net_pnl, self.position.result,
        )

        self._transition(BotState.DONE_TODAY, f"{self.position.result} PnL=${self.position.net_pnl:+.2f}")

    def _handle_done_today(self):
        """Wait until next day."""
        if not self._done_today_logged:
            stats = get_cumulative_stats(load_trades())
            logger.info(f"Cumulative: {stats['total_trades']}T WR={stats['win_rate']}% "
                         f"PnL=${stats['total_pnl']:+.2f} PF={stats['profit_factor']}")
            self._done_today_logged = True

        # Sleep until midnight or long interval
        time.sleep(300)
