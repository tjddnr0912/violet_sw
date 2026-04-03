#!/usr/bin/env python3
"""
Casper Production Code Backtest
================================
프로덕션 src/ 모듈을 직접 import하여 백테스트 실행.
초기 자본 $500 기준, yfinance 5분봉 최대 60일.

사용하는 프로덕션 모듈:
  - src.core.orb: calculate_orb, is_orb_too_wide
  - src.core.fvg: check_breakout_with_fvg
  - src.core.strategy: scan_for_signal, check_pullback
  - src.core.position: create_position, check_exit, move_stop_to_breakeven, close_position
  - src.core.risk: check_vix_filter, determine_trend, CircuitBreaker
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
import warnings
warnings.filterwarnings('ignore')

# ─── Production modules ───
from src.core.orb import calculate_orb, is_orb_too_wide, OpeningRange
from src.core.fvg import check_breakout_with_fvg
from src.core.strategy import scan_for_signal, check_pullback, TradeSignal
from src.core.position import (
    create_position, check_exit, move_stop_to_breakeven, close_position, Position
)
from src.core.risk import check_vix_filter, determine_trend, CircuitBreaker
import logging
logging.disable(logging.CRITICAL)  # Suppress production logs during backtest

# ============================================================
# Config (from strategy_params.json)
# ============================================================
BULL_SYMBOL = "TQQQ"
BEAR_SYMBOL = "SQQQ"
TREND_SYMBOL = "QQQ"
COMMISSION_RATE = 0.0009
RR_RATIO = 2.0
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


def fetch_data():
    """Download all required data."""
    print("[1/4] 데이터 다운로드...")
    tqqq_5m = yf.Ticker(BULL_SYMBOL).history(period="60d", interval="5m")
    sqqq_5m = yf.Ticker(BEAR_SYMBOL).history(period="60d", interval="5m")
    qqq_daily = yf.Ticker(TREND_SYMBOL).history(period="6mo", interval="1d")
    tqqq_daily = yf.Ticker(BULL_SYMBOL).history(period="6mo", interval="1d")
    sqqq_daily = yf.Ticker(BEAR_SYMBOL).history(period="6mo", interval="1d")
    vix_daily = yf.Ticker("^VIX").history(period="6mo", interval="1d")

    for name, df in [("TQQQ 5m", tqqq_5m), ("SQQQ 5m", sqqq_5m),
                     ("QQQ daily", qqq_daily), ("VIX daily", vix_daily)]:
        if df.empty:
            raise ValueError(f"No data for {name}")

    tqqq_5m.index = tqqq_5m.index.tz_convert('US/Eastern')
    sqqq_5m.index = sqqq_5m.index.tz_convert('US/Eastern')

    qqq_daily['MA20'] = qqq_daily['Close'].rolling(MA_PERIOD).mean()

    return tqqq_5m, sqqq_5m, qqq_daily, tqqq_daily, sqqq_daily, vix_daily


def run_backtest():
    tqqq_5m, sqqq_5m, qqq_daily, tqqq_daily, sqqq_daily, vix_daily = fetch_data()

    tqqq_5m['date'] = tqqq_5m.index.date
    sqqq_5m['date'] = sqqq_5m.index.date

    trading_days = sorted(set(tqqq_5m['date'].unique()) & set(sqqq_5m['date'].unique()))

    print(f"  기간: {trading_days[0]} ~ {trading_days[-1]} ({len(trading_days)}일)")
    print(f"  초기 자본: ${INITIAL_CAPITAL:.2f}")
    print()

    # ─── State ───
    capital = INITIAL_CAPITAL
    cb = CircuitBreaker(
        max_consecutive_losses=CIRCUIT_BREAKER_LOSSES,
        max_weekly_loss_pct=MAX_WEEKLY_LOSS_PCT,
    )
    current_week = None
    trades = []
    skip_reasons = {
        'no_orb': 0, 'vix_filter': 0, 'ma_na': 0, 'orb_wide': 0,
        'no_signal': 0, 'circuit_breaker': 0, 'insufficient_capital': 0,
    }
    capital_history = [(str(trading_days[0]), capital)]

    print(f"[2/4] 백테스트 실행...")

    for day in trading_days:
        # Weekly reset
        wk = pd.Timestamp(day).isocalendar()[1]
        if current_week != wk:
            current_week = wk
            cb.reset_if_new_week(wk, capital)

        # Circuit breaker
        if cb.is_active:
            skip_reasons['circuit_breaker'] += 1
            continue

        # VIX filter (using production code)
        vix_day = vix_daily[vix_daily.index.date <= day]
        if len(vix_day) == 0:
            skip_reasons['vix_filter'] += 1
            continue
        vix_val = float(vix_day.iloc[-1]['Close'])
        vix_skip = check_vix_filter(vix_val, VIX_LOW, VIX_HIGH)
        if vix_skip:
            skip_reasons['vix_filter'] += 1
            continue

        # Trend filter (using production code)
        daily_before = qqq_daily[qqq_daily.index.date <= day]
        if len(daily_before) < MA_PERIOD + 1 or pd.isna(daily_before.iloc[-1]['MA20']):
            skip_reasons['ma_na'] += 1
            continue

        qqq_close = float(daily_before.iloc[-1]['Close'])
        qqq_ma20 = float(daily_before.iloc[-1]['MA20'])
        trend = determine_trend(qqq_close, qqq_ma20, BULL_SYMBOL, BEAR_SYMBOL)

        if trend.symbol == BULL_SYMBOL:
            day_data = tqqq_5m[tqqq_5m['date'] == day].copy()
            sym_daily = tqqq_daily
        else:
            day_data = sqqq_5m[sqqq_5m['date'] == day].copy()
            sym_daily = sqqq_daily

        if len(day_data) == 0:
            skip_reasons['no_orb'] += 1
            continue

        # ORB calculation (using production code)
        orb = calculate_orb(day_data)
        if orb is None:
            skip_reasons['no_orb'] += 1
            continue

        # ORB width filter (using production code)
        recent_daily = sym_daily[sym_daily.index.date <= day].tail(20)
        if len(recent_daily) >= 10:
            adr = float((recent_daily['High'] - recent_daily['Low']).mean())
            if is_orb_too_wide(orb, adr, ORB_ATR_MAX_RATIO):
                skip_reasons['orb_wide'] += 1
                continue

        # Scan for signal (using production code)
        post_orb = day_data.between_time('09:45', '10:55')
        if len(post_orb) < 4:
            skip_reasons['no_signal'] += 1
            continue

        signal = scan_for_signal(
            post_orb, orb, trend.symbol,
            rr_ratio=RR_RATIO, min_risk=MIN_RISK_DOLLAR,
        )

        if signal is None:
            skip_reasons['no_signal'] += 1
            continue

        # Check pullback
        pullback_found = False
        after_signal = day_data[day_data.index > post_orb.index[min(len(post_orb)-1, len(post_orb)-1)]]
        after_signal = after_signal.between_time('09:45', '15:50')

        entry_time = None
        for j in range(len(after_signal)):
            if check_pullback(after_signal.iloc[j], signal.fvg):
                pullback_found = True
                entry_time = after_signal.index[j]
                break

        # Also check within post_orb bars after signal
        if not pullback_found:
            sig_time = pd.Timestamp(signal.signal_time)
            if sig_time.tzinfo is None:
                import pytz
                sig_time = pytz.timezone('US/Eastern').localize(sig_time)
            for j in range(len(post_orb)):
                if post_orb.index[j] > sig_time:
                    if check_pullback(post_orb.iloc[j], signal.fvg):
                        pullback_found = True
                        entry_time = post_orb.index[j]
                        break

        if not pullback_found:
            skip_reasons['no_signal'] += 1
            continue

        # Position sizing (with caps from production code)
        price = signal.entry_price
        shares = int(capital / price) if price > 0 else 0
        shares = min(shares, MAX_SHARES, int(capital * MAX_POSITION_PCT / price) if price > 0 else 0)
        if shares < 1:
            skip_reasons['insufficient_capital'] += 1
            continue

        # Create position (using production code)
        entry_time_str = entry_time.strftime("%H:%M")
        position = create_position(signal, shares, COMMISSION_RATE, entry_time_str)

        # ─── Position simulation using production exit logic ───
        pos_bars = day_data[day_data.index >= entry_time]
        exit_price = None
        exit_reason = None

        for k in range(len(pos_bars)):
            bar = pos_bars.iloc[k]
            bt = pos_bars.index[k]
            ct = bt.time()

            # 11:00 BE move (using production code)
            if ct >= dtime(11, 0):
                move_stop_to_breakeven(position)

            # 15:50 force close
            if ct >= dtime(15, 50):
                exit_price = bar['Close']
                exit_reason = 'time_force'
                break

            # Check exit (using production code)
            reason = check_exit(position, bar['High'], bar['Low'], bar['Close'])
            if reason:
                if "stop" in reason:
                    exit_price = position.stop_loss
                elif reason == "take_profit":
                    exit_price = position.take_profit
                else:
                    exit_price = bar['Close']
                exit_reason = reason
                break

        if exit_price is None:
            exit_price = pos_bars.iloc[-1]['Close']
            exit_reason = 'eod'

        # Close position (using production code)
        exit_time_str = pos_bars.index[-1].strftime("%H:%M") if exit_reason == 'eod' else bt.strftime("%H:%M")
        close_position(position, exit_price, exit_reason, exit_time_str)

        # Update capital
        capital += position.net_pnl

        # Update circuit breaker (using production code)
        cb.record_trade(position.result, position.net_pnl, capital)

        capital_history.append((str(day), capital))

        trades.append({
            'date': day,
            'symbol': trend.symbol,
            'trend': trend.direction,
            'entry': round(signal.entry_price, 2),
            'sl': round(signal.stop_loss, 2),
            'tp': round(signal.take_profit, 2),
            'exit': round(position.exit_price, 2),
            'reason': exit_reason,
            'shares': shares,
            'risk_ps': round(signal.risk_per_share, 2),
            'gross': round(position.gross_pnl, 2),
            'comm': round(position.commission, 2),
            'net': round(position.net_pnl, 2),
            'r': round(position.r_multiple, 2),
            'result': position.result,
            'entry_t': entry_time_str,
            'exit_t': exit_time_str,
            'capital': round(capital, 2),
        })

    # ════════════════════════════════════════════════════════════
    # REPORT
    # ════════════════════════════════════════════════════════════
    print()
    df = pd.DataFrame(trades)

    print("=" * 70)
    print("  CASPER PRODUCTION BACKTEST REPORT")
    print(f"  프로덕션 src/ 모듈 기반 — $500 시작")
    print("=" * 70)
    print()

    if len(df) == 0:
        print("  *** 거래 신호 0건 ***")
        print()
        for k, v in skip_reasons.items():
            if v > 0:
                labels = {
                    'no_orb': 'ORB 데이터 부족', 'vix_filter': 'VIX 범위 이탈',
                    'ma_na': 'MA20 데이터 부족', 'orb_wide': 'ORB 과대',
                    'no_signal': '세팅 미발생', 'circuit_breaker': 'CB 발동',
                    'insufficient_capital': '자본금 부족',
                }
                print(f"    {labels.get(k,k)}: {v}일")
        return

    n = len(df)
    wins = len(df[df['result'] == 'WIN'])
    losses = len(df[df['result'] == 'LOSS'])
    bes = len(df[df['result'] == 'BE'])
    wr = wins / n * 100 if n > 0 else 0

    net_total = df['net'].sum()
    comm_total = df['comm'].sum()

    win_sum = df[df['net'] > 0]['net'].sum()
    loss_sum = abs(df[df['net'] < 0]['net'].sum())
    pf = win_sum / loss_sum if loss_sum > 0 else float('inf')

    avg_w = df[df['net'] > 0]['net'].mean() if wins > 0 else 0
    avg_l = df[df['net'] < 0]['net'].mean() if losses > 0 else 0
    avg_r = df['r'].mean()
    exp = (wr/100 * avg_w) + ((1 - wr/100) * avg_l)

    # Max consecutive
    mx_cw = mx_cl = cw = cl = 0
    for _, r in df.iterrows():
        if r['result'] == 'WIN':
            cw += 1; cl = 0; mx_cw = max(mx_cw, cw)
        elif r['result'] == 'LOSS':
            cl += 1; cw = 0; mx_cl = max(mx_cl, cl)
        else:
            cw = cl = 0

    # MDD
    caps = pd.Series([c for _, c in capital_history])
    peak = caps.expanding().max()
    dd = (caps - peak) / peak * 100
    mdd = dd.min()

    ret_pct = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # ─── Summary ───
    print(f"  기간: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
    print(f"  총 거래일: {len(trading_days)}일 / 거래 발생: {n}회 ({n/len(trading_days)*100:.1f}%)")
    print()

    # Skip reasons
    print("─" * 70)
    print("  스킵 사유")
    print("─" * 70)
    labels = {
        'no_orb': 'ORB 데이터 부족', 'vix_filter': 'VIX 범위 이탈',
        'ma_na': 'MA20 데이터 부족', 'orb_wide': 'ORB 과대',
        'no_signal': '세팅 미발생', 'circuit_breaker': 'CB 발동',
        'insufficient_capital': '자본금 부족',
    }
    for k, v in sorted(skip_reasons.items(), key=lambda x: -x[1]):
        if v > 0:
            print(f"    {labels.get(k,k)}: {v}일")
    print()

    # W/L
    print("─" * 70)
    print("  승/패 통계")
    print("─" * 70)
    print(f"    승리: {wins}회 ({wr:.1f}%)")
    print(f"    패배: {losses}회 ({losses/n*100:.1f}%)")
    if bes > 0:
        print(f"    본전: {bes}회 ({bes/n*100:.1f}%)")
    print(f"    최대 연속 승: {mx_cw}회 / 최대 연속 패: {mx_cl}회")
    print()

    # PnL
    print("─" * 70)
    print("  자본 변화 ($500 기준)")
    print("─" * 70)
    print(f"    초기 자본:     ${INITIAL_CAPITAL:,.2f}")
    print(f"    최종 자본:     ${capital:,.2f}")
    print(f"    총 수익률:     {ret_pct:+.2f}%")
    print(f"    순손익 합계:   ${net_total:+,.2f}")
    print(f"    총 수수료:     ${comm_total:,.2f}")
    print()

    # Key metrics
    print("─" * 70)
    print("  핵심 성과 지표")
    print("─" * 70)
    print(f"    승률:            {wr:.1f}%")
    print(f"    Profit Factor:   {pf:.2f}")
    print(f"    평균 R:          {avg_r:+.2f}R")
    print(f"    기대값:          ${exp:+.2f}/거래")
    print(f"    평균 수익:       ${avg_w:+.2f}")
    print(f"    평균 손실:       ${avg_l:+.2f}")
    if avg_l != 0:
        print(f"    실현 손익비:     1:{abs(avg_w/avg_l):.2f}")
    print(f"    MDD:             {mdd:.2f}%")
    print()

    # By symbol
    tqqq_df = df[df['symbol'] == BULL_SYMBOL]
    sqqq_df = df[df['symbol'] == BEAR_SYMBOL]
    print("─" * 70)
    print("  종목별 성과")
    print("─" * 70)
    for label, sub in [(f"TQQQ (상승장)", tqqq_df), (f"SQQQ (하락장)", sqqq_df)]:
        if len(sub) > 0:
            sw = len(sub[sub['result'] == 'WIN'])
            print(f"    {label}: {len(sub)}회, 승률 {sw/len(sub)*100:.1f}%, PnL ${sub['net'].sum():+.2f}")
    print()

    # Exit reasons
    print("─" * 70)
    print("  청산 사유별")
    print("─" * 70)
    rlabels = {
        'take_profit': '익절 (1:2)', 'stop_loss': '손절',
        'be_stop': '본전 손절', 'time_force': '강제 청산',
        'eod': '장 마감',
    }
    for reason in df['reason'].unique():
        sub = df[df['reason'] == reason]
        print(f"    {rlabels.get(reason, reason):15s}: {len(sub):2d}회  ${sub['net'].sum():+8.2f}")
    print()

    # Day of week
    print("─" * 70)
    print("  요일별")
    print("─" * 70)
    df['wd'] = pd.to_datetime(df['date']).dt.day_name()
    for wd in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
        sub = df[df['wd'] == wd]
        if len(sub) > 0:
            sw = len(sub[sub['result'] == 'WIN'])
            print(f"    {wd:10s}: {len(sub):2d}회  승률 {sw/len(sub)*100:5.1f}%  ${sub['net'].sum():+8.2f}")
    print()

    # Individual trades
    print("─" * 70)
    print("  개별 거래 내역")
    print("─" * 70)
    print(f"  {'날짜':>12} {'종목':>5} {'추세':>4} {'진입':>7} {'청산':>7} {'사유':>6} {'수량':>4} {'순손익':>9} {'R':>6} {'결과':>4} {'자본':>9}")
    print("  " + "-" * 78)
    for _, t in df.iterrows():
        rs = {'take_profit':'익절','stop_loss':'손절','be_stop':'본전','time_force':'강제','eod':'마감'}.get(t['reason'], t['reason'])
        tr = {'bull':'강세','bear':'약세'}.get(t['trend'], t['trend'])
        print(f"  {str(t['date']):>12} {t['symbol']:>5} {tr:>4} ${t['entry']:>6.2f} ${t['exit']:>6.2f} {rs:>6} {t['shares']:>4} ${t['net']:>+8.2f} {t['r']:>+5.2f}R {t['result']:>4} ${t['capital']:>8.2f}")
    print()

    # Capital curve
    print("─" * 70)
    print("  자본 변화 추이")
    print("─" * 70)
    for dt, cap in capital_history:
        bar_len = int((cap / INITIAL_CAPITAL - 0.5) * 40) if cap > INITIAL_CAPITAL * 0.5 else 0
        bar_len = max(0, min(bar_len, 40))
        bar = "█" * bar_len
        print(f"    {dt} ${cap:>8.2f} {bar}")
    print()

    # ─── Validity score ───
    print("=" * 70)
    print("  알고리즘 타당성 평가")
    print("=" * 70)
    print()

    score = 0
    mx = 6

    checks = [
        (wr >= 40, wr >= 33, f"승률 {wr:.1f}%", ">=40%", ">=33%"),
        (pf >= 1.5, pf >= 1.0, f"PF {pf:.2f}", ">=1.5", ">=1.0"),
        (exp > 0, False, f"기대값 ${exp:+.2f}", ">0", ""),
        (abs(mdd) <= 15, abs(mdd) <= 25, f"MDD {mdd:.2f}%", "<=15%", "<=25%"),
        (n >= 30, n >= 15, f"거래 {n}회", ">=30", ">=15"),
    ]
    if avg_l != 0:
        act_rr = abs(avg_w / avg_l)
        checks.append((act_rr >= 1.8, act_rr >= 1.0, f"R:R 1:{act_rr:.2f}", ">=1.8", ">=1.0"))

    for (pass_cond, warn_cond, label, pass_val, warn_val) in checks:
        if pass_cond:
            print(f"  [PASS] {label} ({pass_val})"); score += 1
        elif warn_cond:
            print(f"  [WARN] {label} ({warn_val})"); score += 0.5
        else:
            print(f"  [FAIL] {label}")

    print()
    print(f"  종합 점수: {score}/{mx} ({score/mx*100:.0f}%)")
    if score >= 5: verdict = "STRONG PASS - 실전 적용 검토 가능"
    elif score >= 3.5: verdict = "CONDITIONAL PASS - 파라미터 최적화 후 재검증"
    elif score >= 2: verdict = "WEAK - 추가 필터 보완 필요"
    else: verdict = "FAIL - 전략 재설계 필요"
    print(f"  판정: {verdict}")
    print()
    print("=" * 70)
    print("  프로덕션 모듈 사용 확인")
    print("=" * 70)
    print(f"  - src.core.orb.calculate_orb()")
    print(f"  - src.core.strategy.scan_for_signal()")
    print(f"  - src.core.position.create_position() / check_exit() / close_position()")
    print(f"  - src.core.risk.check_vix_filter() / determine_trend() / CircuitBreaker")
    print(f"  - 모든 거래: Long Only (공매도 없음)")
    print(f"  - 커미션: 편도 {COMMISSION_RATE*100:.2f}%")
    print(f"  - BE 공식: entry*(1+r)/(1-r) (라운드트립 정확)")
    print("=" * 70)


if __name__ == "__main__":
    run_backtest()
