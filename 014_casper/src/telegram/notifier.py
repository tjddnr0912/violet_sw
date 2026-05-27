"""Telegram notification module.

Sends trade alerts, status updates, and daily summaries.
Send-only — no inbound command handling.

Critical trade messages (entry/exit/order failure) that fail to send
because of a *network* issue while a trade is in progress are queued
and re-sent sequentially after the trade closes. Other failures are
silently dropped — never retried mid-trade. Network errors themselves
are *not* surfaced as Telegram messages (would just be noise).
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger("casper")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
NETWORK_EXC = (requests.ConnectionError, requests.Timeout)
QUEUE_FLUSH_DELAY_SEC = 0.5


class TelegramNotifier:
    """Telegram bot notifier with deferred-retry queue for critical messages."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self._queue: list[str] = []
        self._in_trade: bool = False
        if not self.enabled:
            logger.info("Telegram: Not configured (notifications disabled)")

    # ── Trade lifecycle ─────────────────────────────────────────────────

    def begin_trade(self) -> None:
        """Mark a trade as in-progress.

        Critical messages whose send fails with a network error during this
        window are queued for flush at end_trade() instead of being retried
        immediately (which could compete with KIS calls for socket time).
        """
        self._in_trade = True

    def end_trade(self) -> None:
        """Trade ended — sequentially flush any queued critical messages."""
        self._in_trade = False
        if not self._queue:
            return
        logger.info(f"Telegram: flushing {len(self._queue)} deferred critical message(s)")
        for msg in list(self._queue):
            self._try_send(msg)  # best-effort; ignore result
            time.sleep(QUEUE_FLUSH_DELAY_SEC)
        self._queue.clear()

    # ── Send primitives ─────────────────────────────────────────────────

    def send(self, message: str, *, critical: bool = False) -> bool:
        """Send a message.

        Args:
            message: HTML-formatted body.
            critical: Trade-related message that must reach the operator.
                If sending fails with a network error while in-trade, the
                message is queued for end_trade() flush. Non-critical
                messages are silently dropped on any failure.

        Returns:
            True on confirmed delivery.
        """
        if not self.enabled:
            return False
        ok, network_err = self._try_send(message)
        if ok:
            return True
        if network_err and critical and self._in_trade:
            self._queue.append(message)
        # Network errors do not produce any Telegram-side message (per spec).
        return False

    def _try_send(self, message: str) -> tuple[bool, bool]:
        """Attempt one send. Returns (success, was_network_error)."""
        try:
            url = TELEGRAM_API.format(token=self.bot_token)
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.status_code == 200:
                return True, False
            logger.warning(f"Telegram: HTTP {resp.status_code}")
            return False, False
        except NETWORK_EXC as e:
            logger.warning(f"Telegram: network error: {e}")
            return False, True
        except Exception as e:
            logger.warning(f"Telegram: send failed: {e}")
            return False, False

    # ── Layout helpers ──────────────────────────────────────────────────
    # All operator-facing messages flow through `_box()` so we get the
    # same visual rhythm everywhere: emoji+title on top, monospace key/value
    # rows in the middle, optional footer. Putting the body inside a <pre>
    # tag preserves column alignment in Telegram clients.

    _DIVIDER = "━" * 28
    _SUBDIV = "─" * 28

    @staticmethod
    def _box(title: str, rows: list, footer: str = "",
             label_width: int = None) -> str:
        """Render a header + aligned key/value rows + optional footer.

        Args:
          title:  HTML-allowed header line (e.g. "🇺🇸 <b>미장봇 시작</b>")
          rows:   list of (label, value) tuples OR plain strings (rendered
                  as full-width lines inside the box)
          footer: trailing HTML-allowed text outside <pre>
          label_width: override auto-computed label column width

        Korean characters render as 2 columns in most monospace fonts;
        we still .ljust() on character count which is "good enough" for
        Telegram's mobile/desktop clients. Pure ASCII labels are cleaner
        — prefer them where possible.
        """
        body_lines = [TelegramNotifier._DIVIDER]
        if rows:
            tuple_rows = [r for r in rows if isinstance(r, tuple)]
            if label_width is None and tuple_rows:
                label_width = max(len(r[0]) for r in tuple_rows)
            for r in rows:
                if isinstance(r, tuple):
                    lbl, val = r
                    body_lines.append(f"  {lbl.ljust(label_width)}  {val}")
                elif isinstance(r, str) and r == "---":
                    body_lines.append(TelegramNotifier._SUBDIV)
                else:
                    body_lines.append(f"  {r}")
            body_lines.append(TelegramNotifier._DIVIDER)
        msg = f"{title}\n<pre>" + "\n".join(body_lines) + "</pre>"
        if footer:
            msg += f"\n{footer}"
        return msg

    # ── High-level notifications ────────────────────────────────────────

    def notify_bot_started(self, mode: str, capital: float, history: dict,
                           strategy_info: dict = None) -> None:
        rows: list = []
        rows.append(("Mode", mode.upper()))
        rows.append(("Capital", f"${capital:,.2f}"))
        hist_count = history.get('count', 0)
        hist_wr = history.get('win_rate', 0)
        hist_pnl = history.get('pnl', 0)
        rows.append(("History", f"{hist_count}T  WR {hist_wr:.1f}%  PnL ${hist_pnl:+,.2f}"))

        # Multi-bucket runtime info (cap + GEM mode) — pulled from .env.
        # Skipped when both are at defaults (legacy single-bucket Casper).
        if strategy_info:
            cap_usd = float(strategy_info.get("casper_max_position_usd", 0) or 0)
            gem_mode = strategy_info.get("gem_mode", "off")
            if cap_usd > 0 or gem_mode != "off":
                rows.append("---")
                if cap_usd > 0:
                    pct = (cap_usd / capital * 100) if capital > 0 else 0
                    rows.append(("Casper Cap", f"${cap_usd:,.0f}  ({pct:.1f}% of capital)"))
                if gem_mode != "off":
                    rows.append(("GEM Mode", gem_mode))

        if strategy_info:
            rows.append("---")
            scan = "DUAL (TQQQ+SQQQ)" if strategy_info.get("dual_scan") else "TREND (QQQ MA20)"
            fvg = "STRICT" if strategy_info.get("strict_fvg") else "baseline"
            rr_map = strategy_info.get("rr_ratio_by_killzone") or {}
            rr_default = strategy_info.get("rr_ratio", 2.0)
            rows.append(("Scan", scan))
            rows.append(("FVG", fvg))
            if rr_map:
                rr_summary = " / ".join(f"{k} 1:{v:g}" for k, v in rr_map.items())
                rows.append(("R:R", rr_summary))
            else:
                rows.append(("R:R", f"1:{rr_default:g}"))

            # KST window line — DST aware, derived from allowed killzones
            try:
                from datetime import datetime, time as dtime
                import pytz
                from src.core.sessions import KILLZONES
                et = pytz.timezone("US/Eastern")
                kst = pytz.timezone("Asia/Seoul")
                today_et = datetime.now(et)
                allowed = strategy_info.get("ict_allowed_killzones") or []
                if strategy_info.get("ict_killzone") and allowed:
                    ends = [KILLZONES[k][1] for k in allowed if k in KILLZONES]
                    end_t = max(ends) if ends else dtime(10, 55)
                else:
                    end_t = dtime(10, 55)
                s = et.localize(datetime.combine(today_et.date(), dtime(9, 30))).astimezone(kst)
                e = et.localize(datetime.combine(today_et.date(), end_t)).astimezone(kst)
                is_dst = today_et.dst().total_seconds() != 0
                et_end_s = end_t.strftime("%H:%M")
                rows.append(("Window",
                    f"ET 09:30~{et_end_s}  KST {s.strftime('%H:%M')}~{e.strftime('%H:%M')}  ({'DST' if is_dst else 'STD'})"))
            except Exception:
                pass

            # ICT phase flags
            ict_flags = []
            if strategy_info.get("qqq_primary"):
                ict_flags.append("QQQ-PRIMARY")
            if strategy_info.get("ict_killzone"):
                kz_list = strategy_info.get("ict_allowed_killzones") or []
                ict_flags.append("KZ(" + ",".join(kz_list) + ")" if kz_list else "KZ")
            for key, label in [
                ("ict_displacement", "Disp"),
                ("ict_sweep_choch", "Sweep"),
                ("ict_daily_bias", "Bias"),
                ("ict_bear_for_sqqq", "QQQ→SQQQ"),
                ("ict_bull_for_tqqq", "QQQ→TQQQ"),
                ("ict_unicorn", "Unicorn"),
                ("ict_mtf_sl", "MTF-SL"),
                ("ict_power_of_3", "P3"),
                ("ict_eqh_eql_pools", "EQH/EQL"),
                ("ict_session_pools", "SessionPools"),
                ("ict_premkt_history", "PremktHist"),
                ("ict_pdh_pdl_pool", "PDH/PDL"),
            ]:
                if strategy_info.get(key):
                    ict_flags.append(label)
            if strategy_info.get("ict_ote"):
                fib = strategy_info.get("ict_fib_level", 0.705)
                ict_flags.append(f"OTE({fib})")
            rows.append(("ICT", " + ".join(ict_flags) if ict_flags else "off"))

        self.send(self._box("🇺🇸 <b>미장봇 시작</b>", rows))

    def notify_bot_stopped(self, reason: str = "Graceful shutdown") -> None:
        self.send(self._box("🛑 <b>미장봇 종료</b>", [("Reason", reason)]))

    def notify_pre_market(self, vix: float, qqq_close: float, qqq_ma20: float,
                          trend: str, symbol: str,
                          dual_scan: bool = False) -> None:
        emoji = "📈" if trend == "BULL" else "📉"
        rows = [
            ("VIX", f"{vix:.1f}"),
            ("QQQ", f"${qqq_close:.2f}  vs MA20 ${qqq_ma20:.2f}"),
        ]
        if dual_scan:
            rows.append(("Trend", f"{trend}  (info only, dual scan)"))
        else:
            rows.append(("Trend", f"{trend} → {symbol}"))
        self.send(self._box(f"{emoji} <b>PRE-MARKET</b>", rows))

    def notify_orb(self, symbol: str, orb_high: float, orb_low: float,
                   orb_range: float) -> None:
        rows = [
            ("High", f"${orb_high:.2f}"),
            ("Low", f"${orb_low:.2f}"),
            ("Range", f"${orb_range:.2f}"),
        ]
        self.send(self._box(f"📊 <b>ORB</b>  {symbol}", rows))

    # ── ICT phase-aware decision notifications (added 2026-05-12) ─────

    def notify_daily_bias(self, bias) -> None:
        """Send Daily Bias (PDH/PDL/PWH/PWL + MA20/50 score) after pre-market."""
        if bias is None:
            return
        emoji = {"bull": "📈", "bear": "📉", "neutral": "⚖️"}.get(bias.direction, "📊")
        comps = "  ".join(f"{k}{v:+d}" if isinstance(v, int) else f"{k}={v}"
                          for k, v in bias.components.items())
        rows = [
            ("방향", f"{bias.direction.upper()}   score {bias.score:+d}"),
            ("PDH/PDL", f"${bias.pdh:.2f}  /  ${bias.pdl:.2f}"),
            ("PWH/PWL", f"${bias.pwh:.2f}  /  ${bias.pwl:.2f}"),
            ("Comps", comps),
        ]
        self.send(self._box(f"{emoji} <b>DAILY BIAS</b>", rows))

    def notify_orb_summary(self, orbs: dict) -> None:
        """Multi-symbol ORB summary (sent once when all legs finalised)."""
        if not orbs:
            return
        table_lines = [
            f"  {'Symbol':<6} {'High':>10} {'Low':>10} {'Range':>9}",
            "  " + "─" * 38,
        ]
        for symbol, orb in orbs.items():
            table_lines.append(
                f"  {symbol:<6} ${orb.high:>8.2f} ${orb.low:>8.2f} ${orb.range_size:>7.2f}"
            )
        header = "📊 <b>ORB Summary</b>  (15분)"
        body = "<pre>" + "\n".join([self._DIVIDER, *table_lines, self._DIVIDER]) + "</pre>"
        self.send(f"{header}\n{body}")

    def notify_scan_start(self, killzone_label: Optional[str] = None,
                          kst_window: Optional[str] = None,
                          rr_default: float = 3.0,
                          kz_segments: Optional[list] = None) -> None:
        """Notify that scan window is now open."""
        rows = []
        if killzone_label:
            rows.append(("Killzone", killzone_label))
        if kst_window:
            rows.append(("Window", kst_window))
        if kz_segments:
            rows.append("---")
            for seg in kz_segments:
                name = seg.get("name", "?")
                ks = seg.get("kst_start", "??:??")
                ke = seg.get("kst_end", "??:??")
                rr = seg.get("rr", rr_default)
                rows.append((name, f"KST {ks}~{ke}   R:R 1:{rr:g}"))
        footer = (
            "<i>ℹ 같은 setup이라도 breakout이 어느 zone에서 나오는지에 따라 TP 거리가 달라짐</i>"
            if kz_segments
            else "<i>이 시간 안에서만 진입 가능</i>"
        )
        self.send(self._box("🔍 <b>SCAN START</b>", rows, footer=footer))

    def notify_setup_detected(self, symbol: str, direction: str,
                               fvg_top: float, fvg_bot: float,
                               filters_active: Optional[list] = None) -> None:
        """A valid ICT setup formed; bot now waiting for pullback to FVG."""
        dir_emoji = "📈" if direction == "long" else "📉"
        rows = [
            ("Symbol", symbol),
            ("Direction", direction.upper()),
            ("FVG zone", f"${min(fvg_bot, fvg_top):.2f} ~ ${max(fvg_bot, fvg_top):.2f}"),
        ]
        if filters_active:
            rows.append(("Filters", ", ".join(filters_active)))
        footer = "<i>→ 가격이 FVG로 돌아오면 진입</i>"
        self.send(self._box(f"{dir_emoji} <b>SETUP</b>", rows, footer=footer))

    def notify_killzone_end_no_signal(self, killzone_label: str = "AM_MACRO",
                                       kst_window: Optional[str] = None,
                                       reasons: Optional[dict] = None) -> None:
        """End of allowed Killzone(s) with no entry."""
        rows = [("Zone", killzone_label)]
        if kst_window:
            rows.append(("Window", kst_window))
        if reasons:
            rows.append("---")
            for k, v in reasons.items():
                rows.append((k, f"{v}건"))
        footer = "<i>유효 setup 없음 — 오늘 매매 없이 종료</i>"
        self.send(self._box("⏰ <b>KILLZONE END</b>", rows, footer=footer))

    def notify_filter_reject(self, symbol: str, filter_name: str,
                              reason: str) -> None:
        """Verbose filter rejection (env-gated to avoid spam)."""
        rows = [
            ("Symbol", symbol),
            ("Filter", filter_name),
            ("Reason", reason),
        ]
        self.send(self._box("⏭ <b>FILTER</b>", rows))

    def notify_signal(self, symbol: str, entry: float, stop: float,
                      target: float, rr_ratio: float,
                      ict_meta: Optional[dict] = None) -> None:
        risk_ps = abs(entry - stop)
        reward_ps = abs(target - entry)
        rows = [
            ("Symbol", symbol),
            ("Entry", f"${entry:.2f}"),
            ("SL", f"${stop:.2f}    (-${risk_ps:.2f}/sh)"),
            ("TP", f"${target:.2f}   (+${reward_ps:.2f}/sh)"),
            ("R:R", f"1:{rr_ratio:g}"),
        ]
        if ict_meta:
            kz = ict_meta.get("killzone")
            filters = ict_meta.get("filters_active") or []
            bias = ict_meta.get("daily_bias_direction")
            bias_score = ict_meta.get("daily_bias_score")
            if kz or filters or bias is not None:
                rows.append("---")
            if kz:
                rows.append(("KZ", f"{kz}  →  R:R 1:{rr_ratio:g}"))
            if bias is not None:
                bias_str = (f"{bias} ({bias_score:+d})"
                            if bias_score is not None else str(bias))
                rows.append(("Bias", bias_str))
            if filters:
                rows.append(("Filters", ", ".join(filters)))
        self.send(self._box("🎯 <b>SIGNAL</b>", rows))

    def notify_entry(self, symbol: str, price: float, shares: int,
                     stop: float, target: float, risk: float,
                     rr_ratio: float = 3.0,
                     killzone: Optional[str] = None,
                     bucket_cap_usd: float = 0.0) -> None:
        """Trade entry — critical (queued on network failure during trade).

        bucket_cap_usd: when > 0, render ‘Position $X of $cap’ so the
        operator immediately sees how much of the Casper bucket cap was
        consumed. Pulled from CASPER_MAX_POSITION_USD env upstream.
        """
        risk_total = risk * shares
        reward_ps = abs(target - price)
        reward_total = reward_ps * shares
        total_cost = price * shares
        if bucket_cap_usd > 0:
            usage_pct = (total_cost / bucket_cap_usd * 100)
            position_str = (
                f"{shares}주 × ${price:.2f} = ${total_cost:,.2f}  "
                f"/ cap ${bucket_cap_usd:,.0f}  ({usage_pct:.1f}%)"
            )
        else:
            position_str = f"{shares}주 × ${price:.2f} = ${total_cost:,.2f}"
        rows = [
            ("Symbol", symbol),
            ("Position", position_str),
            ("SL", f"${stop:.2f}   risk ${risk:.2f}/sh  (-${risk_total:.2f})"),
            ("TP", f"${target:.2f}  reward ${reward_ps:.2f}/sh  (+${reward_total:.2f})"),
            ("R:R", f"1:{rr_ratio:g}" + (f"   KZ: {killzone}" if killzone else "")),
        ]
        self.send(self._box("🟢 <b>ENTRY</b>", rows), critical=True)

    def notify_partial_close(self, symbol: str, tp1_price: float,
                              shares_sold: int, shares_remaining: int,
                              partial_pnl: float, old_sl: float,
                              new_sl: float, tp2_price: float) -> None:
        """Partial TP1 fill — 50% close + SL moved to ORB.high (free trade)."""
        sl_delta = new_sl - old_sl
        rows = [
            ("Symbol", symbol),
            ("TP1 fill", f"{shares_sold}주 @ ${tp1_price:.2f}  →  +${partial_pnl:+.2f}"),
            ("Remaining", f"{shares_remaining}주 보유"),
            ("SL move", f"${old_sl:.2f} → ${new_sl:.2f}  (Δ {sl_delta:+.2f}, free trade)"),
            ("TP2", f"${tp2_price:.2f}"),
        ]
        self.send(self._box("🟡 <b>PARTIAL CLOSE</b>", rows), critical=True)

    def notify_be_move(self, symbol: str, old_sl: float, new_sl: float) -> None:
        rows = [
            ("Symbol", symbol),
            ("SL move", f"${old_sl:.2f} → ${new_sl:.2f}"),
        ]
        self.send(self._box("🟡 <b>BE MOVE</b>", rows))

    def notify_exit(self, symbol: str, entry: float, exit_price: float,
                    reason: str, net_pnl: float, result: str) -> None:
        """Trade exit — critical (queued on network failure during trade)."""
        emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(result, "❓")
        pct = (exit_price - entry) / entry * 100 if entry else 0
        rows = [
            ("Symbol", symbol),
            ("Reason", reason),
            ("Price", f"${entry:.2f} → ${exit_price:.2f}  ({pct:+.2f}%)"),
            ("Net P&L", f"${net_pnl:+.2f}   ({result})"),
        ]
        self.send(self._box(f"{emoji} <b>EXIT</b>", rows), critical=True)

    def notify_order_failed(self, symbol: str, side: str, qty: int, reason: str) -> None:
        """Order failure — critical."""
        rows = [
            ("Side", side.upper()),
            ("Symbol", symbol),
            ("Qty", f"{qty}주"),
            ("Reason", reason),
        ]
        self.send(self._box("🚨 <b>ORDER FAILED</b>", rows), critical=True)

    def notify_skip(self, reason: str) -> None:
        self.send(self._box("⏭ <b>SKIP</b>", [("Reason", reason)]))

    def notify_daily_summary(self, today_trade: Optional[dict],
                             cumulative: dict, capital: float) -> None:
        """End-of-day comprehensive summary."""
        rows = []
        if today_trade:
            r = today_trade.get("result", "?")
            emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(r, "❓")
            rows.append(("Today", f"{emoji} {today_trade.get('symbol', '?')}  "
                                  f"{today_trade.get('reason', '?')}"))
            rows.append(("P&L", f"${today_trade.get('net', 0):+.2f}   "
                                f"R {today_trade.get('r', 0):+.2f}"))
        else:
            rows.append(("Today", "No trade"))
        rows.append("---")
        rows.append(("Capital", f"${capital:,.2f}"))
        rows.append(("Cum trades", f"{cumulative.get('total', 0)} (WR {cumulative.get('wr', 0):.1f}%)"))
        rows.append(("Cum PF", f"{cumulative.get('pf', 0):.2f}"))
        rows.append(("Cum PnL", f"${cumulative.get('pnl', 0):+,.2f}"))
        self.send(self._box("📋 <b>DAILY SUMMARY</b>", rows))

    # ── Portfolio / GEM / Bucket lifecycle ──────────────────────────────
    # These messages are NOT critical (no in-trade queueing). Sent on a
    # best-effort basis at scheduled tick points (daily new-day reset,
    # month-end signal, quarter-end drift check).

    def notify_gem_signal(self, signal_date: str, target: str,
                          us_ret: float, exus_ret: float, bill_ret: float,
                          reason: str, mode: str = "alert") -> None:
        """GEM (Antonacci) monthly signal.

        mode='alert' → P1 behavior: signal detected, NO order placed.
        mode='auto'  → P2 behavior: signal detected, order on next open.
        """
        target_label = {
            "SPY": "SPY  (S&P 500)",
            "VEU": "VEU  (ex-US 전세계)",
            "AGG": "AGG  (미국 종합채권)",
        }.get(target, target)

        # Mark the winning leg with an arrow
        winner = "US" if us_ret > exus_ret and max(us_ret, exus_ret) > bill_ret else \
                 "ExUS" if exus_ret > us_ret and max(us_ret, exus_ret) > bill_ret else "Bond"
        spy_mark = "  ← 선택" if winner == "US" else ""
        veu_mark = "  ← 선택" if winner == "ExUS" else ""
        bond_mark = "  ← 선택" if winner == "Bond" else ""

        rows = [
            ("선택", target_label),
            ("SPY 12m", f"{us_ret*100:+6.2f}%{spy_mark}"),
            ("VEU 12m", f"{exus_ret*100:+6.2f}%{veu_mark}"),
            ("BIL 12m", f"{bill_ret*100:+6.2f}%{bond_mark}"),
            "---",
            ("판정", reason),
            ("실행", "🤖 다음 시가 자동 매매" if mode == "auto" else "📋 수동 매매 필요 (alert)"),
        ]
        self.send(self._box(f"🌐 <b>GEM 신호</b>  {signal_date}", rows))

    def notify_gem_executed(self, action: str, symbol: str, qty: int,
                            price: float, prev_symbol: Optional[str] = None) -> None:
        """GEM auto-execution result. action ∈ {SELL, BUY, HOLD, SKIP}."""
        emoji = {"SELL": "🔴", "BUY": "🟢", "HOLD": "⚪️", "SKIP": "⏭"}.get(action, "ℹ️")
        title = f"{emoji} <b>GEM {action}</b>"
        rows = [
            ("종목", symbol),
            ("수량", f"{qty}주"),
            ("단가", f"${price:.2f}"),
            ("총액", f"${price * qty:,.2f}"),
        ]
        if prev_symbol and prev_symbol != symbol:
            rows.append(("회전", f"{prev_symbol} → {symbol}"))
        self.send(self._box(title, rows))

    def notify_portfolio_summary(self, total_usd: float, buckets: list,
                                 tier_key: str,
                                 casper_cap_usd: float = 0.0) -> None:
        """Daily portfolio snapshot — total value + per-bucket allocation.

        Renders a compact aligned table inside a <pre> block so columns
        line up on both mobile and desktop Telegram clients.

        casper_cap_usd: env-driven CASPER_MAX_POSITION_USD. When > 0 the
        Casper row gets a ‘cap $N’ annotation so the operator can see
        the per-trade limit alongside the bucket value.
        """
        # Build the bucket table as a single multi-line "row" so column
        # alignment is exact (we control the widths ourselves).
        table_lines = [
            f"  {'Bucket':<8} {'Symbol':<6} {'Current':>11} {'Target':>11}  Drift",
            "  " + "─" * 47,
        ]
        for b in buckets:
            arrow = "↑" if b.drift_pct > 0.001 else ("↓" if b.drift_pct < -0.001 else "•")
            sym = b.current_symbol or "—"
            line = (
                f"  {b.name:<8} {sym:<6} "
                f"${b.current_value_usd:>9,.2f} ${b.target_usd:>9,.2f}  "
                f"{arrow} {b.drift_pct*100:+5.1f}%"
            )
            # Casper row annotation: per-trade cap from CASPER_MAX_POSITION_USD env
            if b.name == "casper" and casper_cap_usd > 0:
                line += f"   cap ${casper_cap_usd:,.0f}"
            table_lines.append(line)

        # Header (outside <pre>) then the table (inside <pre>) for alignment
        header = f"💼 <b>포트폴리오</b>  ${total_usd:,.2f}"
        body = "<pre>" + "\n".join([
            self._DIVIDER,
            *table_lines,
            self._DIVIDER,
        ]) + "</pre>"
        # `Target` 의 의미를 footer 에 명시: 매도 트리거가 아니라 자본 규모 기반
        # 목표 배분액. Drift 는 그 배분 대비 편차 (분기말 ±10% 초과 시 리밸런스).
        legend = (
            "<i>Current=평가금액(현재가×수량) · "
            "Target=목표배분(자본×weight, 매도가 아님) · "
            "Drift=배분편차(분기말 ±10%↑ 리밸런스)</i>"
        )
        footer = f"{legend}\n<i>Tier: {tier_key}</i>"
        self.send(f"{header}\n{body}\n{footer}")

    def notify_tier_change(self, prev_tier: Optional[str], new_tier: str,
                           total_usd: float) -> None:
        """Capital tier transition (e.g., $4,950 → $5,100 enables MTUM/QUAL)."""
        rows = [
            ("Total", f"${total_usd:,.2f}"),
            "---",
            ("Prev", prev_tier or "(none)"),
            ("New", new_tier),
        ]
        footer = "<i>다음 분기말 리밸런스에 새 비중 적용</i>"
        self.send(self._box("🎯 <b>Tier 변경</b>", rows, footer=footer))

    def notify_bucket_drift(self, buckets_drifted: list, today: str) -> None:
        """Quarter-end drift candidates — sent BEFORE rebalance executes."""
        if not buckets_drifted:
            return
        # Use a hand-rolled table so columns line up
        table_lines = [
            f"  {'Bucket':<8} {'Current':>11} {'Target':>11}  Drift",
            "  " + "─" * 42,
        ]
        for b in buckets_drifted:
            table_lines.append(
                f"  {b.name:<8} "
                f"${b.current_value_usd:>9,.2f} ${b.target_usd:>9,.2f}  "
                f"{b.drift_pct*100:+5.1f}%"
            )
        header = f"⚖️ <b>Bucket Drift</b>  {today}"
        body = "<pre>" + "\n".join([
            self._DIVIDER, *table_lines, self._DIVIDER,
        ]) + "</pre>"
        self.send(f"{header}\n{body}")

    def notify_etf_rebalance(self, side: str, symbol: str, qty: int,
                             price: float, bucket: str, reason: str) -> None:
        """ETF buy/sell executed for a non-Casper bucket (SPMO/GEM/etc.)."""
        emoji = "🟢" if side.lower() == "buy" else "🔴"
        side_kr = "매수" if side.lower() == "buy" else "매도"
        title = f"{emoji} <b>{side_kr}</b>  {bucket.upper()} bucket"
        rows = [
            ("종목", symbol),
            ("수량", f"{qty}주"),
            ("단가", f"${price:.2f}"),
            ("총액", f"${price * qty:,.2f}"),
            ("사유", reason),
        ]
        self.send(self._box(title, rows))

    # ── Errors ──────────────────────────────────────────────────────────

    def notify_error(self, error: str) -> None:
        """Notify a non-network error.

        The caller is expected to filter network-class errors out before
        calling — see _is_network_error_text() helper for callers that
        receive raw error strings.
        """
        if _is_network_error_text(error):
            return  # Per spec: never alert on network errors
        self.send(self._box("🚨 <b>ERROR</b>", [("Detail", error)]))

    # ── Initial seed lifecycle (P0 multi-bucket bootstrap) ───────────

    def notify_seed_start(self, total_usd: float) -> None:
        """Initial seed begins — sent before any buy orders fire."""
        self.send(self._box(
            "🎬 <b>Initial Seed</b>",
            [
                ("Total", f"${total_usd:,.2f}"),
                ("Status", "다중 bucket 자동 매수 시작"),
            ],
        ))

    def notify_seed_complete(self, bought: list) -> None:
        """Initial seed finished.

        bought: list of (bucket_name, symbol, qty, price) tuples.
        """
        if not bought:
            rows = [("결과", "매수된 bucket 없음 (로그 확인 권장)")]
            self.send(self._box("⚠️ <b>Seed 미완료</b>", rows))
            return
        table_lines = [
            f"  {'Bucket':<8} {'Symbol':<6} {'Qty':>4}   {'Price':>9}   {'Total':>11}",
            "  " + "─" * 49,
        ]
        grand_total = 0.0
        for bucket, sym, qty, px in bought:
            line_total = qty * px
            grand_total += line_total
            table_lines.append(
                f"  {bucket:<8} {sym:<6} {qty:>4}주  ${px:>7.2f}   ${line_total:>9,.2f}"
            )
        table_lines.append("  " + "─" * 49)
        table_lines.append(f"  {'Total':<8} {'':<6} {'':>4}    {'':>7}    ${grand_total:>9,.2f}")
        header = "✅ <b>Seed 완료</b>"
        body = "<pre>" + "\n".join([self._DIVIDER, *table_lines, self._DIVIDER]) + "</pre>"
        self.send(f"{header}\n{body}")


def _is_network_error_text(text: str) -> bool:
    """Heuristic: does this error message describe a network-layer failure?"""
    s = text.lower()
    needles = (
        "timeout", "timed out",
        "connection", "connect ",
        "read timed",
        "network", "unreachable",
        "ssl", "remote disconnect", "incomplete read",
        "max retries exceeded", "name resolution", "getaddrinfo",
    )
    return any(n in s for n in needles)
