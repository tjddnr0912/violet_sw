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

    # ── High-level notifications ────────────────────────────────────────

    def notify_bot_started(self, mode: str, capital: float, history: dict,
                           strategy_info: dict = None) -> None:
        lines = [f"🤖 <b>BOT STARTED</b>", f"Mode: {mode.upper()}"]
        if strategy_info:
            scan = "DUAL (TQQQ+SQQQ)" if strategy_info.get("dual_scan") else "TREND (QQQ MA20)"
            fvg = "STRICT" if strategy_info.get("strict_fvg") else "baseline"
            rr = strategy_info.get("rr_ratio", 2.0)
            rr_map = strategy_info.get("rr_ratio_by_killzone") or {}
            if rr_map:
                rr_summary = " / ".join(f"{k}=1:{v:g}" for k, v in rr_map.items())
                lines.append(f"Scan: {scan}  FVG: {fvg}")
                lines.append(f"R:R: default 1:{rr:g}  ({rr_summary})")
            else:
                lines.append(f"Scan: {scan}  FVG: {fvg}  R:R: 1:{rr:g}")
            # ICT phase flags (compact)
            ict_flags = []
            if strategy_info.get("qqq_primary"):
                ict_flags.append("QQQ-PRIMARY")
            if strategy_info.get("ict_killzone"):
                kz_list = strategy_info.get("ict_allowed_killzones") or []
                ict_flags.append("KZ(" + ",".join(kz_list) + ")" if kz_list else "KZ")
            if strategy_info.get("ict_displacement"):
                ict_flags.append("Disp")
            if strategy_info.get("ict_sweep_choch"):
                ict_flags.append("Sweep")
            if strategy_info.get("ict_daily_bias"):
                ict_flags.append("Bias")
            if strategy_info.get("ict_bear_for_sqqq"):
                ict_flags.append("QQQ→SQQQ")
            if strategy_info.get("ict_bull_for_tqqq"):
                ict_flags.append("QQQ→TQQQ")
            if strategy_info.get("ict_ote"):
                fib = strategy_info.get("ict_fib_level", 0.705)
                ict_flags.append(f"OTE({fib})")
            if strategy_info.get("ict_unicorn"):
                ict_flags.append("Unicorn")
            if strategy_info.get("ict_mtf_sl"):
                ict_flags.append("MTF-SL")
            if strategy_info.get("ict_power_of_3"):
                ict_flags.append("P3")
            if strategy_info.get("ict_eqh_eql_pools"):
                ict_flags.append("EQH/EQL")
            if strategy_info.get("ict_session_pools"):
                ict_flags.append("SessionPools")
            if strategy_info.get("ict_premkt_history"):
                ict_flags.append("PremktHist")
            if strategy_info.get("ict_pdh_pdl_pool"):
                ict_flags.append("PDH/PDL")
            if ict_flags:
                lines.append("ICT: " + " + ".join(ict_flags))
                # DST-aware KST window line — honours allowed killzones
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
                    lines.append(
                        f"Window: ET 09:30-{et_end_s} (KST {s.strftime('%H:%M')}-{e.strftime('%H:%M')}, "
                        f"{'DST' if is_dst else 'STD'})"
                    )
                    # Per-killzone breakdown when allowed_killzones has 2+ entries
                    if strategy_info.get("ict_killzone") and len(allowed) >= 2:
                        for k in allowed:
                            if k not in KILLZONES:
                                continue
                            zs, ze = KILLZONES[k]
                            zs_kst = et.localize(datetime.combine(today_et.date(), zs)).astimezone(kst).strftime("%H:%M")
                            ze_kst = et.localize(datetime.combine(today_et.date(), ze)).astimezone(kst).strftime("%H:%M")
                            rr_for_k = rr_map.get(k, rr) if rr_map else rr
                            lines.append(
                                f"  • {k}: KST {zs_kst}-{ze_kst}  RR=1:{rr_for_k:g}"
                            )
                except Exception:
                    pass
            else:
                lines.append("ICT: off")
        lines.append(f"Capital: ${capital:.2f}")
        lines.append(
            f"History: {history.get('count', 0)}T  "
            f"WR {history.get('win_rate', 0):.1f}%  "
            f"PnL ${history.get('pnl', 0):+.2f}"
        )
        self.send("\n".join(lines))

    def notify_bot_stopped(self, reason: str = "Graceful shutdown") -> None:
        self.send(f"🛑 <b>BOT STOPPED</b>\n{reason}")

    def notify_pre_market(self, vix: float, qqq_close: float, qqq_ma20: float,
                          trend: str, symbol: str,
                          dual_scan: bool = False) -> None:
        emoji = "📈" if trend == "BULL" else "📉"
        if dual_scan:
            trend_line = f"Trend (info only): {trend} — dual scan ignores this for entry"
        else:
            trend_line = f"Trend: {trend} → {symbol}"
        msg = (
            f"{emoji} <b>PRE-MARKET</b>\n"
            f"VIX: {vix:.1f}\n"
            f"QQQ: {qqq_close:.2f} vs MA20 {qqq_ma20:.2f}\n"
            f"{trend_line}"
        )
        self.send(msg)

    def notify_orb(self, symbol: str, orb_high: float, orb_low: float,
                   orb_range: float) -> None:
        msg = (
            f"📊 <b>ORB</b> {symbol}\n"
            f"H ${orb_high:.2f}  L ${orb_low:.2f}  Range ${orb_range:.2f}"
        )
        self.send(msg)

    # ── ICT phase-aware decision notifications (added 2026-05-12) ─────

    def notify_daily_bias(self, bias) -> None:
        """Send Daily Bias (PDH/PDL/PWH/PWL + MA20/50 score) after pre-market."""
        if bias is None:
            return
        emoji = {"bull": "📈", "bear": "📉", "neutral": "⚖️"}.get(bias.direction, "📊")
        comps = ", ".join(f"{k}{v:+d}" if isinstance(v, int) else f"{k}={v}"
                          for k, v in bias.components.items())
        msg = (
            f"{emoji} <b>DAILY BIAS</b>\n"
            f"방향: {bias.direction.upper()}  score={bias.score:+d}\n"
            f"PDH ${bias.pdh:.2f}  PDL ${bias.pdl:.2f}\n"
            f"PWH ${bias.pwh:.2f}  PWL ${bias.pwl:.2f}\n"
            f"comp: {comps}"
        )
        self.send(msg)

    def notify_orb_summary(self, orbs: dict) -> None:
        """Multi-symbol ORB summary (sent once when all legs finalised)."""
        if not orbs:
            return
        lines = ["📊 <b>ORB SUMMARY</b>"]
        for symbol, orb in orbs.items():
            lines.append(
                f"  {symbol:5s}: H ${orb.high:.2f}  L ${orb.low:.2f}  "
                f"R ${orb.range_size:.2f}"
            )
        self.send("\n".join(lines))

    def notify_scan_start(self, killzone_label: Optional[str] = None,
                          kst_window: Optional[str] = None,
                          rr_default: float = 3.0,
                          kz_segments: Optional[list] = None) -> None:
        """Notify that scan window is now open.

        kz_segments: optional list of dicts with keys
          name, kst_start, kst_end, rr — one entry per allowed killzone.
          When supplied, the message renders each zone on its own line
          with the RR that will apply to setups originating in that zone.
        """
        lines = ["🔍 <b>SCAN START</b>"]
        if killzone_label:
            lines.append(f"Killzone: {killzone_label}")
        if kst_window:
            lines.append(f"Window: {kst_window}")
        if kz_segments:
            lines.append("─" * 18)
            lines.append("진입 구간별 RR (breakout 캔들 시각 기준):")
            for seg in kz_segments:
                name = seg.get("name", "?")
                ks = seg.get("kst_start", "??:??")
                ke = seg.get("kst_end", "??:??")
                rr = seg.get("rr", rr_default)
                lines.append(f"  • {name}: KST {ks}~{ke}  →  RR 1:{rr:g}")
            lines.append("─" * 18)
            lines.append(
                "ℹ️ 같은 setup이라도 breakout이 어느 zone에서 나오는지에 따라 TP 거리가 달라짐."
            )
        else:
            lines.append("(이 시간 안에서만 진입 가능)")
        self.send("\n".join(lines))

    def notify_setup_detected(self, symbol: str, direction: str,
                               fvg_top: float, fvg_bot: float,
                               filters_active: Optional[list] = None) -> None:
        """A valid ICT setup formed; bot now waiting for pullback to FVG.

        Distinct from notify_signal — this fires BEFORE pullback (i.e.
        the signal is recognised but entry hasn't triggered yet).
        """
        dir_emoji = "📈" if direction == "long" else "📉"
        zone = f"${min(fvg_bot, fvg_top):.2f}~${max(fvg_bot, fvg_top):.2f}"
        msg = (
            f"{dir_emoji} <b>SETUP</b> {symbol} ({direction})\n"
            f"FVG zone: {zone}\n"
            f"→ 가격이 FVG로 돌아오면 진입"
        )
        if filters_active:
            msg += f"\nfilters: {','.join(filters_active)}"
        self.send(msg)

    def notify_killzone_end_no_signal(self, killzone_label: str = "AM_MACRO",
                                       kst_window: Optional[str] = None,
                                       reasons: Optional[dict] = None) -> None:
        """End of allowed Killzone(s) with no entry.

        reasons: optional dict like {"killzone_reject": 3, "displacement_fail": 1, ...}
                 to give the operator a hint of WHY today produced no trade.
        """
        lines = [f"⏰ <b>KILLZONE END</b>", f"종료된 zone: {killzone_label}"]
        if kst_window:
            lines.append(f"Window: {kst_window}")
        lines.append("유효 setup 없음 — 오늘 매매 없이 종료")
        if reasons:
            lines.append("─" * 18)
            lines.append("탈락 사유 분포:")
            for k, v in reasons.items():
                lines.append(f"  • {k}: {v}건")
        self.send("\n".join(lines))

    def notify_filter_reject(self, symbol: str, filter_name: str,
                              reason: str) -> None:
        """Verbose filter rejection (env-gated to avoid spam)."""
        msg = (
            f"⏭ <b>FILTER</b> {symbol}\n"
            f"{filter_name}: {reason}"
        )
        self.send(msg)

    def notify_signal(self, symbol: str, entry: float, stop: float,
                      target: float, rr_ratio: float,
                      ict_meta: Optional[dict] = None) -> None:
        risk_ps = abs(entry - stop)
        reward_ps = abs(target - entry)
        lines = [
            f"🎯 <b>SIGNAL</b> {symbol}",
            f"Entry ${entry:.2f}  SL ${stop:.2f}  TP ${target:.2f}",
            f"Risk ${risk_ps:.2f}/sh  Reward ${reward_ps:.2f}/sh  R:R 1:{rr_ratio:g}",
        ]
        if ict_meta:
            kz = ict_meta.get("killzone")
            filters = ict_meta.get("filters_active") or []
            bias = ict_meta.get("daily_bias_direction")
            bias_score = ict_meta.get("daily_bias_score")
            extras = []
            if kz:
                # Annotate WHY this RR was chosen (Scenario B)
                extras.append(f"KZ:{kz}→RR=1:{rr_ratio:g}")
            if filters:
                extras.append("filters:" + ",".join(filters))
            if bias is not None:
                extras.append(f"bias:{bias}({bias_score:+d})"
                              if bias_score is not None else f"bias:{bias}")
            if extras:
                lines.append("ICT  " + "  ".join(extras))
        self.send("\n".join(lines))

    def notify_entry(self, symbol: str, price: float, shares: int,
                     stop: float, target: float, risk: float,
                     rr_ratio: float = 3.0,
                     killzone: Optional[str] = None) -> None:
        """Trade entry — critical (queued on network failure during trade)."""
        risk_total = risk * shares
        reward_total = abs(target - price) * shares
        kz_line = f"\nKZ: {killzone}  →  R:R 1:{rr_ratio:g}" if killzone else f"\nR:R 1:{rr_ratio:g}"
        msg = (
            f"🟢 <b>ENTRY</b> {symbol}\n"
            f"${price:.2f} × {shares}sh = ${price * shares:.2f}\n"
            f"SL ${stop:.2f}  TP ${target:.2f}\n"
            f"Risk ${risk:.2f}/sh (${risk_total:.2f} total)\n"
            f"Reward ${abs(target - price):.2f}/sh (${reward_total:.2f} total)"
            f"{kz_line}"
        )
        self.send(msg, critical=True)

    def notify_partial_close(self, symbol: str, tp1_price: float,
                              shares_sold: int, shares_remaining: int,
                              partial_pnl: float, old_sl: float,
                              new_sl: float, tp2_price: float) -> None:
        """Partial TP1 fill — 50% close + SL moved to ORB.high (free trade).

        Sent on TP1 hit. Critical: queue on network failure during trade.
        """
        sl_delta = new_sl - old_sl
        msg = (
            f"🟡 <b>PARTIAL CLOSE</b> {symbol}\n"
            f"TP1 ${tp1_price:.2f} × {shares_sold}sh = +${partial_pnl:+.2f}\n"
            f"Remaining: {shares_remaining}sh @ entry\n"
            f"SL ${old_sl:.2f} → ${new_sl:.2f} (Δ {sl_delta:+.2f}, free trade)\n"
            f"TP2 still ${tp2_price:.2f}"
        )
        self.send(msg, critical=True)

    def notify_be_move(self, symbol: str, old_sl: float, new_sl: float) -> None:
        msg = (
            f"🟡 <b>BE MOVE</b> {symbol}\n"
            f"SL ${old_sl:.2f} → ${new_sl:.2f}"
        )
        self.send(msg)

    def notify_exit(self, symbol: str, entry: float, exit_price: float,
                    reason: str, net_pnl: float, result: str) -> None:
        """Trade exit — critical (queued on network failure during trade)."""
        emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(result, "❓")
        msg = (
            f"{emoji} <b>EXIT</b> {symbol} ({reason})\n"
            f"${entry:.2f} → ${exit_price:.2f}\n"
            f"Net P&L ${net_pnl:+.2f}  ({result})"
        )
        self.send(msg, critical=True)

    def notify_order_failed(self, symbol: str, side: str, qty: int, reason: str) -> None:
        """Order failure — critical."""
        msg = (
            f"🚨 <b>ORDER FAILED</b>\n"
            f"{side.upper()} {symbol} × {qty}\n"
            f"{reason}"
        )
        self.send(msg, critical=True)

    def notify_skip(self, reason: str) -> None:
        self.send(f"⏭ <b>SKIP</b> {reason}")

    def notify_daily_summary(self, today_trade: Optional[dict],
                             cumulative: dict, capital: float) -> None:
        """End-of-day comprehensive summary."""
        lines = ["📋 <b>DAILY SUMMARY</b>"]
        if today_trade:
            r = today_trade.get("result", "?")
            emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(r, "❓")
            lines.append(
                f"{emoji} Today: {today_trade.get('symbol', '?')} "
                f"{today_trade.get('reason', '?')}  "
                f"P&L ${today_trade.get('net', 0):+.2f}  R={today_trade.get('r', 0):+.2f}"
            )
        else:
            lines.append("No trade today")
        lines.append(
            f"Capital: ${capital:.2f}\n"
            f"Cum: {cumulative.get('total', 0)}T  "
            f"WR {cumulative.get('wr', 0):.1f}%  "
            f"PF {cumulative.get('pf', 0):.2f}  "
            f"PnL ${cumulative.get('pnl', 0):+.2f}"
        )
        self.send("\n".join(lines))

    # ── Errors ──────────────────────────────────────────────────────────

    def notify_error(self, error: str) -> None:
        """Notify a non-network error.

        The caller is expected to filter network-class errors out before
        calling — see _is_network_error_text() helper for callers that
        receive raw error strings.
        """
        if _is_network_error_text(error):
            return  # Per spec: never alert on network errors
        self.send(f"🚨 <b>ERROR</b>\n{error}")


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
