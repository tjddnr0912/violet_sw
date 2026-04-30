#!/usr/bin/env python3
"""
Casper Dual-Scan vs Trend-Filter Comparison Backtest
=====================================================
A/B comparison of two symbol-selection modes, all else equal:

  MODE A — trend (existing _current strategy):
    QQQ daily MA20 → BULL/BEAR → trade ONE symbol that day.

  MODE B — dual-scan (proposed):
    Both TQQQ and SQQQ are scanned in parallel from open. ORB is computed
    for each. Whichever forms a valid signal AND pulls back first wins
    the day's single trade. No pre-market direction commitment.

Fairness:
  Same data, same filters (VIX, ORB width, holidays), same exit logic
  (R:R 1:2, BE at 11:00, force close 15:50), same circuit breaker, same
  position sizing. Only the symbol-selection step differs.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf
import pandas as pd
from datetime import time as dtime
import warnings
warnings.filterwarnings('ignore')

import pytz

from src.core.orb import calculate_orb, is_orb_too_wide
from src.core.fvg import check_breakout_with_fvg  # noqa: F401
from src.core.strategy import scan_for_signal, check_pullback, TradeSignal
from src.core.position import (
    create_position, check_exit, move_stop_to_breakeven, close_position
)
from src.core.risk import check_vix_filter, determine_trend, CircuitBreaker
import logging
logging.disable(logging.CRITICAL)

BULL_SYMBOL = "TQQQ"
BEAR_SYMBOL = "SQQQ"
TREND_SYMBOL = "QQQ"
# Asymmetric commission — user's real account (no benefit):
#   buy:  0.25% (거래소 수수료)
#   sell: 0.25% + 0.15% (농어촌세 매도시) = 0.40%
# Override via env BT_BUY_RATE / BT_SELL_RATE for sensitivity analysis.
BUY_RATE = float(os.environ.get("BT_BUY_RATE", "0.0025"))
SELL_RATE = float(os.environ.get("BT_SELL_RATE", "0.0040"))
# COMMISSION_RATE used only by Position dataclass for BE-move calculation;
# pick the buy rate (entry side) so BE doesn't undershoot.
COMMISSION_RATE = BUY_RATE
# R:R override for sensitivity analysis
RR_RATIO = float(os.environ.get("BT_RR_RATIO", "2.0"))
INITIAL_CAPITAL = 500.0
VIX_LOW = 12.0
VIX_HIGH = 30.0
MA_PERIOD = 20
CIRCUIT_BREAKER_LOSSES = 3
MAX_WEEKLY_LOSS_PCT = 3.0
MIN_RISK_DOLLAR = 0.10
MAX_SHARES = 200
MAX_POSITION_PCT = 1.0
ORB_ATR_MAX_RATIO = 1.5
ET = pytz.timezone("US/Eastern")


def fetch_data():
    print("[data] downloading...")
    tqqq_5m = yf.Ticker(BULL_SYMBOL).history(period="60d", interval="5m")
    sqqq_5m = yf.Ticker(BEAR_SYMBOL).history(period="60d", interval="5m")
    qqq_d = yf.Ticker(TREND_SYMBOL).history(period="6mo", interval="1d")
    tqqq_d = yf.Ticker(BULL_SYMBOL).history(period="6mo", interval="1d")
    sqqq_d = yf.Ticker(BEAR_SYMBOL).history(period="6mo", interval="1d")
    vix_d = yf.Ticker("^VIX").history(period="6mo", interval="1d")

    tqqq_5m.index = tqqq_5m.index.tz_convert("US/Eastern")
    sqqq_5m.index = sqqq_5m.index.tz_convert("US/Eastern")
    qqq_d["MA20"] = qqq_d["Close"].rolling(MA_PERIOD).mean()
    return tqqq_5m, sqqq_5m, qqq_d, tqqq_d, sqqq_d, vix_d


def find_first_pullback(signal: TradeSignal, day_data, post_orb):
    """Return the timestamp of the first pullback bar after the signal, or None."""
    if signal is None:
        return None
    sig_time = pd.Timestamp(signal.signal_time)
    if sig_time.tzinfo is None:
        sig_time = ET.localize(sig_time)

    # Search post_orb bars after signal_time
    for j in range(len(post_orb)):
        ts = post_orb.index[j]
        if ts <= sig_time:
            continue
        if check_pullback(post_orb.iloc[j], signal.fvg):
            return ts

    # Then search after_signal bars (15:50 cutoff)
    after = day_data.between_time("09:45", "15:50")
    for j in range(len(after)):
        ts = after.index[j]
        if ts <= sig_time:
            continue
        if check_pullback(after.iloc[j], signal.fvg):
            return ts
    return None


def evaluate_symbol(day_data, sym, sym_daily, day, skip_reasons):
    """Return (signal, pullback_time) or (None, None) with skip reason recorded."""
    if len(day_data) == 0:
        skip_reasons["no_orb"] += 1
        return None, None

    orb = calculate_orb(day_data)
    if orb is None:
        skip_reasons["no_orb"] += 1
        return None, None

    recent = sym_daily[sym_daily.index.date <= day].tail(20)
    if len(recent) >= 10:
        adr = float((recent["High"] - recent["Low"]).mean())
        if is_orb_too_wide(orb, adr, ORB_ATR_MAX_RATIO):
            skip_reasons["orb_wide"] += 1
            return None, None

    post_orb = day_data.between_time("09:45", "10:55")
    if len(post_orb) < 4:
        skip_reasons["no_signal"] += 1
        return None, None

    signal = scan_for_signal(
        post_orb, orb, sym,
        rr_ratio=RR_RATIO, min_risk=MIN_RISK_DOLLAR,
    )
    if signal is None:
        skip_reasons["no_signal"] += 1
        return None, None

    pb_time = find_first_pullback(signal, day_data, post_orb)
    if pb_time is None:
        skip_reasons["no_signal"] += 1
        return None, None
    return signal, pb_time


def run_one_position(signal, pb_time, day_data, capital):
    """Simulate position from entry to exit. Returns (trade_dict, capital_after)."""
    price = signal.entry_price
    shares = int(capital / price) if price > 0 else 0
    shares = min(shares, MAX_SHARES, int(capital * MAX_POSITION_PCT / price) if price > 0 else 0)
    if shares < 1:
        return None, capital

    entry_time_str = pb_time.strftime("%H:%M")
    position = create_position(signal, shares, COMMISSION_RATE, entry_time_str)

    pos_bars = day_data[day_data.index >= pb_time]
    exit_price = None
    exit_reason = None
    bt = pb_time
    for k in range(len(pos_bars)):
        bar = pos_bars.iloc[k]
        bt = pos_bars.index[k]
        ct = bt.time()
        if ct >= dtime(11, 0):
            move_stop_to_breakeven(position)
        if ct >= dtime(15, 50):
            exit_price = bar["Close"]
            exit_reason = "time_force"
            break
        reason = check_exit(position, bar["High"], bar["Low"], bar["Close"])
        if reason:
            if "stop" in reason:
                exit_price = position.stop_loss
            elif reason == "take_profit":
                exit_price = position.take_profit
            else:
                exit_price = bar["Close"]
            exit_reason = reason
            break
    if exit_price is None:
        exit_price = pos_bars.iloc[-1]["Close"]
        exit_reason = "eod"

    exit_time_str = pos_bars.index[-1].strftime("%H:%M") if exit_reason == "eod" else bt.strftime("%H:%M")
    close_position(position, exit_price, exit_reason, exit_time_str)

    # Recompute net_pnl with asymmetric buy/sell commission.
    buy_comm = position.entry_price * position.shares * BUY_RATE
    sell_comm = position.exit_price * position.shares * SELL_RATE
    asym_comm = buy_comm + sell_comm
    asym_net = position.gross_pnl - asym_comm
    capital += asym_net

    # Recompute result classification under asymmetric fee.
    if exit_reason == "take_profit":
        asym_result = "WIN"
    elif asym_net < -0.01:
        asym_result = "LOSS"
    else:
        asym_result = "BE"

    total_risk = position.risk_per_share * position.shares
    asym_r = asym_net / total_risk if total_risk > 0 else 0.0

    return {
        "date": str(pb_time.date()),
        "symbol": position.symbol,
        "direction": signal.direction,
        "entry": round(signal.entry_price, 2),
        "sl": round(signal.stop_loss, 2),
        "tp": round(signal.take_profit, 2),
        "exit": round(position.exit_price, 2),
        "reason": exit_reason,
        "shares": shares,
        "net": round(asym_net, 2),
        "comm": round(asym_comm, 2),
        "r": round(asym_r, 2),
        "result": asym_result,
        "entry_t": entry_time_str,
        "exit_t": exit_time_str,
        "capital": round(capital, 2),
        "pb_time": pb_time.strftime("%H:%M:%S"),
    }, capital


def run_backtest(mode, data):
    """mode: 'trend' or 'dual'."""
    tqqq_5m, sqqq_5m, qqq_d, tqqq_d, sqqq_d, vix_d = data

    tqqq_5m = tqqq_5m.copy()
    sqqq_5m = sqqq_5m.copy()
    tqqq_5m["date"] = tqqq_5m.index.date
    sqqq_5m["date"] = sqqq_5m.index.date

    days = sorted(set(tqqq_5m["date"].unique()) & set(sqqq_5m["date"].unique()))

    capital = INITIAL_CAPITAL
    cb = CircuitBreaker(
        max_consecutive_losses=CIRCUIT_BREAKER_LOSSES,
        max_weekly_loss_pct=MAX_WEEKLY_LOSS_PCT,
    )
    cur_week = None
    trades = []
    skip_reasons = {
        "no_orb": 0, "vix_filter": 0, "ma_na": 0, "orb_wide": 0,
        "no_signal": 0, "circuit_breaker": 0, "insufficient_capital": 0,
    }
    cap_hist = [(str(days[0]), capital)]

    for day in days:
        wk = pd.Timestamp(day).isocalendar()[1]
        if cur_week != wk:
            cur_week = wk
            cb.reset_if_new_week(wk, capital)
        if cb.is_active:
            skip_reasons["circuit_breaker"] += 1
            continue

        # VIX filter (shared)
        vix_day = vix_d[vix_d.index.date <= day]
        if len(vix_day) == 0:
            skip_reasons["vix_filter"] += 1
            continue
        vix = float(vix_day.iloc[-1]["Close"])
        if check_vix_filter(vix, VIX_LOW, VIX_HIGH):
            skip_reasons["vix_filter"] += 1
            continue

        # MA filter availability (shared)
        d_before = qqq_d[qqq_d.index.date <= day]
        if len(d_before) < MA_PERIOD + 1 or pd.isna(d_before.iloc[-1]["MA20"]):
            skip_reasons["ma_na"] += 1
            continue

        tqqq_day = tqqq_5m[tqqq_5m["date"] == day]
        sqqq_day = sqqq_5m[sqqq_5m["date"] == day]

        if mode == "trend":
            qqq_close = float(d_before.iloc[-1]["Close"])
            qqq_ma20 = float(d_before.iloc[-1]["MA20"])
            trend = determine_trend(qqq_close, qqq_ma20, BULL_SYMBOL, BEAR_SYMBOL)
            if trend.symbol == BULL_SYMBOL:
                signal, pb_time = evaluate_symbol(tqqq_day, BULL_SYMBOL, tqqq_d, day, skip_reasons)
                day_data = tqqq_day
            else:
                signal, pb_time = evaluate_symbol(sqqq_day, BEAR_SYMBOL, sqqq_d, day, skip_reasons)
                day_data = sqqq_day
            if signal is None:
                continue
        else:  # dual
            sig_t, pb_t = evaluate_symbol(tqqq_day, BULL_SYMBOL, tqqq_d, day, skip_reasons)
            sig_s, pb_s = evaluate_symbol(sqqq_day, BEAR_SYMBOL, sqqq_d, day, skip_reasons)
            # Race: pick earliest pullback
            candidates = []
            if sig_t and pb_t:
                candidates.append((pb_t, sig_t, tqqq_day, BULL_SYMBOL))
            if sig_s and pb_s:
                candidates.append((pb_s, sig_s, sqqq_day, BEAR_SYMBOL))
            if not candidates:
                continue
            candidates.sort(key=lambda x: x[0])  # earliest pullback wins
            pb_time, signal, day_data, _sym = candidates[0]

        trade, capital = run_one_position(signal, pb_time, day_data, capital)
        if trade is None:
            skip_reasons["insufficient_capital"] += 1
            continue
        trades.append(trade)
        cb.record_trade(trade["result"], trade["net"], capital)
        cap_hist.append((str(day), capital))

    return trades, capital, skip_reasons, cap_hist


def metrics(trades, final_capital):
    if not trades:
        return None
    df = pd.DataFrame(trades)
    n = len(df)
    wins = (df["result"] == "WIN").sum()
    losses = (df["result"] == "LOSS").sum()
    bes = (df["result"] == "BE").sum()
    wr = wins / n * 100 if n else 0
    win_sum = df[df["net"] > 0]["net"].sum()
    loss_sum = abs(df[df["net"] < 0]["net"].sum())
    pf = win_sum / loss_sum if loss_sum > 0 else float("inf")
    total = df["net"].sum()
    ret = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # Symbol/day distribution
    sym_dist = df["symbol"].value_counts().to_dict()
    return {
        "trades": n, "wins": wins, "losses": losses, "bes": bes, "wr": wr,
        "pf": pf, "net_total": total, "final_cap": final_capital, "ret_pct": ret,
        "sym_dist": sym_dist,
    }


def main():
    data = fetch_data()
    days = sorted(set(data[0].index.date.tolist()) & set(data[1].index.date.tolist()))
    print(f"[range] {days[0]} ~ {days[-1]}  ({len(days)} trading days)")
    print(f"[capital] ${INITIAL_CAPITAL:.2f}")
    print(f"[commission] buy {BUY_RATE*100:.2f}% / sell {SELL_RATE*100:.2f}% "
          f"(round-trip {(BUY_RATE+SELL_RATE)*100:.2f}%)")
    print(f"[R:R] 1:{RR_RATIO:.1f}\n")

    print("=" * 72)
    print("  MODE A — trend (QQQ MA20 → single symbol)")
    print("=" * 72)
    trades_a, cap_a, skip_a, hist_a = run_backtest("trend", data)
    m_a = metrics(trades_a, cap_a)

    print("=" * 72)
    print("  MODE B — dual-scan (race-to-first-pullback)")
    print("=" * 72)
    trades_b, cap_b, skip_b, hist_b = run_backtest("dual", data)
    m_b = metrics(trades_b, cap_b)

    def calc_mdd(hist):
        caps = pd.Series([c for _, c in hist])
        peak = caps.expanding().max()
        dd = (caps - peak) / peak * 100
        return dd.min()
    m_a["mdd"] = calc_mdd(hist_a)
    m_b["mdd"] = calc_mdd(hist_b)

    print("\n" + "=" * 72)
    print("  COMPARISON")
    print("=" * 72)
    if m_a is None or m_b is None:
        print("Insufficient trades.")
        return

    print(f"{'metric':<24}{'trend':>16}{'dual-scan':>16}{'Δ':>16}")
    print("-" * 72)
    rows = [
        ("거래 수", m_a["trades"], m_b["trades"], m_b["trades"] - m_a["trades"]),
        ("승리", m_a["wins"], m_b["wins"], m_b["wins"] - m_a["wins"]),
        ("패배", m_a["losses"], m_b["losses"], m_b["losses"] - m_a["losses"]),
        ("본전", m_a["bes"], m_b["bes"], m_b["bes"] - m_a["bes"]),
    ]
    for label, a, b, d in rows:
        print(f"{label:<24}{a:>16}{b:>16}{d:>+16}")

    pct_rows = [
        ("승률 %", m_a["wr"], m_b["wr"]),
        ("PF", m_a["pf"], m_b["pf"]),
        ("순손익 $", m_a["net_total"], m_b["net_total"]),
        ("최종 자본 $", m_a["final_cap"], m_b["final_cap"]),
        ("총 수익률 %", m_a["ret_pct"], m_b["ret_pct"]),
        ("MDD %", m_a["mdd"], m_b["mdd"]),
    ]
    for label, a, b in pct_rows:
        d = b - a
        if isinstance(a, float):
            print(f"{label:<24}{a:>16.2f}{b:>16.2f}{d:>+16.2f}")
        else:
            print(f"{label:<24}{a:>16}{b:>16}{d:>+16}")

    print()
    print("심볼 분포:")
    print(f"  trend:     {m_a['sym_dist']}")
    print(f"  dual-scan: {m_b['sym_dist']}")
    print()

    print("스킵 사유 비교:")
    labels = {
        "no_orb": "ORB 데이터 부족", "vix_filter": "VIX 범위 이탈",
        "ma_na": "MA20 데이터 부족", "orb_wide": "ORB 과대",
        "no_signal": "세팅/풀백 미발생", "circuit_breaker": "CB 발동",
        "insufficient_capital": "자본 부족",
    }
    print(f"  {'사유':<22}{'trend':>10}{'dual':>10}")
    for k in skip_a:
        a, b = skip_a[k], skip_b[k]
        if a == 0 and b == 0:
            continue
        print(f"  {labels.get(k, k):<22}{a:>10}{b:>10}")
    print()

    # Day-of-week trade counts
    df_a = pd.DataFrame(trades_a)
    df_b = pd.DataFrame(trades_b)
    df_a["dow"] = pd.to_datetime(df_a["date"]).dt.day_name()
    df_b["dow"] = pd.to_datetime(df_b["date"]).dt.day_name()

    print("요일별 거래 수:")
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    print(f"  {'요일':<14}{'trend':>10}{'dual':>10}")
    for d in dow_order:
        a = (df_a["dow"] == d).sum()
        b = (df_b["dow"] == d).sum()
        print(f"  {d:<14}{a:>10}{b:>10}")
    print()

    # Quality of extra trades (in dual but not trend)
    set_a = set(df_a["date"])
    set_b = set(df_b["date"])
    only_b = set_b - set_a
    extra = df_b[df_b["date"].isin(only_b)]
    if len(extra) > 0:
        ex_n = len(extra)
        ex_w = (extra["result"] == "WIN").sum()
        ex_l = (extra["result"] == "LOSS").sum()
        ex_be = (extra["result"] == "BE").sum()
        ex_net = extra["net"].sum()
        ex_wr = ex_w / ex_n * 100
        win_sum_e = extra[extra["net"] > 0]["net"].sum()
        loss_sum_e = abs(extra[extra["net"] < 0]["net"].sum())
        ex_pf = win_sum_e / loss_sum_e if loss_sum_e > 0 else float("inf")
        print(f"\ndual 단독 추가 거래 ({ex_n}건) 품질:")
        print(f"  결과: {ex_w}승 {ex_l}패 {ex_be}본전")
        print(f"  승률: {ex_wr:.1f}%   PF: {ex_pf:.2f}   순손익: ${ex_net:+.2f}")
        print(f"  심볼: {extra['symbol'].value_counts().to_dict()}")

    # Date overlap analysis
    only_a = set_a - set_b
    both = set_a & set_b
    print(f"거래 발생 날짜:")
    print(f"  trend 단독:    {len(only_a)}일  → {sorted(only_a)[:5]}{'...' if len(only_a) > 5 else ''}")
    print(f"  dual 단독:     {len(only_b)}일  → {sorted(only_b)[:5]}{'...' if len(only_b) > 5 else ''}")
    print(f"  공통:          {len(both)}일")

    # Of common dates, does dual pick same symbol or different?
    if both:
        same_sym = 0
        diff_sym = 0
        diff_details = []
        for d in sorted(both):
            sa = df_a[df_a["date"] == d].iloc[0]
            sb = df_b[df_b["date"] == d].iloc[0]
            if sa["symbol"] == sb["symbol"]:
                same_sym += 1
            else:
                diff_sym += 1
                diff_details.append((d, sa["symbol"], sa["result"], sa["net"], sb["symbol"], sb["result"], sb["net"]))
        print(f"  공통일 — 동일 심볼: {same_sym}, 다른 심볼: {diff_sym}")
        if diff_details:
            print(f"  심볼이 갈린 날 (trend → dual):")
            for d, sa, ra, na, sb, rb, nb in diff_details:
                print(f"    {d}  trend={sa}({ra} ${na:+.2f})  dual={sb}({rb} ${nb:+.2f})")
    print()


if __name__ == "__main__":
    main()
