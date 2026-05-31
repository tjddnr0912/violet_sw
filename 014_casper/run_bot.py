#!/usr/bin/env python3
"""
Casper Trading Bot - Entry Point
=================================
TQQQ/SQQQ Long-Only ORB+FVG Strategy

Usage:
    python run_bot.py           # Start the bot
    python run_bot.py --status  # Show cumulative stats

Environment:
    Set TRADING_MODE in .env:
      - "paper"  : Paper trading (모의투자)
      - "live"   : Live trading (실거래)
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.trade_store import load_trades, get_cumulative_stats
from src.utils.config import load_strategy_params, load_env


def _ict_status_line(entry: dict, mode: dict | None = None) -> str:
    """Compact ICT flag summary, matching telegram/bash output style."""
    flags = []
    if mode and mode.get("qqq_primary"):
        flags.append("QQQ-PRIMARY")
    if entry.get("killzone_filter_enabled"):
        kz = entry.get("allowed_killzones") or []
        flags.append("KZ(" + ",".join(kz) + ")" if kz else "KZ")
    if entry.get("require_displacement"):
        flags.append("Disp")
    if entry.get("require_sweep_choch"):
        flags.append("Sweep")
    if entry.get("daily_bias_skip_neutral"):
        flags.append("Bias")
    if entry.get("bear_fvg_for_sqqq"):
        flags.append("QQQ→SQQQ")
    if entry.get("bull_fvg_for_tqqq"):
        flags.append("QQQ→TQQQ")
    if entry.get("use_ote"):
        flags.append(f"OTE({entry.get('ote_fib_level', 0.705)})")
    if entry.get("require_unicorn"):
        flags.append("Unicorn")
    if entry.get("use_multi_tf_sl"):
        flags.append("MTF-SL")
    if entry.get("use_power_of_3"):
        flags.append("P3")
    if entry.get("use_eqh_eql_pools"):
        flags.append("EQH/EQL")
    if entry.get("use_session_pools"):
        flags.append("SessionPools")
    if entry.get("use_premkt_history"):
        flags.append("PremktHist")
    if entry.get("use_pdh_pdl_pool"):
        flags.append("PDH/PDL")
    return " + ".join(flags) if flags else "off"


def _print_trend_status(params: dict) -> None:
    """Print the active low-freq trend sleeve description + live status.

    Mirrors src/bot.py _log_trend_startup_detail / run_casper.sh
    show_trend_banner so all three banners agree.
    """
    t = params.get("trend", {}) if isinstance(params, dict) else {}
    mode = os.getenv("TREND_MODE") or t.get("mode", "off")
    sig = t.get("signal_symbol", "QQQ")
    sma = t.get("sma_period", 200)
    asset = t.get("asset", "TQQQ")
    safe = t.get("safe_asset", "BIL")
    tvol = t.get("target_vol", 0.40)
    vlb = t.get("vol_lookback", 20)
    rebal = t.get("rebalance", "monthly")
    print(f"  슬리브: TREND (TQQQ Vol-Target, mode={mode})")
    print(f"  전략: {sig}>{sma}d SMA 이면 {asset}, 아니면 {safe} (레짐 게이트)")
    print(f"     • 노출 = min(1, target_vol {tvol} / 실현변동성({asset},{vlb}d))")
    print(f"     • 리밸런스 {rebal} (저빈도) — 인트라데이 스캔 없음")
    # Live status from trend_state.json (non-raising).
    try:
        import json
        s = json.load(open("data/trend_state.json"))
        if isinstance(s, dict):
            hold = s.get("current_holding") or "대기"
            last = s.get("last_signal_date") or "없음"
            expo = s.get("last_exposure")
            expo_s = f"{expo:.0%}" if isinstance(expo, (int, float)) else "—"
            print(f"     └ 상태: 보유 {hold} | 마지막 리밸런스 {last} | 노출 {expo_s}")
    except Exception:
        pass
    print("  비활성: 레거시 ORB+FVG 인트라데이 엔진 (sleeve_engine='intraday' 로 전환 시 활성)")


def show_status():
    """Print cumulative trading statistics + current ICT config."""
    # env + config (env can override ICT phases per .env.example)
    load_env()
    try:
        params = load_strategy_params()
        entry = params.get("entry", {})
        mode = params.get("mode", {})
    except Exception:
        entry = {}
        mode = {}

    trades = load_trades()
    stats = get_cumulative_stats(trades)

    print("=" * 60)
    print("  Casper Bot - Cumulative Stats")
    print("=" * 60)
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Wins: {stats['wins']} | Losses: {stats['losses']} | BE: {stats['bes']}")
    print(f"  Win Rate: {stats['win_rate']}%")
    print(f"  Total P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Profit Factor: {stats['profit_factor']}")
    print("-" * 60)

    # Strategy section is sleeve-aware. In the default trend mode the intraday
    # ORB+FVG engine is dormant, so printing R:R / Strict FVG / ICT / Fine-tune
    # would describe a strategy that isn't running. Show the active TQQQ
    # Vol-Target sleeve instead; the legacy block stays for intraday mode.
    sleeve_engine = params.get("sleeve_engine", "trend") if isinstance(params, dict) else "trend"
    if sleeve_engine != "intraday":
        _print_trend_status(params)
    else:
        print(f"  R:R: 1:{entry.get('rr_ratio', '?')}")
        print(f"  Strict FVG: {entry.get('strict_fvg', '?')}")
        print(f"  ICT: {_ict_status_line(entry, mode)}")
        # KST window (DST-aware)
        try:
            from datetime import datetime, time as dtime
            import pytz
            et = pytz.timezone("US/Eastern")
            kst = pytz.timezone("Asia/Seoul")
            today_et = datetime.now(et)
            s = et.localize(datetime.combine(today_et.date(), dtime(9, 30))).astimezone(kst)
            e = et.localize(datetime.combine(today_et.date(), dtime(10, 55))).astimezone(kst)
            is_dst = today_et.dst().total_seconds() != 0
            print(f"  매매 윈도우: ET 09:30~10:55  "
                  f"(KST {s.strftime('%H:%M')}~{e.strftime('%H:%M')}, "
                  f"{'서머타임' if is_dst else '표준시'})")
        except Exception:
            pass
    print(f"  Data Collection: {os.getenv('DATA_COLLECTION', 'off')}")
    print("=" * 60)

    if sleeve_engine == "intraday":
        # Per-trade ICT meta summary (recent 5)
        recent = [t for t in trades if isinstance(t, dict) and t.get("ict")][-5:]
        if recent:
            print("  Recent trades with ICT meta:")
            for t in recent:
                ict = t.get("ict", {})
                print(f"    {t.get('date', '?')} {t.get('symbol', '?'):5s} "
                      f"{t.get('result', '?'):4s} "
                      f"R={t.get('r_multiple', 0):+.2f}  "
                      f"kz={ict.get('killzone', '-')}  "
                      f"filters={','.join(ict.get('filters_active', []) or ['-'])}  "
                      f"bias={ict.get('daily_bias_direction', '-')}")
            print("=" * 60)

        # Fine-tune reminder (intraday-only — counts ICT-tagged trades)
        n_ict = sum(1 for t in trades if isinstance(t, dict) and t.get("ict"))
        target = 5
        print()
        if n_ict < target:
            rem = target - n_ict
            print(f"📌 Fine-tune: ICT 매매 {n_ict}/{target}건 누적 ({rem}건 더 필요)")
            print(f"   누적 후 실행 → python scripts/phase1_precheck.py")
        elif n_ict % target == 0:
            print(f"📌 FINE-TUNE NOW: ICT 매매 {n_ict}건 누적 — phase1_precheck.py 재실행 권장!")
        else:
            nxt = ((n_ict // target) + 1) * target
            print(f"📌 Fine-tune: ICT 매매 {n_ict}건 누적 (다음 검증 시점: {nxt}건)")
        print()


def main():
    if "--status" in sys.argv:
        show_status()
        return

    from src.bot import CasperBot
    bot = CasperBot()
    bot.run()


if __name__ == "__main__":
    main()
