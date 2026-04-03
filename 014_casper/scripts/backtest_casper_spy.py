#!/usr/bin/env python3
"""
Casper Trading Strategy Backtest - TQQQ / SQQQ (Long Only)
============================================================
전략: ORB (15분) + FVG (5분) + Pullback Entry + R:R 1:2
기간: 최근 60일 (yfinance 5분봉 한계)

매매 방식 (공매도 없음, Long Only):
  - 상승 추세 (QQQ > 20MA): TQQQ 매수 (Long)
  - 하락 추세 (QQQ < 20MA): SQQQ 매수 (Long)
  - 양쪽 모두 ORB 상단 돌파 + Bullish FVG + 되돌림 진입

전략 규칙:
1. 9:30~9:45 ET → 15분 Opening Range (ORB) 고가/저가 설정
2. 5분봉 전환, 캔들 몸통(body)이 ORB 상단 돌파 (항상 Long)
3. 돌파 캔들에서 Bullish FVG 형성 확인
4. FVG 구간으로 되돌림 시 매수 진입
5. 손절: FVG 제1캔들 저점
6. 익절: R:R 1:2
7. 11:00 이후 미청산 → 손절을 손익분기가(수수료 포함)로 이동
8. 15:50 미청산 → 강제 시장가 청산
9. 하루 최대 1회 매매
10. VIX 12~30 필터, QQQ 20MA 추세 필터
11. Circuit Breaker: 주간 연속 3회 손절 → 해당 주 중단
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# 설정
# ============================================================
BULL_SYMBOL = "TQQQ"       # 상승 추세 매매 대상
BEAR_SYMBOL = "SQQQ"       # 하락 추세 매매 대상
TREND_SYMBOL = "QQQ"       # 추세 필터용 (QQQ 20MA)
COMMISSION_RATE = 0.0009   # 편도 0.09%
RR_RATIO = 2.0             # R:R 1:2
INITIAL_CAPITAL = 1500.0   # 초기 자본
VIX_LOW = 12.0
VIX_HIGH = 30.0
MA_PERIOD = 20             # 추세 필터 이동평균 기간
CIRCUIT_BREAKER_LOSSES = 3 # 주간 연속 손절 한도
MIN_RISK_DOLLAR = 0.10     # 최소 리스크 $


def get_data(symbol, period="60d", interval="5m"):
    """5분봉 데이터 다운로드"""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No data for {symbol}")
    df.index = df.index.tz_convert('US/Eastern')
    return df


def get_daily_data(symbol, period="6mo"):
    """일봉 데이터"""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval="1d")
    if df.empty:
        raise ValueError(f"No daily data for {symbol}")
    return df


def get_vix_data(period="6mo"):
    """VIX 일봉"""
    ticker = yf.Ticker("^VIX")
    return ticker.history(period=period, interval="1d")


def calculate_orb(day_data_5m):
    """9:30~9:45 ET Opening Range 계산"""
    orb_bars = day_data_5m.between_time('09:30', '09:44')
    if len(orb_bars) < 3:
        return None, None
    return orb_bars['High'].max(), orb_bars['Low'].min()


def identify_bullish_fvg(candles_3):
    """
    Bullish FVG 식별 (3캔들 패턴)
    조건: candle[0].high < candle[2].low → 갭 존재
    Returns: (fvg_exists, fvg_top, fvg_bottom)
    """
    if len(candles_3) < 3:
        return False, None, None
    c1, c2, c3 = candles_3.iloc[0], candles_3.iloc[1], candles_3.iloc[2]
    if c1['High'] < c3['Low']:
        return True, c3['Low'], c1['High']
    return False, None, None


def check_bullish_breakout(candle, orb_high):
    """
    캔들 몸통이 ORB 상단 돌파 (Long only)
    조건: 종가 > ORB 고가 + 양봉
    """
    return candle['Close'] > orb_high and candle['Close'] > candle['Open']


def run_backtest():
    """메인 백테스트"""
    print("=" * 70)
    print("  Casper Strategy Backtest - TQQQ/SQQQ (Long Only)")
    print("=" * 70)
    print()

    # ─── 데이터 다운로드 ───
    print("[1/4] 데이터 다운로드 중...")
    tqqq_5m = get_data(BULL_SYMBOL, period="60d", interval="5m")
    sqqq_5m = get_data(BEAR_SYMBOL, period="60d", interval="5m")
    trend_daily = get_daily_data(TREND_SYMBOL, period="6mo")
    tqqq_daily = get_daily_data(BULL_SYMBOL, period="6mo")
    sqqq_daily = get_daily_data(BEAR_SYMBOL, period="6mo")
    vix_daily = get_vix_data(period="6mo")

    trend_daily['MA20'] = trend_daily['Close'].rolling(MA_PERIOD).mean()

    # 날짜 인덱싱
    tqqq_5m['date'] = tqqq_5m.index.date
    sqqq_5m['date'] = sqqq_5m.index.date

    # 공통 거래일
    tqqq_days = set(tqqq_5m['date'].unique())
    sqqq_days = set(sqqq_5m['date'].unique())
    trading_days = sorted(tqqq_days & sqqq_days)

    print(f"  TQQQ 5분봉: {tqqq_5m.index[0].date()} ~ {tqqq_5m.index[-1].date()}")
    print(f"  SQQQ 5분봉: {sqqq_5m.index[0].date()} ~ {sqqq_5m.index[-1].date()}")
    print(f"  추세 필터: {TREND_SYMBOL} 20MA")
    print(f"  공통 거래일: {len(trading_days)}일")
    print()

    print(f"[2/4] 백테스트 실행 중... ({len(trading_days)}일)")
    print()

    # 결과 & 디버그
    trades = []
    skip = {
        'no_orb': 0, 'vix_filter': 0, 'ma_na': 0, 'orb_wide': 0,
        'no_signal': 0, 'circuit_breaker': 0,
    }
    debug = {
        'breakout_found': 0, 'fvg_found': 0, 'fvg_miss': 0,
        'pullback_found': 0, 'pullback_miss': 0, 'min_risk_skip': 0,
    }

    weekly_consec_losses = 0
    current_week = None
    cb_active = False
    capital = INITIAL_CAPITAL
    capital_history = [(trading_days[0], capital)]

    for day in trading_days:
        # 주간 리셋
        wk = pd.Timestamp(day).isocalendar()[1]
        if current_week != wk:
            current_week = wk
            weekly_consec_losses = 0
            cb_active = False

        if cb_active:
            skip['circuit_breaker'] += 1
            continue

        # VIX 필터
        vix_day = vix_daily[vix_daily.index.date <= day]
        if len(vix_day) > 0:
            vix_val = vix_day.iloc[-1]['Close']
            if vix_val < VIX_LOW or vix_val > VIX_HIGH:
                skip['vix_filter'] += 1
                continue

        # QQQ MA20 추세 필터 → 매매 종목 결정
        daily_before = trend_daily[trend_daily.index.date <= day]
        if len(daily_before) < MA_PERIOD + 1 or pd.isna(daily_before.iloc[-1]['MA20']):
            skip['ma_na'] += 1
            continue

        prev_close = daily_before.iloc[-1]['Close']
        ma20 = daily_before.iloc[-1]['MA20']

        if prev_close > ma20:
            trend = 'bull'
            symbol = BULL_SYMBOL
            day_data = tqqq_5m[tqqq_5m['date'] == day].copy()
            sym_daily = tqqq_daily
        else:
            trend = 'bear'
            symbol = BEAR_SYMBOL
            day_data = sqqq_5m[sqqq_5m['date'] == day].copy()
            sym_daily = sqqq_daily

        if len(day_data) == 0:
            skip['no_orb'] += 1
            continue

        # ORB 계산 (해당 종목의 5분봉)
        orb_high, orb_low = calculate_orb(day_data)
        if orb_high is None:
            skip['no_orb'] += 1
            continue

        orb_range = orb_high - orb_low

        # ORB 과대 필터
        recent_daily = sym_daily[sym_daily.index.date <= day].tail(20)
        if len(recent_daily) >= 10:
            avg_dr = (recent_daily['High'] - recent_daily['Low']).mean()
            if orb_range > avg_dr * 1.5:
                skip['orb_wide'] += 1
                continue

        # 9:45 ~ 11:00 세팅 탐색
        post_orb = day_data.between_time('09:45', '10:55')
        if len(post_orb) < 4:
            skip['no_signal'] += 1
            continue

        trade_found = False

        for i in range(1, len(post_orb) - 1):
            candle = post_orb.iloc[i]

            # 1) ORB 상단 돌파 (항상 Long — TQQQ든 SQQQ든 매수)
            if not check_bullish_breakout(candle, orb_high):
                continue
            debug['breakout_found'] += 1

            # 2) Bullish FVG 확인
            if i + 1 >= len(post_orb):
                continue
            three = post_orb.iloc[i-1:i+2]
            fvg_ok, fvg_top, fvg_bot = identify_bullish_fvg(three)
            if not fvg_ok:
                debug['fvg_miss'] += 1
                continue
            debug['fvg_found'] += 1

            # 3) 진입가, 손절, 익절
            entry_price = (fvg_top + fvg_bot) / 2
            prev_c = post_orb.iloc[i-1]
            stop_loss = prev_c['Low']
            risk = entry_price - stop_loss

            if risk <= 0.01:
                continue
            if risk < MIN_RISK_DOLLAR:
                debug['min_risk_skip'] += 1
                continue

            take_profit = entry_price + risk * RR_RATIO

            # 4) 되돌림 확인
            after_fvg = day_data[day_data.index > post_orb.index[min(i+1, len(post_orb)-1)]]
            after_fvg = after_fvg.between_time('09:45', '15:50')

            pb_found = False
            entry_time = None
            for j in range(len(after_fvg)):
                if after_fvg.iloc[j]['Low'] <= fvg_top:
                    pb_found = True
                    entry_time = after_fvg.index[j]
                    break

            if not pb_found:
                debug['pullback_miss'] += 1
                continue
            debug['pullback_found'] += 1

            # ─── 포지션 시뮬레이션 (항상 Long) ───
            pos_bars = day_data[day_data.index >= entry_time]
            shares = int(capital / entry_price)
            if shares < 1:
                continue

            exit_price = None
            exit_time = None
            exit_reason = None
            be_price = entry_price * (1 + COMMISSION_RATE * 2)
            sl_moved = False
            orig_sl = stop_loss

            for k in range(len(pos_bars)):
                bar = pos_bars.iloc[k]
                bt = pos_bars.index[k]
                ct = bt.time()

                # 11:00 이후 → 손절을 손익분기가로 이동
                if ct >= dtime(11, 0) and not sl_moved:
                    sl_moved = True
                    stop_loss = max(stop_loss, be_price)

                # 15:50 강제 청산
                if ct >= dtime(15, 50):
                    exit_price = bar['Close']
                    exit_time = bt
                    exit_reason = 'time_force'
                    break

                # Long: 손절 체크
                if bar['Low'] <= stop_loss:
                    exit_price = stop_loss
                    exit_time = bt
                    exit_reason = 'be_stop' if sl_moved else 'stop_loss'
                    break
                # Long: 익절 체크
                if bar['High'] >= take_profit:
                    exit_price = take_profit
                    exit_time = bt
                    exit_reason = 'take_profit'
                    break

            if exit_price is None:
                exit_price = pos_bars.iloc[-1]['Close']
                exit_time = pos_bars.index[-1]
                exit_reason = 'eod'

            # 손익 계산 (항상 Long)
            gross_pnl = (exit_price - entry_price) * shares
            comm = (entry_price + exit_price) * shares * COMMISSION_RATE
            net_pnl = gross_pnl - comm
            r_mult = net_pnl / (risk * shares) if risk * shares > 0 else 0

            if exit_reason == 'take_profit':
                result = 'WIN'
            elif exit_reason in ('stop_loss', 'be_stop'):
                result = 'LOSS' if net_pnl < -0.01 else 'BE'
            else:
                result = 'WIN' if net_pnl > 0 else 'LOSS'

            capital += net_pnl
            capital_history.append((day, capital))

            if result == 'LOSS':
                weekly_consec_losses += 1
                if weekly_consec_losses >= CIRCUIT_BREAKER_LOSSES:
                    cb_active = True
            else:
                weekly_consec_losses = 0

            trades.append({
                'date': day,
                'symbol': symbol,
                'trend': trend,
                'entry': round(entry_price, 2),
                'sl': round(orig_sl, 2),
                'tp': round(take_profit, 2),
                'exit': round(exit_price, 2),
                'reason': exit_reason,
                'shares': shares,
                'risk_ps': round(risk, 2),
                'gross': round(gross_pnl, 2),
                'comm': round(comm, 2),
                'net': round(net_pnl, 2),
                'r': round(r_mult, 2),
                'result': result,
                'entry_t': entry_time.strftime('%H:%M'),
                'exit_t': exit_time.strftime('%H:%M') if exit_time else '-',
                'orb_h': round(orb_high, 2),
                'orb_l': round(orb_low, 2),
                'orb_rng': round(orb_range, 2),
                'fvg_t': round(fvg_top, 2),
                'fvg_b': round(fvg_bot, 2),
                'cap': round(capital, 2),
            })
            trade_found = True
            break

        if not trade_found and not cb_active:
            skip['no_signal'] += 1

    # ════════════════════════════════════════════════════════════
    # REPORT
    # ════════════════════════════════════════════════════════════
    print("[3/4] 디버그 통계...")
    print()
    print(f"  ORB 상단 돌파: {debug['breakout_found']}회")
    print(f"  Bullish FVG 형성: {debug['fvg_found']}회 / 미형성: {debug['fvg_miss']}회")
    print(f"  되돌림 발생: {debug['pullback_found']}회 / 미발생: {debug['pullback_miss']}회")
    print(f"  최소리스크 미달: {debug['min_risk_skip']}회")
    print()

    print("[4/4] 리포트 출력...")
    print()

    df = pd.DataFrame(trades)

    if len(df) == 0:
        print("  *** 거래 신호 0건 ***")
        print()
        for k, v in skip.items():
            if v > 0:
                print(f"    {k}: {v}일")
        return None, None

    # ─── 기본 통계 ───
    n = len(df)
    wins = len(df[df['result'] == 'WIN'])
    losses = len(df[df['result'] == 'LOSS'])
    bes = len(df[df['result'] == 'BE'])
    wr = wins / n * 100

    net_total = df['net'].sum()
    comm_total = df['comm'].sum()
    gross_total = df['gross'].sum()

    win_sum = df[df['net'] > 0]['net'].sum()
    loss_sum = abs(df[df['net'] < 0]['net'].sum())
    pf = win_sum / loss_sum if loss_sum > 0 else float('inf')

    avg_w = df[df['net'] > 0]['net'].mean() if wins > 0 else 0
    avg_l = df[df['net'] < 0]['net'].mean() if losses > 0 else 0
    avg_r = df['r'].mean()

    # 연속 승/패
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
    pk = caps.expanding().max()
    dd = (caps - pk) / pk * 100
    mdd = dd.min()

    # 기대값
    exp = (wr/100 * avg_w) + ((1 - wr/100) * avg_l)
    ret_pct = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # TQQQ / SQQQ 분리
    tqqq_df = df[df['symbol'] == BULL_SYMBOL]
    sqqq_df = df[df['symbol'] == BEAR_SYMBOL]

    # ─── 출력 ───
    print("=" * 70)
    print("  CASPER STRATEGY BACKTEST REPORT")
    print("  TQQQ (상승) / SQQQ (하락) — Long Only, 공매도 없음")
    print("=" * 70)
    print()
    print(f"  기간: {df['date'].iloc[0]} ~ {df['date'].iloc[-1]}")
    print(f"  총 거래일: {len(trading_days)}일")
    print(f"  총 거래: {n}회  (세팅 발생률 {n/len(trading_days)*100:.1f}%)")
    print(f"  R:R: 1:{RR_RATIO:.0f}")
    print()

    # 스킵 사유
    print("─" * 70)
    print("  스킵 사유")
    print("─" * 70)
    labels = {
        'no_orb': 'ORB 데이터 부족', 'vix_filter': 'VIX 범위 이탈',
        'ma_na': 'MA20 데이터 부족', 'orb_wide': 'ORB 과대',
        'no_signal': '세팅 미발생', 'circuit_breaker': 'CB 발동',
    }
    for k, v in sorted(skip.items(), key=lambda x: -x[1]):
        if v > 0:
            print(f"    {labels.get(k,k)}: {v}일")
    print()

    # 승/패
    print("─" * 70)
    print("  승/패 통계")
    print("─" * 70)
    print(f"    승리: {wins}회 ({wr:.1f}%)")
    print(f"    패배: {losses}회 ({losses/n*100:.1f}%)")
    if bes > 0:
        print(f"    본전: {bes}회 ({bes/n*100:.1f}%)")
    print(f"    최대 연속 승: {mx_cw}회")
    print(f"    최대 연속 패: {mx_cl}회")
    print()

    # 손익
    print("─" * 70)
    print("  손익 통계")
    print("─" * 70)
    print(f"    초기 자본:     ${INITIAL_CAPITAL:,.2f}")
    print(f"    최종 자본:     ${capital:,.2f}")
    print(f"    총 수익률:     {ret_pct:+.2f}%")
    print(f"    순손익 합계:   ${net_total:+,.2f}")
    print(f"    총 수수료:     ${comm_total:,.2f}")
    print(f"    Gross P&L:     ${gross_total:+,.2f}")
    print()

    # 핵심 지표
    print("─" * 70)
    print("  핵심 성과 지표")
    print("─" * 70)
    print(f"    승률 (Win Rate):     {wr:.1f}%")
    print(f"    Profit Factor:       {pf:.2f}")
    print(f"    평균 R 배수:         {avg_r:+.2f}R")
    print(f"    기대값 (Expectancy): ${exp:+.2f}/거래")
    print(f"    평균 수익 (Win):     ${avg_w:+.2f}")
    print(f"    평균 손실 (Loss):    ${avg_l:+.2f}")
    if avg_l != 0:
        print(f"    실현 손익비:         1:{abs(avg_w/avg_l):.2f}")
    print(f"    최대 낙폭 (MDD):     {mdd:.2f}%")
    print()

    # TQQQ / SQQQ 분리
    for label, sub in [(f"TQQQ (상승장 Long)", tqqq_df), (f"SQQQ (하락장 Long)", sqqq_df)]:
        if len(sub) > 0:
            sw = len(sub[sub['result'] == 'WIN'])
            print(f"  {label}: {len(sub)}회, 승률 {sw/len(sub)*100:.1f}%, 순손익 ${sub['net'].sum():+.2f}")
    print()

    # 청산 사유
    print("─" * 70)
    print("  청산 사유별")
    print("─" * 70)
    rlabels = {
        'take_profit': '익절 (1:2)', 'stop_loss': '손절',
        'be_stop': '본전 손절', 'time_force': '강제 청산 (15:50)',
        'eod': '장 마감',
    }
    for reason in df['reason'].unique():
        sub = df[df['reason'] == reason]
        print(f"    {rlabels.get(reason, reason):15s}: {len(sub):2d}회  ${sub['net'].sum():+8.2f}")
    print()

    # 요일별
    print("─" * 70)
    print("  요일별 성과")
    print("─" * 70)
    df['wd'] = pd.to_datetime(df['date']).dt.day_name()
    for wd in ['Monday','Tuesday','Wednesday','Thursday','Friday']:
        sub = df[df['wd'] == wd]
        if len(sub) > 0:
            sw = len(sub[sub['result'] == 'WIN'])
            print(f"    {wd:10s}: {len(sub):2d}회  승률 {sw/len(sub)*100:5.1f}%  ${sub['net'].sum():+8.2f}")
    print()

    # 개별 거래
    print("─" * 70)
    print("  개별 거래 내역")
    print("─" * 70)
    print(f"  {'날짜':>12} {'종목':>5} {'진입':>7} {'청산':>7} {'사유':>6} {'수량':>4} {'순손익':>9} {'R':>6} {'결과':>4}")
    print("  " + "-" * 68)
    for _, t in df.iterrows():
        rs = {'take_profit':'익절','stop_loss':'손절','be_stop':'본전','time_force':'강제','eod':'마감'}.get(t['reason'], t['reason'])
        print(f"  {str(t['date']):>12} {t['symbol']:>5} ${t['entry']:>6.2f} ${t['exit']:>6.2f} {rs:>6} {t['shares']:>4} ${t['net']:>+8.2f} {t['r']:>+5.2f}R {t['result']:>4}")
    print()

    # ════════════════════════════════════════════════════════════
    # 타당성 평가
    # ════════════════════════════════════════════════════════════
    print("=" * 70)
    print("  알고리즘 타당성 평가")
    print("=" * 70)
    print()

    score = 0
    mx = 6

    if wr >= 40:
        print(f"  [PASS] 승률 {wr:.1f}% >= 40%"); score += 1
    elif wr >= 33:
        print(f"  [WARN] 승률 {wr:.1f}% >= 33% (마진 부족)"); score += 0.5
    else:
        print(f"  [FAIL] 승률 {wr:.1f}% < 33%")

    if pf >= 1.5:
        print(f"  [PASS] Profit Factor {pf:.2f} >= 1.5"); score += 1
    elif pf >= 1.0:
        print(f"  [WARN] Profit Factor {pf:.2f} >= 1.0"); score += 0.5
    else:
        print(f"  [FAIL] Profit Factor {pf:.2f} < 1.0")

    if exp > 0:
        print(f"  [PASS] 기대값 ${exp:+.2f} > 0"); score += 1
    else:
        print(f"  [FAIL] 기대값 ${exp:+.2f} <= 0")

    if abs(mdd) <= 15:
        print(f"  [PASS] MDD {mdd:.2f}% (안전)"); score += 1
    elif abs(mdd) <= 25:
        print(f"  [WARN] MDD {mdd:.2f}% (주의)"); score += 0.5
    else:
        print(f"  [FAIL] MDD {mdd:.2f}% (위험)")

    if n >= 30:
        print(f"  [PASS] {n}회 >= 30 (통계적 유의)"); score += 1
    elif n >= 15:
        print(f"  [WARN] {n}회 (제한적 유의)"); score += 0.5
    else:
        print(f"  [FAIL] {n}회 < 15 (통계적 의미 부족)")

    act_rr = abs(avg_w / avg_l) if avg_l != 0 else 0
    if act_rr >= 1.8:
        print(f"  [PASS] 실현 R:R 1:{act_rr:.2f}"); score += 1
    elif act_rr >= 1.0:
        print(f"  [WARN] 실현 R:R 1:{act_rr:.2f}"); score += 0.5
    else:
        print(f"  [FAIL] 실현 R:R 1:{act_rr:.2f}")

    print()
    print(f"  종합 점수: {score}/{mx} ({score/mx*100:.0f}%)")
    print()
    if score >= 5:
        verdict = "STRONG PASS - 실전 적용 검토 가능"
    elif score >= 3.5:
        verdict = "CONDITIONAL PASS - 파라미터 최적화 후 재검증"
    elif score >= 2:
        verdict = "WEAK - 추가 필터 보완 필요"
    else:
        verdict = "FAIL - 전략 재설계 필요"
    print(f"  종합 판정: {verdict}")

    print()
    print("─" * 70)
    print("  매매 방식 확인")
    print("─" * 70)
    print(f"  - 모든 거래: Long(매수) Only — 공매도 없음")
    print(f"  - 상승 추세 (QQQ > 20MA): TQQQ 매수 → ORB 상단 돌파 + FVG")
    print(f"  - 하락 추세 (QQQ < 20MA): SQQQ 매수 → ORB 상단 돌파 + FVG")
    print(f"  - SQQQ는 실제 SQQQ 5분봉 데이터 기반 (TQQQ 역산 아님)")
    print("=" * 70)

    return df, capital_history


if __name__ == "__main__":
    result = run_backtest()
    if result[0] is None:
        print("\n  거래 없음")
