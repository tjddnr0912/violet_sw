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
    get_avg_daily_range, get_current_price, set_kis_client,
)
from src.data.trade_store import (
    load_trades, save_trade, trade_from_position, update_last_trade,
    get_cumulative_stats,
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
        self.trend: Optional[TrendState] = None  # informational only in dual_scan
        # Multi-symbol ORB / signal tracking. In dual_scan mode both BULL and
        # BEAR are scanned in parallel; in single-trend mode only one symbol
        # is keyed.
        self.orbs: dict = {}
        self.signals: dict = {}
        self.orb: Optional[OpeningRange] = None  # winning leg (set on entry)
        self.signal: Optional[TradeSignal] = None
        self.position: Optional[Position] = None
        self.capital = 0.0
        self.trades_today = 0
        self._sell_retry_count = 0
        self._pending_buy_order_no: Optional[str] = None

        # Test mode (live but 1 share only)
        self.test_mode = self.env.get("test_mode", False)

        # Circuit breaker
        cb_params = self.params["risk"]
        self.circuit_breaker = CircuitBreaker(
            max_consecutive_losses=cb_params["circuit_breaker_losses"],
            max_weekly_loss_pct=cb_params["max_weekly_loss_pct"],
        )

        # Telegram — env-driven; absent keys disable alerts silently
        self.notifier = TelegramNotifier(
            bot_token=self.env.get("telegram_bot_token", ""),
            chat_id=self.env.get("telegram_chat_id", ""),
        )

        # KIS API (order execution)
        self._init_kis()

        # Position state file for crash recovery
        self._position_state_file = os.path.join(
            os.path.dirname(__file__), "..", "data", "position_state.json"
        )
        self._done_today_logged = False
        # Re-sync capital once when entering pre-market, to catch mid-day
        # USD deposits/FX conversions made after _check_new_day's sync ran
        # (_check_new_day fires at ET 00:00 ≈ KST 13:00, which is before
        # the afternoon window when a Korean user typically moves money).
        self._premarket_synced_today = False
        # Telegram notification dedup flags (reset per day)
        self._notified_pre_market = False
        self._notified_orb = False
        self._notified_signal = False

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
            order_params = self.params.get("order", {})
            self.kis_order = KISOrder(
                client, mode,
                buy_slippage=order_params.get("buy_slippage_pct", 0.005),
                sell_slippage=order_params.get("sell_slippage_pct", 0.005),
            )
            self.kis_client = client
            set_kis_client(client)  # Inject into market_data module
            logger.info(f"KIS API initialized ({mode})")

            # Cold-start warm-up. KIS returns HTTP 500 with empty body
            # (rt_cd:"1", msg:"") on calls issued within ~15-60s of a fresh
            # process/token handshake. Without a warm-up guard, the first
            # _sync_capital() call fails and self.capital stays at 0.0 —
            # which disables position sizing for the entire day. The
            # warm_up() helper polls a cheap quote every 10s until KIS
            # responds 200 (no per-call internal retry, to avoid wasting
            # the polling budget on rate-limit-adjacent paths).
            client.warm_up(max_secs=90, poll_interval=10)
        else:
            self.kis_order = None
            self.kis_client = None
            set_kis_client(None)
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
                "rr_ratio": self.position.signal.rr_ratio,
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
        """Restore open position from crash recovery file.

        Verifies actual broker holdings before restoring.
        If no matching holding exists, discards the stale state file.
        """
        if not os.path.exists(self._position_state_file):
            return
        try:
            with open(self._position_state_file, "r") as f:
                state = json.load(f)
            symbol = state["symbol"]
            shares = state["shares"]
            logger.warning(f"CRASH RECOVERY: Found state file for {symbol} x{shares} "
                          f"@ ${state['entry_price']:.2f}")

            # Verify actual holdings at broker
            if self.kis_client:
                holdings = self.kis_client.get_us_holdings()
                if holdings is not None:
                    held = next((h for h in holdings if h["symbol"] == symbol), None)
                    if held is None or held["qty"] <= 0:
                        logger.warning(
                            f"CRASH RECOVERY: {symbol} NOT held at broker — "
                            f"discarding stale position state"
                        )
                        self._clear_position_state()
                        return
                    # Adjust shares to actual holding if different
                    if held["qty"] != shares:
                        logger.warning(
                            f"CRASH RECOVERY: Broker has {held['qty']} shares "
                            f"(state says {shares}) — using broker qty"
                        )
                        state["shares"] = held["qty"]
                    logger.info(f"CRASH RECOVERY: Broker confirms {symbol} x{held['qty']}")
                else:
                    logger.warning("CRASH RECOVERY: Cannot verify holdings (API unavailable), "
                                  "proceeding with state file")

            # Reconstruct position
            from src.core.orb import OpeningRange
            from src.core.fvg import FairValueGap
            from src.core.strategy import TradeSignal
            stub_orb = OpeningRange(high=0, low=0, range_size=0, date="")
            stub_fvg = FairValueGap(top=0, bottom=0, size=0, timestamp="")
            # rr_ratio: prefer saved value (the R:R the trade was opened with);
            # fall back to current config for state files written before rr_ratio
            # was persisted.
            saved_rr = state.get("rr_ratio")
            if saved_rr is None:
                saved_rr = self.params.get("entry", {}).get("rr_ratio", 2.0)
            stub_signal = TradeSignal(
                symbol=state["symbol"], direction=state["direction"],
                entry_price=state["entry_price"], stop_loss=state["stop_loss"],
                take_profit=state["take_profit"], risk_per_share=state["risk_per_share"],
                rr_ratio=saved_rr, fvg=stub_fvg, orb=stub_orb, signal_time="",
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
        scan_mode = "DUAL_SCAN (TQQQ+SQQQ)" if self.params.get("mode", {}).get("dual_scan", False) else "TREND (QQQ MA20)"
        fvg_mode = "STRICT (body straddles ORB + FVG-ORB intersect)" if self.params.get("entry", {}).get("strict_fvg", False) else "baseline"
        rr = self.params.get("entry", {}).get("rr_ratio", 2.0)
        logger.info(f"Scan: {scan_mode}")
        logger.info(f"FVG : {fvg_mode}")
        logger.info(f"R:R : 1:{rr}")
        logger.info("=" * 50)
        # Sync capital from KIS BEFORE the start banner so the Telegram
        # message reflects the actual orderable USD instead of the
        # __init__ default ($0.00). _check_new_day will sync again on the
        # first tick — that second sync is a no-op when nothing changed.
        self._sync_capital()
        # Build history snapshot for the start banner
        from src.data.trade_store import get_cumulative_stats, load_trades
        try:
            stats = get_cumulative_stats(load_trades())
            history = {
                "count": stats.get("total_trades", 0),
                "win_rate": stats.get("win_rate", 0),
                "pnl": stats.get("total_pnl", 0),
            }
        except Exception:
            history = {"count": 0, "win_rate": 0, "pnl": 0}
        strategy_info = {
            "dual_scan": self.params.get("mode", {}).get("dual_scan", False),
            "strict_fvg": self.params.get("entry", {}).get("strict_fvg", False),
            "rr_ratio": self.params.get("entry", {}).get("rr_ratio", 2.0),
        }
        self.notifier.notify_bot_started(
            self.env["trading_mode"], self.capital, history, strategy_info,
        )

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
                    # notify_error filters network-class errors per spec
                    self.notifier.notify_error(f"Tick error: {e}")
                    # Shorter sleep during position monitoring to not miss exits
                    sleep_time = 5 if self.state == BotState.POSITION_OPEN else 30
                    time.sleep(sleep_time)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped")
            self._save_position_state()
            self.notifier.notify_bot_stopped("Graceful shutdown")

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
        # Preserve unclosed position across day boundary
        if self.position and self.position.is_open:
            logger.critical(
                f"OVERNIGHT: Unclosed position {self.position.symbol} "
                f"x{self.position.shares} @ ${self.position.entry_price:.2f} — "
                f"will attempt to close at next market open"
            )
            self.today_date = today
            self.trades_today = 0
            self._done_today_logged = False
            self.state = BotState.POSITION_OPEN
            self.circuit_breaker.reset_if_new_week(time_utils.get_week_number(), self.capital)
            logger.info(f"=== New Day: {today} (POSITION CARRIED OVER) ===")
            return

        self.today_date = today
        self.trend = None
        self.orb = None
        self.signal = None
        self.orbs = {}
        self.signals = {}
        self.position = None
        self.trades_today = 0
        self.state = BotState.WAITING
        self._done_today_logged = False
        self._premarket_synced_today = False
        self._notified_pre_market = False
        self._notified_orb = False
        self._notified_signal = False
        self._sync_capital()
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
        # If trend already determined, skip VIX/QQQ checks and just wait for ORB
        if self.trend is not None:
            if time_utils.is_orb_forming():
                self._transition(BotState.ORB_FORMING)
            else:
                secs = time_utils.seconds_until(time_utils.dtime(9, 30))
                if secs > 0:
                    time.sleep(min(secs, 60))
                else:
                    # Past 9:30 but is_orb_forming() is False — ORB window ended
                    self._transition(BotState.ORB_FORMING, "Late join")
            return

        # First pre-market entry of the day: re-sync capital so mid-day
        # USD deposits/FX conversions made after _check_new_day are picked
        # up before position sizing. Gated by a per-day flag to avoid
        # extra KIS calls on VIX/QQQ retry loops.
        if not self._premarket_synced_today:
            self._sync_capital()
            self._premarket_synced_today = True

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
        dual = self.params.get("mode", {}).get("dual_scan", False)

        if dual:
            logger.info(
                f"Pre-market complete: trend={self.trend.direction.upper()} "
                f"(info only — dual scan ignores trend for entry)"
            )
        else:
            logger.info(f"Pre-market complete: {self.trend.direction.upper()} → {self.trend.symbol}")
        if not self._notified_pre_market:
            self.notifier.notify_pre_market(
                vix, qqq_close, qqq_ma20,
                self.trend.direction.upper(), self.trend.symbol,
                dual_scan=dual,
            )
            self._notified_pre_market = True

        # Wait for ORB or transition immediately
        if time_utils.is_orb_forming():
            self._transition(BotState.ORB_FORMING)
        else:
            secs = time_utils.seconds_until(time_utils.dtime(9, 30))
            if secs > 0:
                logger.info(f"Waiting {secs/60:.0f}min for ORB window")
                time.sleep(min(secs, 60))

    def _handle_orb_forming(self):
        """Collect ORB data during 9:30-9:45.

        In dual_scan mode, ORB is computed for both BULL and BEAR symbols.
        In single-trend mode, only the trend-selected symbol is computed.
        """
        if self.trend is None:
            # Missed pre-market, do quick check
            self._handle_pre_market()
            return

        if time_utils.is_orb_forming():
            time.sleep(30)
            return

        syms = self.params["symbols"]
        dual = self.params.get("mode", {}).get("dual_scan", False)
        candidates = [syms["bull"], syms["bear"]] if dual else [self.trend.symbol]
        atr_ratio = self.params["filters"]["orb_atr_max_ratio"]

        self.orbs = {}
        for symbol in candidates:
            bars = get_intraday_bars(symbol, period="1d", interval="5m")
            if bars is None:
                logger.warning(f"ORB: No intraday data for {symbol}, retrying in 60s")
                time.sleep(60)
                bars = get_intraday_bars(symbol, period="1d", interval="5m")
            if bars is None:
                logger.warning(f"ORB: {symbol} unavailable after retry, skipping leg")
                continue

            orb = calculate_orb(bars)
            if orb is None:
                logger.warning(f"ORB: calculation failed for {symbol}")
                continue

            adr = get_avg_daily_range(symbol)
            if adr and is_orb_too_wide(orb, adr, atr_ratio):
                logger.info(f"ORB: {symbol} too wide ({orb.range_size:.2f}), skipping leg")
                continue

            self.orbs[symbol] = orb

        if not self.orbs:
            self._transition(BotState.DONE_TODAY, "No valid ORB on either leg")
            self.notifier.notify_skip("ORB unavailable / too wide on all legs")
            return

        # Keep self.orb pointing at the trend-preferred leg for legacy
        # consumers; signals are scanned per-leg from self.orbs.
        self.orb = self.orbs.get(self.trend.symbol) or next(iter(self.orbs.values()))

        if not self._notified_orb:
            for symbol, orb in self.orbs.items():
                self.notifier.notify_orb(symbol, orb.high, orb.low, orb.range_size)
            self._notified_orb = True

        self._transition(BotState.SCANNING)

    def _handle_scanning(self):
        """Scan for entry signals in 9:45-10:55 window.

        In dual_scan mode each leg in self.orbs is scanned. The first leg
        whose latest bar pulls back into its FVG wins the day's single trade.
        """
        if not time_utils.is_scan_window():
            self._transition(BotState.DONE_TODAY, "Scan window closed, no signal")
            self.notifier.notify_skip("No signal today")
            return

        if not self.orbs:
            self._transition(BotState.DONE_TODAY, "No ORB data available")
            return

        entry_params = self.params["entry"]
        strict = entry_params.get("strict_fvg", False)

        for symbol, orb in self.orbs.items():
            bars = get_intraday_bars(symbol, period="1d", interval="5m")
            if bars is None:
                continue

            scan_bars = bars.between_time("09:45", "10:55")
            if len(scan_bars) < 4:
                continue

            sig = self.signals.get(symbol)
            if sig is None:
                sig = scan_for_signal(
                    scan_bars, orb, symbol,
                    rr_ratio=entry_params["rr_ratio"],
                    min_risk=entry_params["min_risk_dollar"],
                    strict=strict,
                )
                if sig is None:
                    continue
                self.signals[symbol] = sig
                if not self._notified_signal:
                    self.notifier.notify_signal(
                        sig.symbol, sig.entry_price,
                        sig.stop_loss, sig.take_profit, sig.rr_ratio,
                    )
                    self._notified_signal = True

            latest_bar = scan_bars.iloc[-1]
            if check_pullback(latest_bar, sig.fvg):
                self.signal = sig
                self.orb = orb
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
                self._sync_capital()
                if self.capital <= 0:
                    self._transition(
                        BotState.DONE_TODAY,
                        "Capital sync failed — skipping today"
                    )
                    return
            # Size against the all-in cost-per-share that KIS validates against:
            # limit price (price * (1 + buy_slippage)) plus entry-side commission.
            # Without this, "주문가능금액 초과" rejects when capital sits at a
            # 1-share boundary.
            buy_slip = self.params.get("order", {}).get("buy_slippage_pct", 0.005)
            comm_rate = self.params.get("commission", {}).get("rate_per_side", 0.0009)
            eff_price = price * (1 + buy_slip + comm_rate)
            shares = int(self.capital / eff_price) if eff_price > 0 else 0
            # Apply position size cap
            risk_params = self.params.get("risk", {})
            max_shares = risk_params.get("max_shares", 200)
            max_pct = risk_params.get("max_position_pct", 1.0)
            max_by_pct = int(self.capital * max_pct / eff_price) if eff_price > 0 else 0
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
                self.notifier.notify_order_failed(
                    self.position.symbol, "buy", shares,
                    "KIS rejected (see logs)",
                )
                self.position = None
                self._transition(BotState.DONE_TODAY, "Order execution failed")
                return
            order_no = order_result.get("order_no", "")
            logger.info(f"BUY ORDER OK: #{order_no}")
            # Persist position state immediately after order is accepted by KIS,
            # before the (slow) fill-price polling. If the process crashes
            # during polling, restart can recover the position via state file
            # rather than orphaning the broker-side holding.
            self._pending_buy_order_no = order_no
            self._save_position_state()

            # Query actual fill price and update position entry
            if self.kis_client and order_no:
                fill_price = self.kis_client.get_us_filled_price(
                    order_no, self.position.symbol
                )
                if fill_price:
                    self._apply_fill_price(fill_price)
                    self._pending_buy_order_no = None
                else:
                    logger.info(f"Fill price pending — will retry in POSITION_OPEN loop")

        # Mark trade in-progress so any critical Telegram message that fails
        # with a network error gets queued for end_trade() flush instead of
        # competing with KIS calls during the live trade window.
        self.notifier.begin_trade()
        self.notifier.notify_entry(
            self.position.symbol, self.position.entry_price,
            self.position.shares, self.position.stop_loss,
            self.position.take_profit, self.position.risk_per_share,
            rr_ratio=self.position.signal.rr_ratio,
        )
        self._save_position_state()
        self._transition(BotState.POSITION_OPEN)

    def _apply_fill_price(self, fill_price: float):
        """Update position entry price, risk, and TP based on actual fill."""
        if not self.position or fill_price == self.position.entry_price:
            return
        old_price = self.position.entry_price
        risk = fill_price - self.position.signal.stop_loss
        if risk > 0:
            self.position.entry_price = fill_price
            self.position.risk_per_share = round(risk, 2)
            self.position.take_profit = fill_price + risk * self.position.signal.rr_ratio
            logger.info(f"Entry adjusted to fill: ${old_price:.2f} → ${fill_price:.4f}, "
                       f"TP ${self.position.take_profit:.2f}")
            self._save_position_state()

    def _handle_position_open(self):
        """Monitor open position for exit conditions."""
        if self.position is None or not self.position.is_open:
            self._transition(BotState.DONE_TODAY)
            return

        # ─── Retry fill price query if still pending ───
        if self._pending_buy_order_no and self.kis_client:
            fill_price = self.kis_client.get_us_filled_price(
                self._pending_buy_order_no, self.position.symbol,
                max_attempts=1,
            )
            if fill_price:
                self._apply_fill_price(fill_price)
                self._pending_buy_order_no = None

        # ─── Overnight position: next-day market open → immediate close ───
        if time_utils.is_next_day_open():
            logger.critical("OVERNIGHT CLOSE: Selling carried-over position at market open")
            current = get_current_price(self.position.symbol)
            if current is None:
                current = self.position.entry_price
            self._close_and_record(current, "overnight_force")
            return

        # ─── After hours (16:00+): attempt limit order if market sell failed ───
        if time_utils.is_after_hours():
            if self._sell_retry_count > 0:
                # Market sell already failed during regular hours, try limit
                logger.warning(
                    f"After hours: attempting limit sell for {self.position.symbol} "
                    f"(market sell failed {self._sell_retry_count}x)"
                )
            current = get_current_price(self.position.symbol)
            if current is None:
                current = self.position.entry_price
            self._close_and_record(current, "after_hours_force")
            time.sleep(30)
            return

        # 11:00 BE move
        if time_utils.is_past_be_time() and not self.position.be_stop_moved:
            old_sl = self.position.stop_loss
            move_stop_to_breakeven(self.position)
            if self.position.be_stop_moved:
                self.notifier.notify_be_move(
                    self.position.symbol, old_sl, self.position.stop_loss,
                )

        # 15:50 force close
        if time_utils.is_force_close_time():
            current = get_current_price(self.position.symbol)
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

            # Check for partial fill via order_no, not holdings polling — the
            # holdings endpoint lags KIS settlement by seconds and can return
            # the pre-fill quantity, causing a duplicate retry sell.
            if self.kis_client and order_no:
                time.sleep(2)  # Allow KIS to record execution
                executions = self.kis_client.get_us_today_executions(
                    self.position.symbol
                )
                filled_qty = sum(
                    e.get("fill_qty", 0)
                    for e in executions
                    if e.get("order_no") == order_no
                )
                remaining_qty = self.position.shares - filled_qty
                if filled_qty > 0 and remaining_qty > 0:
                    logger.warning(
                        f"PARTIAL FILL: order #{order_no} filled "
                        f"{filled_qty}/{self.position.shares} — retrying {remaining_qty}"
                    )
                    self.kis_order.sell_market(
                        self.position.symbol, remaining_qty
                    )
                elif filled_qty == 0:
                    logger.warning(
                        f"NO FILL DETECTED for #{order_no} after 2s — "
                        f"skipping retry to avoid duplicate sell; reconcile will adjust"
                    )

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
        # Trade is over — flush any queued critical messages that hit a
        # network error during the live trade window.
        self.notifier.end_trade()

        # Reconcile with actual broker execution data
        self._reconcile_with_broker()

        self._transition(BotState.DONE_TODAY, f"{self.position.result} PnL=${self.position.net_pnl:+.2f}")

    def _reconcile_with_broker(self):
        """Query KIS for actual execution data and update trade record."""
        if not self.kis_client or not self.position:
            return
        try:
            executions = self.kis_client.get_us_today_executions(self.position.symbol)
            if not executions:
                logger.warning("RECONCILE: No executions found from broker")
                return

            buys = [e for e in executions if e["side"] == "buy"]
            sells = [e for e in executions if e["side"] == "sell"]

            broker_buy_price = buys[-1]["fill_price"] if buys else None
            broker_sell_price = sells[-1]["fill_price"] if sells else None
            broker_buy_amount = sum(e["fill_amount"] for e in buys)
            broker_sell_amount = sum(e["fill_amount"] for e in sells)
            broker_gross_pnl = round(broker_sell_amount - broker_buy_amount, 2) if buys and sells else None

            updates = {
                "broker_buy_price": broker_buy_price,
                "broker_sell_price": broker_sell_price,
                "broker_buy_amount": round(broker_buy_amount, 2),
                "broker_sell_amount": round(broker_sell_amount, 2),
                "broker_gross_pnl": broker_gross_pnl,
            }
            update_last_trade(updates)

            # Correct circuit breaker with actual PnL
            if broker_gross_pnl is not None and self.position:
                actual_pnl = broker_gross_pnl - self.position.commission
                old_pnl = self.position.net_pnl
                if abs(actual_pnl - old_pnl) > 0.01:
                    self.circuit_breaker.correct_last_trade(
                        self.position.result, old_pnl, actual_pnl
                    )

            logger.info(
                f"RECONCILE: Buy ${broker_buy_price:.4f} → Sell ${broker_sell_price:.4f} "
                f"Gross PnL=${broker_gross_pnl:+.2f}"
                if broker_buy_price and broker_sell_price and broker_gross_pnl is not None
                else f"RECONCILE: Partial data — {updates}"
            )
        except Exception as e:
            logger.error(f"RECONCILE failed: {e}")

    def _sync_capital(self):
        """Sync capital with actual KIS account balance."""
        if not self.kis_client:
            return
        balance = self.kis_client.get_us_balance()
        if balance and balance.get("available_cash", 0) > 0:
            old = self.capital
            self.capital = balance["available_cash"]
            if old > 0:
                logger.info(f"Capital synced: ${old:.2f} → ${self.capital:.2f} "
                           f"(diff ${self.capital - old:+.2f})")
            else:
                logger.info(f"Capital synced from KIS: ${self.capital:.2f}")

    def _handle_done_today(self):
        """Wait until next day."""
        if not self._done_today_logged:
            self._sync_capital()
            all_trades = load_trades()
            stats = get_cumulative_stats(all_trades)
            logger.info(f"Cumulative: {stats['total_trades']}T WR={stats['win_rate']}% "
                         f"PnL=${stats['total_pnl']:+.2f} PF={stats['profit_factor']}")
            # Daily Telegram summary — pull today's trade (if any) from history
            today_str = time_utils.now_et().strftime("%Y-%m-%d")
            today_trade = next(
                (t for t in reversed(all_trades) if t.get("date") == today_str),
                None,
            )
            self.notifier.notify_daily_summary(
                today_trade,
                {
                    "total": stats.get("total_trades", 0),
                    "wr": stats.get("win_rate", 0),
                    "pf": stats.get("profit_factor", 0),
                    "pnl": stats.get("total_pnl", 0),
                },
                self.capital,
            )
            self._done_today_logged = True

        # Sleep until midnight or long interval
        time.sleep(300)
