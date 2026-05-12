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

import pandas as pd

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
        # ICT meta captured at signal time, stored alongside the trade.
        self._signal_ict_meta: Optional[dict] = None
        # Daily bias (ICT Phase 3), computed once per pre-market.
        self._daily_bias = None
        # Telegram dedup flags for new ICT-aware notifications
        self._notified_scan_start = False
        self._notified_setup = False

        # Load trade history
        self._init_from_history()

        # Data collector (env-toggled, isolated). MUST come last so that
        # any failure here cannot abort the trading bot construction.
        self.collector = None
        self._marketdata_base = os.path.join(
            os.path.dirname(__file__), "..", "data", "marketdata"
        )
        self._init_collector(self._marketdata_base)
        self._cold_start_backfill(
            self._marketdata_base,
            symbols=[
                self.params["symbols"]["bull"],
                self.params["symbols"]["bear"],
                self.params["symbols"]["trend_filter"],
                "^VIX",
            ],
        )

    def _init_collector(self, base_dir):
        """Start BarCollector iff DATA_COLLECTION=on. Safe on failure."""
        if os.environ.get("DATA_COLLECTION", "off").lower() != "on":
            self.collector = None
            return
        try:
            from src.data.collector import BarCollector
            self.collector = BarCollector(base_dir=base_dir)
            self.collector.start()
            logger.info("DataCollection: enabled (DATA_COLLECTION=on)")
        except Exception as e:
            logger.warning(f"DataCollection: init failed, disabled: {e}")
            self.collector = None

    def _record_bars(self, symbol, bars):
        """Submit bars to collector. NEVER raises."""
        if self.collector is None or bars is None or bars.empty:
            return
        try:
            date_str = bars.index[0].strftime("%Y-%m-%d")
            self.collector.submit(symbol, date_str, bars, source="kis")
        except Exception as e:
            logger.warning(f"DataCollection: submit failed silently: {e}")

    def _cold_start_backfill(self, base_dir, symbols):
        """Fill missing days via yfinance on bot startup. Silent on failure.

        Backfills both 5-min Parquet (60 day yfinance window) and daily
        Parquet store. Daily store reuses get_daily_df() which writes back.
        """
        if self.collector is None:
            return
        if os.environ.get("DATA_COLLECTION_BACKFILL", "on").lower() != "on":
            return
        try:
            from datetime import datetime, timedelta, timezone
            from src.data.gap_finder import find_gaps
            from src.data.backfill import fill_gaps_from_yfinance
            from src.data.market_data import get_daily_df

            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=60)
            total_5m = 0
            for sym in symbols:
                gaps = find_gaps(base_dir, sym, start, end)
                if gaps:
                    n = fill_gaps_from_yfinance(base_dir, sym, gaps)
                    total_5m += n
                    logger.info(f"Backfill: {sym} 5m {n}/{len(gaps)} days written")
            logger.info(f"Backfill: 5m cold start done (total={total_5m} days)")

            # Daily store warm-up (skip ^VIX — daily VIX is on yfinance only,
            # treated separately by other code paths).
            for sym in symbols:
                if sym.startswith("^"):
                    continue
                try:
                    df = get_daily_df(sym, lookback=120)
                    if df is not None and not df.empty:
                        logger.info(f"Backfill: {sym} daily store has {len(df)} rows")
                except Exception as e:
                    logger.warning(f"Backfill: {sym} daily fetch failed: {e}")

            # Phase 4: NQ futures 5-min for Power of 3 (best effort)
            try:
                from src.data.futures import fetch_nq_futures_5m
                from src.data.store import save_bars
                nq = fetch_nq_futures_5m(period="5d")
                if nq is not None and not nq.empty:
                    # Persist per-day
                    nq = nq.copy()
                    nq["date"] = nq.index.date
                    for d in sorted(set(nq["date"].tolist())):
                        sub = nq[nq["date"] == d].drop(columns=["date"])
                        save_bars(base_dir, "NQ=F", d.isoformat(), sub, source="yfinance")
                    logger.info(f"Backfill: NQ=F {len(nq)} 5m bars persisted")
            except Exception as e:
                logger.debug(f"Backfill: NQ=F skipped silently: {e}")

            # 1-min bar warm-up (used by Multi-TF SL refinement)
            try:
                from src.data.market_data import get_intraday_bars
                for sym in ["TQQQ", "QQQ", "SQQQ"]:
                    bars1 = get_intraday_bars(sym, period="1d", interval="1m")
                    if bars1 is not None and not bars1.empty:
                        logger.info(f"Backfill: {sym} 1m fetched ({len(bars1)} bars)")
            except Exception as e:
                logger.debug(f"Backfill: 1m fetch failed silently: {e}")
        except Exception as e:
            logger.warning(f"Backfill: cold start failed silently: {e}")

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
        # ICT phase summary (compact). Reads effective config (env overrides applied).
        ep = self.params.get("entry", {})
        ict_flags = []
        if ep.get("killzone_filter_enabled"):
            kz = ep.get("allowed_killzones") or []
            ict_flags.append("KZ(" + ",".join(kz) + ")" if kz else "KZ")
        if ep.get("require_displacement"):
            ict_flags.append("Disp")
        if ep.get("require_sweep_choch"):
            ict_flags.append("Sweep")
        if ep.get("daily_bias_skip_neutral"):
            ict_flags.append("Bias")
        if ep.get("bear_fvg_for_sqqq"):
            ict_flags.append("QQQ→SQQQ")
        if ep.get("bull_fvg_for_tqqq"):
            ict_flags.append("QQQ→TQQQ")
        if ep.get("use_ote"):
            ict_flags.append(f"OTE({ep.get('ote_fib_level', 0.705)})")
        if ep.get("require_unicorn"):
            ict_flags.append("Unicorn")
        if ep.get("use_multi_tf_sl"):
            ict_flags.append("MTF-SL")
        if ep.get("use_power_of_3"):
            ict_flags.append("P3")
        logger.info(f"ICT : {' + '.join(ict_flags) if ict_flags else 'off'}")
        # Render trading window in both ET and current KST (DST-aware).
        try:
            from datetime import datetime, time as dtime
            import pytz
            et = pytz.timezone("US/Eastern")
            kst = pytz.timezone("Asia/Seoul")
            today_et = datetime.now(et)
            t_start_et = et.localize(datetime.combine(today_et.date(), dtime(9, 30)))
            t_end_et = et.localize(datetime.combine(today_et.date(), dtime(10, 55)))
            kst_start = t_start_et.astimezone(kst).strftime("%H:%M")
            kst_end = t_end_et.astimezone(kst).strftime("%H:%M")
            dst_tag = "서머타임" if today_et.dst() != datetime.now(et).utcoffset() * 0 else ""
            is_dst = today_et.dst().total_seconds() != 0
            dst_tag = "서머타임" if is_dst else "표준시"
            logger.info(
                f"      ※ 매매 윈도우: ET 09:30~10:55  (KST {kst_start}~{kst_end}, {dst_tag})"
            )
        except Exception as e:
            logger.debug(f"KST window render failed: {e}")
            logger.info("      ※ 매매 윈도우: ET 09:30~10:55 (KST 변환 실패)")

        # ── Fine-tune reminder (ICT trades 누적 추적) ──
        try:
            from src.data.trade_store import load_trades as _lt
            _all_trades = _lt()
            n_ict = sum(1 for t in _all_trades if isinstance(t, dict) and t.get("ict"))
            target = 5  # 통계적 의미 최소 표본
            if n_ict < target:
                logger.info(
                    f"📌 Fine-tune: ICT 매매 {n_ict}/{target}건 누적 "
                    f"(목표 도달 시 'python scripts/phase1_precheck.py' 재실행 권장)"
                )
            elif n_ict % target == 0:
                logger.info(
                    f"📌 Fine-tune NOW: ICT 매매 {n_ict}건 — "
                    f"phase1_precheck.py 재실행해서 임계값 검증 권장"
                )
            else:
                next_check = ((n_ict // target) + 1) * target
                logger.info(
                    f"📌 Fine-tune: ICT 매매 {n_ict}건 누적 (다음 검증: {next_check}건)"
                )
        except Exception as e:
            logger.debug(f"Fine-tune reminder skipped: {e}")

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
        ep = self.params.get("entry", {})
        strategy_info = {
            "dual_scan": self.params.get("mode", {}).get("dual_scan", False),
            "strict_fvg": ep.get("strict_fvg", False),
            "rr_ratio": ep.get("rr_ratio", 2.0),
            # ICT phase status — telegram displays a compact summary
            "ict_killzone": ep.get("killzone_filter_enabled", False),
            "ict_allowed_killzones": ep.get("allowed_killzones", []),
            "ict_displacement": ep.get("require_displacement", False),
            "ict_sweep_choch": ep.get("require_sweep_choch", False),
            "ict_daily_bias": ep.get("daily_bias_skip_neutral", False),
            "ict_bear_for_sqqq": ep.get("bear_fvg_for_sqqq", False),
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
            if getattr(self, "collector", None) is not None:
                try:
                    self.collector.stop(timeout=5.0)
                except Exception:
                    pass

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
        self._signal_ict_meta = None
        self._daily_bias = None
        self._notified_scan_start = False
        self._notified_setup = False
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

        # ICT Phase 3: Daily Bias hook. If enabled and bias == 'neutral',
        # skip the day. Failure of bias computation is non-fatal — we keep
        # trading on the default (MA20-only) decision in that case.
        skip_neutral = self.params.get("entry", {}).get("daily_bias_skip_neutral", False)
        if skip_neutral:
            try:
                from src.data.market_data import get_qqq_daily_df
                from src.core.bias import compute_daily_bias
                daily_df = get_qqq_daily_df(lookback=60)
                judas = None
                if self.params.get("entry", {}).get("use_power_of_3", False):
                    try:
                        from src.data.futures import fetch_nq_futures_5m, detect_judas_swing
                        nq = fetch_nq_futures_5m(period="5d")
                        if nq is not None and not nq.empty:
                            judas = detect_judas_swing(nq, time_utils.now_et().date())
                            if judas:
                                logger.info(f"Power of 3: Judas Swing detected — {judas}")
                    except Exception as e:
                        logger.debug(f"Power of 3 fetch failed (non-fatal): {e}")
                if daily_df is not None and not daily_df.empty:
                    bias = compute_daily_bias(daily_df, judas_signal=judas)
                    if bias is not None:
                        logger.info(
                            f"Daily Bias: direction={bias.direction} "
                            f"score={bias.score:+d} components={bias.components}"
                        )
                        self._daily_bias = bias  # exposed for telegram / status
                        # ICT log: persist the bias decision
                        try:
                            from src.data.ict_log import record as _ict_log
                            _ict_log(event="daily_bias", passed=None,
                                     details={
                                         "direction": bias.direction,
                                         "score": bias.score,
                                         "components": bias.components,
                                         "pdh": bias.pdh, "pdl": bias.pdl,
                                         "pwh": bias.pwh, "pwl": bias.pwl,
                                         "judas": judas,
                                     })
                        except Exception as e:
                            logger.debug(f"ict_log daily_bias failed: {e}")
                        # Telegram notification (always, even if not neutral)
                        try:
                            self.notifier.notify_daily_bias(bias)
                        except Exception as e:
                            logger.debug(f"notify_daily_bias failed: {e}")
                        if bias.direction == "neutral":
                            self._transition(
                                BotState.DONE_TODAY,
                                f"Daily Bias neutral (score=0) — skip per ICT Phase 3",
                            )
                            self.notifier.notify_skip(
                                "Daily Bias neutral (ICT Phase 3 skip-neutral)"
                            )
                            return
                else:
                    logger.warning(
                        "Daily Bias: QQQ daily df unavailable — continuing without bias gate"
                    )
            except Exception as e:
                logger.warning(f"Daily Bias hook failed (non-fatal): {e}")

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
        # ICT Phase-3/4 QQQ-signal-mapping: when bear→SQQQ or bull→TQQQ is on,
        # we also need QQQ's ORB so we can scan QQQ for setups and remap.
        bear_for_sqqq = self.params["entry"].get("bear_fvg_for_sqqq", False)
        bull_for_tqqq = self.params["entry"].get("bull_fvg_for_tqqq", False)
        if (bear_for_sqqq or bull_for_tqqq) and syms["trend_filter"] not in candidates:
            candidates = candidates + [syms["trend_filter"]]
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

            self._record_bars(symbol, bars)

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
            # Persist ORB to the audit log (one entry per symbol)
            try:
                from src.data.ict_log import record as _ict_log
                for symbol, orb in self.orbs.items():
                    _ict_log(event="orb_formed", symbol=symbol, passed=None,
                             details={"high": orb.high, "low": orb.low,
                                       "range": orb.range_size, "date": orb.date})
            except Exception as e:
                logger.debug(f"ict_log orb_formed failed: {e}")
            # Single consolidated ORB summary covering all legs (replaces N pings).
            try:
                self.notifier.notify_orb_summary(self.orbs)
            except Exception:
                # Fall back to per-symbol legacy notifications if summary fails
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
            # Distinguish Killzone-end vs full scan-window-end for clarity
            ep = self.params.get("entry", {})
            if ep.get("killzone_filter_enabled"):
                try:
                    self.notifier.notify_killzone_end_no_signal(
                        killzone_label=",".join(ep.get("allowed_killzones", ["AM_MACRO"]))
                    )
                except Exception:
                    self.notifier.notify_skip("No signal today")
            else:
                self.notifier.notify_skip("No signal today")
            return

        if not self.orbs:
            self._transition(BotState.DONE_TODAY, "No ORB data available")
            return

        # Scan-start announcement (once per day)
        if not getattr(self, "_notified_scan_start", False):
            try:
                from datetime import datetime, time as dtime
                import pytz
                et = pytz.timezone("US/Eastern")
                kst = pytz.timezone("Asia/Seoul")
                today_et = datetime.now(et)
                s = et.localize(datetime.combine(today_et.date(), dtime(9, 45))).astimezone(kst)
                # End of allowed scan: use last killzone end or 10:55
                ep_ = self.params.get("entry", {})
                if ep_.get("killzone_filter_enabled"):
                    kz_label = ",".join(ep_.get("allowed_killzones", ["AM_MACRO"]))
                    # AM_MACRO ends 10:10
                    e_et = et.localize(datetime.combine(today_et.date(), dtime(10, 10)))
                else:
                    kz_label = None
                    e_et = et.localize(datetime.combine(today_et.date(), dtime(10, 55)))
                e_kst = e_et.astimezone(kst)
                kst_win = f"KST {s.strftime('%H:%M')}~{e_kst.strftime('%H:%M')}"
                self.notifier.notify_scan_start(killzone_label=kz_label, kst_window=kst_win)
            except Exception as e:
                logger.debug(f"notify_scan_start failed: {e}")
            self._notified_scan_start = True

        entry_params = self.params["entry"]
        strict = entry_params.get("strict_fvg", False)

        # ICT Phase 1 filters (config-toggled, default OFF for safe rollout)
        kz_enabled = entry_params.get("killzone_filter_enabled", False)
        allowed_killzones = entry_params.get("allowed_killzones", []) if kz_enabled else None
        require_disp = entry_params.get("require_displacement", False)
        disp_atr_mult = entry_params.get("disp_atr_mult", 1.0)
        disp_max_wick = entry_params.get("disp_max_wick", 0.50)
        disp_prev_mult = entry_params.get("disp_prev_mult", 1.5)
        # ICT Phase 2 filter (sweep + CHoCH)
        require_sweep_choch = entry_params.get("require_sweep_choch", False)
        sweep_lookback = entry_params.get("sweep_lookback", 6)
        choch_lookback = entry_params.get("choch_lookback", 6)
        sweep_min_breach_pct = entry_params.get("sweep_min_breach_pct", 0.0005)
        sweep_min_wick_ratio = entry_params.get("sweep_min_wick_ratio", 0.60)
        # ICT Phase 3 QQQ-mapping: scan QQQ for bear setup → SQQQ Long
        bear_for_sqqq = entry_params.get("bear_fvg_for_sqqq", False)
        # ICT Phase 4 N6: scan QQQ for bull setup → TQQQ Long (symmetric)
        bull_for_tqqq = entry_params.get("bull_fvg_for_tqqq", False)
        # ICT Phase 4: Multi-TF SL refinement (1-min swing)
        use_multi_tf_sl = entry_params.get("use_multi_tf_sl", False)
        mtf_lookback_min = entry_params.get("mtf_lookback_min", 15)
        # ICT Phase 4: OTE entry
        use_ote = entry_params.get("use_ote", False)
        ote_fib_level = entry_params.get("ote_fib_level", 0.705)
        # ICT Phase 4: Unicorn (Breaker + FVG overlap)
        require_unicorn = entry_params.get("require_unicorn", False)
        syms = self.params["symbols"]

        for symbol, orb in self.orbs.items():
            # Skip SQQQ self-scan when bear-QQQ-mapping is on
            if bear_for_sqqq and symbol == syms["bear"]:
                continue
            # Skip TQQQ self-scan when bull-QQQ-mapping is on
            if bull_for_tqqq and symbol == syms["bull"]:
                continue

            # Decide direction for this leg.
            if symbol == syms["trend_filter"]:
                directions = []
                if bull_for_tqqq:
                    directions.append("bull")    # QQQ bull → TQQQ Long
                if bear_for_sqqq:
                    directions.append("bear")    # QQQ bear → SQQQ Long
                if not directions:
                    # QQQ leg only used when at least one mapping is enabled
                    continue
            else:
                directions = ["bull"]   # default — TQQQ/SQQQ self-chart bullish

            bars = get_intraday_bars(symbol, period="1d", interval="5m")
            if bars is None:
                continue

            self._record_bars(symbol, bars)

            scan_bars = bars.between_time("09:45", "10:55")
            if len(scan_bars) < 4:
                continue

            # Optional 1-min bars for Multi-TF SL refinement (best effort)
            bars_1m = None
            if use_multi_tf_sl:
                try:
                    bars_1m = get_intraday_bars(symbol, period="1d", interval="1m")
                except Exception as e:
                    logger.debug(f"{symbol}: 1m fetch failed (non-fatal): {e}")

            for direction in directions:
                cache_key = f"{symbol}:{direction}"
                sig = self.signals.get(cache_key)
                if sig is None:
                    sig = scan_for_signal(
                        scan_bars, orb, symbol,
                        rr_ratio=entry_params["rr_ratio"],
                        min_risk=entry_params["min_risk_dollar"],
                        strict=strict,
                        allowed_killzones=allowed_killzones,
                        require_displacement=require_disp,
                        disp_atr_mult=disp_atr_mult,
                        disp_max_wick=disp_max_wick,
                        disp_prev_mult=disp_prev_mult,
                        history_bars=bars,
                        require_sweep_choch=require_sweep_choch,
                        sweep_lookback=sweep_lookback,
                        choch_lookback=choch_lookback,
                        sweep_min_breach_pct=sweep_min_breach_pct,
                        sweep_min_wick_ratio=sweep_min_wick_ratio,
                        direction=direction,
                        bars_1m=bars_1m,
                        use_multi_tf_sl=use_multi_tf_sl,
                        mtf_lookback_min=mtf_lookback_min,
                        use_ote=use_ote,
                        ote_fib_level=ote_fib_level,
                        require_unicorn=require_unicorn,
                    )
                    if sig is None:
                        continue
                    self.signals[cache_key] = sig
                    # Setup-detected announcement (BEFORE pullback)
                    if not self._notified_setup:
                        try:
                            self.notifier.notify_setup_detected(
                                symbol=sig.symbol,
                                direction=sig.direction,
                                fvg_top=sig.fvg.top,
                                fvg_bot=sig.fvg.bottom,
                                filters_active=(
                                    ["killzone"] if allowed_killzones else []
                                ) + (
                                    ["displacement"] if require_disp else []
                                ) + (
                                    ["sweep_choch"] if require_sweep_choch else []
                                ) + (
                                    ["qqq_mapping"] if bear_for_sqqq and direction == "bear" else []
                                ),
                            )
                            self._notified_setup = True
                        except Exception as e:
                            logger.debug(f"notify_setup_detected failed: {e}")
                    # Capture ICT metadata for trade record.
                    try:
                        from src.core.sessions import killzone_for
                        filters_active = []
                        if allowed_killzones:
                            filters_active.append("killzone")
                        if require_disp:
                            filters_active.append("displacement")
                        if require_sweep_choch:
                            filters_active.append("sweep_choch")
                        if bear_for_sqqq and direction == "bear":
                            filters_active.append("qqq_mapping")
                        try:
                            sig_ts = pd.Timestamp(sig.signal_time).tz_localize("US/Eastern")
                            kz = killzone_for(sig_ts)
                        except Exception:
                            kz = None
                        self._signal_ict_meta = {
                            "killzone": kz,
                            "filters_active": filters_active,
                            "signal_direction": sig.direction,
                            "rr_ratio": sig.rr_ratio,
                            "daily_bias_direction":
                                getattr(self._daily_bias, "direction", None),
                            "daily_bias_score":
                                getattr(self._daily_bias, "score", None),
                            "signal_source": symbol,
                        }
                    except Exception as e:
                        logger.debug(f"ICT meta capture failed (non-fatal): {e}")
                        self._signal_ict_meta = None

                # Pullback detection on the ORIGINATING chart (QQQ for bear
                # leg, exec ETF for bull leg).
                latest_bar = scan_bars.iloc[-1]
                if check_pullback(latest_bar, sig.fvg, direction=direction):
                    if symbol == syms["trend_filter"] and direction == "bear":
                        # QQQ bearish → SQQQ Long mapping (Phase 3)
                        from src.core.exec_mapper import remap_qqq_bear_to_sqqq_long
                        sqqq_price = get_current_price(syms["bear"])
                        if sqqq_price is None or sqqq_price <= 0:
                            logger.warning("SQQQ price unavailable, skipping bear-mapped trade")
                            return
                        remapped = remap_qqq_bear_to_sqqq_long(sig, sqqq_price, exec_symbol=syms["bear"])
                        if remapped is None:
                            logger.warning("SQQQ remap failed, skipping")
                            return
                        self.signal = remapped
                        self.orb = orb
                        if not self._notified_signal:
                            self.notifier.notify_signal(
                                remapped.symbol, remapped.entry_price,
                                remapped.stop_loss, remapped.take_profit, remapped.rr_ratio,
                                ict_meta=self._signal_ict_meta,
                            )
                            self._notified_signal = True
                        self._execute_entry()
                        return
                    elif symbol == syms["trend_filter"] and direction == "bull":
                        # QQQ bullish → TQQQ Long mapping (Phase 4 N6)
                        from src.core.exec_mapper import remap_qqq_bull_to_tqqq_long
                        tqqq_price = get_current_price(syms["bull"])
                        if tqqq_price is None or tqqq_price <= 0:
                            logger.warning("TQQQ price unavailable, skipping bull-mapped trade")
                            return
                        remapped = remap_qqq_bull_to_tqqq_long(sig, tqqq_price, exec_symbol=syms["bull"])
                        if remapped is None:
                            logger.warning("TQQQ remap failed, skipping")
                            return
                        self.signal = remapped
                        self.orb = orb
                        if not self._notified_signal:
                            self.notifier.notify_signal(
                                remapped.symbol, remapped.entry_price,
                                remapped.stop_loss, remapped.take_profit, remapped.rr_ratio,
                                ict_meta=self._signal_ict_meta,
                            )
                            self._notified_signal = True
                        self._execute_entry()
                        return
                    else:
                        if not self._notified_signal:
                            self.notifier.notify_signal(
                                sig.symbol, sig.entry_price,
                                sig.stop_loss, sig.take_profit, sig.rr_ratio,
                                ict_meta=self._signal_ict_meta,
                            )
                            self._notified_signal = True
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

        # Save trade (with ICT metadata captured at signal time, if any)
        trade = trade_from_position(self.position, ict_meta=self._signal_ict_meta)
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
