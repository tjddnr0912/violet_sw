#!/usr/bin/env python3
"""
Intraday Strategy Comparison Backtest
=====================================
Evaluates 12 intraday strategies (incl. Casper baseline) on the same
TQQQ 5-min dataset, with identical commission, slippage, sizing, and
trading window — so the only thing that differs is the entry signal.

Strategies covered (all Long-only on TQQQ unless noted):
  Baseline:
    01. Casper-ORB-FVG (RR=3, dual-scan SQQQ also)         — production rules
    02. Casper-ORB-FVG-RR2  (same but RR=2 for sanity)

  Trend-following:
    03. VWAP Pullback Long
    04. EMA 9/21 Crossover Long
    05. MACD-Fast (5/34/5) Long
    06. Holy Grail (ADX>=25 + EMA20 pullback)

  Mean-reversion:
    07. RSI-2 Long (Connors, intraday)
    08. Bollinger Band (20,2) Reentry Long
    09. ORB Fade (false breakout reversal)
    10. Z-Score Reversion Long

  Breakout / Quant:
    11. NR7 Open ± 30%·ATR Breakout Long
    12. IB-60 Breakout Long  (09:30–10:30 IB, breakout 10:30–11:00)
    13. Intraday Momentum (09:30–09:45 ret>+0.5% → Long@09:45)
    14. Vol-Targeted EMA20 (ATR sized, EMA20 cross)

Same engine assumptions for fairness (KIS 미국주식 비용 모델 정밀):
  - Window: enter 09:45–10:55 ET only (Casper window)
  - Force close at 15:50 ET (or earlier on TP/SL)
  - Brokerage 0.25% per side (KIS online, truefriend.com 2026-05)
  - Slippage 차등: BUY 0.05%, TP 0.05%, STOP 0.10%, EOD 0.05%
  - SEC fee $0.0000278/$ + FINRA TAF $0.000166/share (매도 시)
  - 환전: USD 잔고 내 매매 가정 → 미적용
  - $1,500 initial capital, position-sized to fit capital, 1 trade/day max
  - All strategies see identical TQQQ 5-min OHLCV (yfinance, 60d)

Reads Casper config (config/strategy_params.json) so the baseline matches
production exactly.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import time as dtime, datetime
from typing import Optional, Callable, Dict, List

import numpy as np
import pandas as pd
import yfinance as yf

import warnings
warnings.filterwarnings('ignore')


# ─────────────────────────── CONFIG ────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAMS_PATH = os.path.join(ROOT, "config", "strategy_params.json")
with open(PARAMS_PATH) as f:
    CFG = json.load(f)

BULL = CFG["symbols"]["bull"]
BEAR = CFG["symbols"]["bear"]
TREND_SYM = CFG["symbols"]["trend_filter"]

# ──────────── KIS 미국주식 거래비용 모델 (정밀) ────────────
# 출처:
#   - 거래수수료: KIS 온라인 미국주식 0.25% per side (truefriend.com 2026-05)
#   - 환전 수수료: USD 잔고 내 매매 가정 → 트레이드별 미적용
#   - SEC fee: 2026년 $0.0000278 per dollar of sale (매도 시)
#   - FINRA TAF: $0.000166 per share (매도 시)
# 슬리피지는 청산 종류별 차등:
#   - 매수 / TP / 강제청산: limit 또는 우호적 fill — 0.05%
#   - SL (시장가 트리거): 0.10% (gap-down 시 더 악화)
BROKERAGE = CFG["commission"]["rate_per_side"]   # 0.0025 per side
SEC_RATE_SELL = 0.0000278                         # $/$ of sale value
TAF_PER_SHARE_SELL = 0.000166                     # $ per share sold

SLIP_BUY = 0.0005
SLIP_TP = 0.0005
SLIP_STOP = 0.0010
SLIP_TIME = 0.0005

RR_PRODUCTION = CFG["entry"]["rr_ratio"]           # 3.0
MIN_RISK = CFG["entry"]["min_risk_dollar"]
VIX_LOW = CFG["filters"]["vix_low"]
VIX_HIGH = CFG["filters"]["vix_high"]
MA_PERIOD = CFG["filters"]["ma_period"]
ORB_ATR_MAX = CFG["filters"]["orb_atr_max_ratio"]

INITIAL_CAPITAL = 1500.0
ENTRY_WINDOW_START = dtime(9, 45)   # signal can be triggered from this time
ENTRY_WINDOW_END = dtime(10, 55)    # last possible entry
BE_MOVE_TIME = dtime(11, 0)
FORCE_CLOSE_TIME = dtime(15, 50)


# ──────────────────── DATA INGESTION ─────────────────────────
def fetch_data():
    print("[data] downloading 60d 5m bars …")
    tqqq = yf.download(BULL, period="60d", interval="5m", progress=False, auto_adjust=False)
    qqq = yf.download(TREND_SYM, period="60d", interval="5m", progress=False, auto_adjust=False)
    sqqq = yf.download(BEAR, period="60d", interval="5m", progress=False, auto_adjust=False)
    qqq_d = yf.download(TREND_SYM, period="6mo", interval="1d", progress=False, auto_adjust=False)
    tqqq_d = yf.download(BULL, period="6mo", interval="1d", progress=False, auto_adjust=False)
    vix_d = yf.download("^VIX", period="6mo", interval="1d", progress=False, auto_adjust=False)

    # yfinance 1.2.0+ returns multiindex columns (level 0 = field, level 1 = ticker)
    def flatten(df):
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = [c[0] for c in df.columns]
        return df

    tqqq = flatten(tqqq)
    qqq = flatten(qqq)
    sqqq = flatten(sqqq)
    qqq_d = flatten(qqq_d)
    tqqq_d = flatten(tqqq_d)
    vix_d = flatten(vix_d)

    for df in (tqqq, qqq, sqqq):
        df.index = df.index.tz_convert("US/Eastern")
        df["date"] = df.index.date

    qqq_d["MA20"] = qqq_d["Close"].rolling(MA_PERIOD).mean()
    tqqq_d["ATR_HL"] = (tqqq_d["High"] - tqqq_d["Low"]).rolling(20).mean()

    return {
        "tqqq": tqqq, "qqq": qqq, "sqqq": sqqq,
        "qqq_d": qqq_d, "tqqq_d": tqqq_d, "vix_d": vix_d,
    }


# ──────────────────── INDICATOR HELPERS ─────────────────────────
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n):
    diff = s.diff()
    up = diff.clip(lower=0)
    dn = -diff.clip(upper=0)
    ma_up = up.ewm(alpha=1.0 / n, adjust=False).mean()
    ma_dn = dn.ewm(alpha=1.0 / n, adjust=False).mean()
    rs = ma_up / ma_dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df, n):
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def adx(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    idx = df.index
    up = h.diff()
    dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=idx)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=idx)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_n = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / n, adjust=False).mean() / atr_n.replace(0, np.nan)
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    out = dx.ewm(alpha=1.0 / n, adjust=False).mean().fillna(0)
    return out


def vwap(df):
    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv = tp * df["Volume"]
    return pv.cumsum() / df["Volume"].cumsum().replace(0, np.nan)


# ──────────────────── SIGNAL DATACLASS ─────────────────────────
@dataclass
class Sig:
    entry_time: pd.Timestamp
    entry_price: float
    stop: float
    target: float
    side: str = "long"
    note: str = ""
    rr_ratio: float = 0.0


# ──────────────────── STRATEGY IMPLEMENTATIONS ─────────────────────────
"""
Each strategy is a function:  sig(day_df, ctx) -> Optional[Sig]
day_df  -- full TQQQ 5m bars for a single calendar day, ET-indexed
ctx     -- dict with filter info (vix_ok, qqq_ma20_dir, sqqq_5m, etc.)
"""

def _bars_in_window(day_df, t0, t1):
    return day_df.between_time(t0.strftime("%H:%M"), t1.strftime("%H:%M"))


def _post_orb(day_df):
    return day_df.between_time("09:45", "10:55")


def _orb_15m(day_df):
    """Standard 09:30-09:44 ORB"""
    o = day_df.between_time("09:30", "09:44")
    if len(o) < 3:
        return None
    return float(o["High"].max()), float(o["Low"].min())


def _detect_bullish_fvg(c1, c2, c3):
    if c1["High"] < c3["Low"]:
        return c3["Low"], c1["High"]
    return None


# ────── helpers shared by ICT variants ──────
def _killzone_for_bar(ts):
    """09:30~10:10 = AM_MACRO, 10:10~10:55 = AM_LATE."""
    t = ts.time() if hasattr(ts, "time") else ts
    if dtime(9, 30) <= t < dtime(10, 10):
        return "AM_MACRO"
    if dtime(10, 10) <= t < dtime(10, 55):
        return "AM_LATE"
    return None


def _is_displacement_bar(bar, prev_window, atr_value, atr_mult=1.0,
                         prev_mult=1.5, max_wick=0.50):
    o = float(bar["Open"]); c = float(bar["Close"])
    h = float(bar["High"]); l = float(bar["Low"])
    if c <= o:
        return False
    body = c - o
    total = h - l
    if total <= 0:
        return False
    wick_ratio = (total - body) / total
    if wick_ratio >= max_wick:
        return False
    if atr_value is not None and atr_value > 0 and body < atr_value * atr_mult:
        return False
    if prev_window is not None and len(prev_window) >= 3:
        prev_body_mean = (prev_window["Close"] - prev_window["Open"]).abs().mean()
        if prev_body_mean > 0 and body < prev_body_mean * prev_mult:
            return False
    return True


def _atr14(bars):
    if bars is None or len(bars) < 15:
        return None
    h = bars["High"]; l = bars["Low"]; pc = bars["Close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    val = tr.rolling(14).mean().iloc[-1]
    return float(val) if not pd.isna(val) and val > 0 else None


# ────── Phase 2 helpers: swing + sweep + CHoCH ──────
def _swings(bars, left=2, right=2):
    if len(bars) < left + right + 1:
        return [], []
    H = bars["High"].values; L = bars["Low"].values; idx = bars.index
    sh = []; sl = []
    for i in range(left, len(bars) - right):
        if all(H[i] > H[j] for j in range(i-left, i)) and all(H[i] >= H[j] for j in range(i+1, i+right+1)):
            sh.append((idx[i], float(H[i])))
        if all(L[i] < L[j] for j in range(i-left, i)) and all(L[i] <= L[j] for j in range(i+1, i+right+1)):
            sl.append((idx[i], float(L[i])))
    return sh, sl


def _is_sweep(bar, level, side="up", min_breach=0.0005, min_wick=0.60):
    if level <= 0:
        return False
    h = float(bar["High"]); l = float(bar["Low"])
    o = float(bar["Open"]); c = float(bar["Close"])
    total = h - l
    if total <= 0:
        return False
    if side == "up":
        if (h - level) / level < min_breach: return False
        if c >= level: return False
        wick = h - max(o, c)
    else:
        if (level - l) / level < min_breach: return False
        if c <= level: return False
        wick = min(o, c) - l
    return (wick / total) >= min_wick


def _sweep_then_choch_until(bars_until_breakout, swing_highs, swing_lows,
                             levels_down, sweep_lookback=6, choch_lookback=6):
    """Composite bullish setup: SSL sweep then close > prior swing high."""
    if len(bars_until_breakout) == 0:
        return False
    win = bars_until_breakout.tail(sweep_lookback + choch_lookback)
    sweep_idx = None
    for ts, row in win.iterrows():
        for lvl in levels_down:
            if _is_sweep(row, lvl, side="down"):
                sweep_idx = ts
                break
        if sweep_idx:
            break
    if sweep_idx is None:
        return False
    after = win[win.index > sweep_idx].head(choch_lookback)
    if after.empty:
        return False
    for ts, row in after.iterrows():
        prior_sh = [p for p in swing_highs if p[0] < ts]
        if not prior_sh:
            continue
        last_sh_price = prior_sh[-1][1]
        if float(row["Close"]) > last_sh_price:
            return True
    return False


def _detect_bearish_fvg(c1, c2, c3):
    """Mirror of _detect_bullish_fvg for bearish setups.

    Returns (fvg_top, fvg_bot) where top = c1.Low, bot = c3.High.
    """
    if c1["Low"] > c3["High"]:
        return c1["Low"], c3["High"]
    return None


def _has_bearish_breakdown(candle, orb_low, strict=False):
    if not (candle["Close"] < orb_low and candle["Close"] < candle["Open"]):
        return False
    if strict and not (candle["Close"] <= orb_low <= candle["Open"]):
        return False
    return True


# ────── 01. Casper-ORB-FVG (RR=3, dual-scan via second symbol) ──────
def strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                 allowed_killzones=None, require_displacement=False,
                 disp_atr_mult=1.0, disp_max_wick=0.50, disp_prev_mult=1.5,
                 require_sweep_choch=False,
                 direction="bull"):
    """Casper production rule + optional ICT phase 1/2/3 filters."""
    o = _orb_15m(day_df)
    if o is None:
        return None
    orb_h, orb_l = o
    if ctx.get("avg_dr") and (orb_h - orb_l) > ctx["avg_dr"] * ORB_ATR_MAX:
        return None
    post = _post_orb(day_df)
    if len(post) < 4:
        return None
    atr_value = _atr14(day_df)
    if require_sweep_choch:
        sh, sl = _swings(day_df)
        levels_down = [orb_l] + [p[1] for p in sl[-5:]]
    else:
        sh = sl = []
        levels_down = []
    for i in range(1, len(post) - 1):
        c = post.iloc[i]
        if direction == "bear":
            if not _has_bearish_breakdown(c, orb_l, strict=strict):
                continue
        else:
            if not (c["Close"] > orb_h and c["Close"] > c["Open"]):
                continue
            if strict and not (c["Open"] <= orb_h <= c["Close"]):
                continue

        if allowed_killzones:
            if _killzone_for_bar(post.index[i]) not in allowed_killzones:
                continue

        if require_displacement:
            prev_win = post.iloc[max(0, i - 5):i]
            if not _is_displacement_bar(c, prev_win, atr_value,
                                        atr_mult=disp_atr_mult,
                                        prev_mult=disp_prev_mult,
                                        max_wick=disp_max_wick):
                # bullish-only displacement; bear has its own body criteria
                if direction == "bull":
                    continue

        if require_sweep_choch:
            bars_until = day_df.loc[:post.index[i]]
            if not _sweep_then_choch_until(bars_until, sh, sl,
                                           levels_down=levels_down,
                                           sweep_lookback=6,
                                           choch_lookback=6):
                continue

        c_prev = post.iloc[i - 1]
        c_next = post.iloc[i + 1]

        if direction == "bear":
            fvg = _detect_bearish_fvg(c_prev, c, c_next)
            if fvg is None:
                continue
            fvg_top, fvg_bot = fvg  # top = c1.Low, bot = c3.High
            if strict and not (fvg_bot <= orb_l <= fvg_top):
                continue
            entry = (fvg_top + fvg_bot) / 2
            stop = float(c_prev["High"])
            risk = stop - entry
            if risk < MIN_RISK:
                continue
            target = entry - risk * rr_ratio
            after = day_df[day_df.index > post.index[i + 1]].between_time("09:45", "15:50")
            for j in range(len(after)):
                if after.iloc[j]["High"] >= fvg_bot:
                    return Sig(after.index[j], entry, stop, target, side="short",
                               rr_ratio=rr_ratio,
                               note=f"casper_bear_rr{rr_ratio}")
            return None
        else:
            fvg = _detect_bullish_fvg(c_prev, c, c_next)
            if fvg is None:
                continue
            fvg_top, fvg_bot = fvg
            if strict and not (fvg_bot <= orb_h <= fvg_top):
                continue
            entry = (fvg_top + fvg_bot) / 2
            stop = float(c_prev["Low"])
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * rr_ratio
            after = day_df[day_df.index > post.index[i + 1]].between_time("09:45", "15:50")
            for j in range(len(after)):
                if after.iloc[j]["Low"] <= fvg_top:
                    return Sig(after.index[j], entry, stop, target, rr_ratio=rr_ratio,
                               note=f"casper_strict_rr{rr_ratio}")
            return None
    return None


def strat_casper_rr2(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=2.0)


# ────── 15. Casper + ICT Killzone (AM_MACRO only) ──────
def strat_casper_ict_killzone(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO"})


# ────── 16. Casper + ICT Displacement ──────
def strat_casper_ict_disp(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        require_displacement=True,
                        disp_atr_mult=1.0, disp_max_wick=0.50,
                        disp_prev_mult=1.5)


# ────── 17. Casper + ICT Killzone + Displacement (combined) ──────
def strat_casper_ict_combo(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO"},
                        require_displacement=True,
                        disp_atr_mult=1.0, disp_max_wick=0.50,
                        disp_prev_mult=1.5)


# ────── 18. Casper RR2 + ICT Phase-1 combo ──────
def strat_casper_rr2_ict_combo(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=2.0, strict=True,
                        allowed_killzones={"AM_MACRO"},
                        require_displacement=True,
                        disp_atr_mult=1.0, disp_max_wick=0.50,
                        disp_prev_mult=1.5)


# ────── Phase 2 variants ──────
def strat_casper_sweep(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        require_sweep_choch=True)


def strat_casper_sweep_kz(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO"},
                        require_sweep_choch=True)


def strat_casper_full_ict(day_df, ctx):
    """Phase 1 + Phase 2 full ICT stack."""
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO"},
                        require_displacement=True,
                        disp_atr_mult=1.0, disp_max_wick=0.50,
                        disp_prev_mult=1.5,
                        require_sweep_choch=True)


def strat_casper_rr2_full_ict(day_df, ctx):
    return strat_casper(day_df, ctx, rr_ratio=2.0, strict=True,
                        allowed_killzones={"AM_MACRO"},
                        require_displacement=True,
                        disp_atr_mult=1.0, disp_max_wick=0.50,
                        disp_prev_mult=1.5,
                        require_sweep_choch=True)


# ────── 03. VWAP Pullback Long ──────
def strat_vwap_pullback(day_df, ctx):
    """First VWAP pullback after a bullish breakout above 09:30-09:45 high."""
    o = _orb_15m(day_df)
    if o is None:
        return None
    orb_h, _ = o
    df = day_df.copy()
    df["VWAP"] = vwap(df)
    post = _post_orb(df)
    crossed_above = False
    pullback_idx = None
    for i in range(len(post)):
        c = post.iloc[i]
        if not crossed_above:
            if c["Close"] > orb_h and c["Close"] > c["VWAP"]:
                crossed_above = True
            continue
        # pullback: low touches VWAP and close back above
        if c["Low"] <= c["VWAP"] and c["Close"] > c["VWAP"]:
            pullback_idx = i
            break
    if pullback_idx is None:
        return None
    bar = post.iloc[pullback_idx]
    entry = float(bar["Close"])
    stop = float(min(bar["Low"], bar["VWAP"] * 0.997))
    risk = entry - stop
    if risk < MIN_RISK:
        return None
    target = entry + risk * 2.0
    return Sig(post.index[pullback_idx], entry, stop, target, rr_ratio=2.0, note="vwap_pull")


# ────── 04. EMA 9/21 Cross Long ──────
def strat_ema_cross(day_df, ctx):
    df = day_df.copy()
    df["E9"] = ema(df["Close"], 9)
    df["E21"] = ema(df["Close"], 21)
    df["RSI14"] = rsi(df["Close"], 14)
    post = _post_orb(df)
    for i in range(2, len(post)):
        prev = post.iloc[i - 1]
        cur = post.iloc[i]
        if prev["E9"] <= prev["E21"] and cur["E9"] > cur["E21"] and cur["RSI14"] >= 50:
            entry = float(cur["Close"])
            stop = float(min(cur["E21"], post.iloc[i - 2:i + 1]["Low"].min()))
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * 2.0
            return Sig(post.index[i], entry, stop, target, rr_ratio=2.0, note="ema_cross")
    return None


# ────── 05. MACD-Fast (5/34/5) Long ──────
def strat_macd_fast(day_df, ctx):
    df = day_df.copy()
    df["MACD"] = ema(df["Close"], 5) - ema(df["Close"], 34)
    df["SIG"] = ema(df["MACD"], 5)
    df["HIST"] = df["MACD"] - df["SIG"]
    post = _post_orb(df)
    for i in range(3, len(post)):
        prev = post.iloc[i - 1]
        cur = post.iloc[i]
        cross = prev["MACD"] <= prev["SIG"] and cur["MACD"] > cur["SIG"]
        zero_ok = cur["MACD"] > 0
        # 3 consecutive expanding histograms
        h0 = post.iloc[i - 2]["HIST"]
        h1 = post.iloc[i - 1]["HIST"]
        h2 = cur["HIST"]
        expand = h2 > h1 > h0
        if cross and zero_ok and expand:
            entry = float(cur["Close"])
            recent_low = float(post.iloc[max(0, i - 3):i + 1]["Low"].min())
            stop = recent_low
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * 2.0
            return Sig(post.index[i], entry, stop, target, rr_ratio=2.0, note="macd_fast")
    return None


# ────── 06. Holy Grail (ADX>=25 + EMA20 pullback) ──────
def strat_holy_grail(day_df, ctx):
    df = day_df.copy()
    df["E20"] = ema(df["Close"], 20)
    df["ADX"] = adx(df, 14)
    post = _post_orb(df)
    for i in range(3, len(post)):
        cur = post.iloc[i]
        prev = post.iloc[i - 1]
        if cur["ADX"] < 25:
            continue
        if cur["Close"] < cur["E20"]:
            continue
        # recent pullback to EMA20 then bounce
        recent = post.iloc[i - 3:i + 1]
        touched_ema = (recent["Low"] <= recent["E20"]).any()
        if not touched_ema:
            continue
        if not (cur["Close"] > prev["High"]):
            continue
        entry = float(cur["Close"])
        stop = float(recent["Low"].min())
        risk = entry - stop
        if risk < MIN_RISK:
            continue
        target = entry + risk * 2.0
        return Sig(post.index[i], entry, stop, target, rr_ratio=2.0, note="holy_grail")
    return None


# ────── 07. RSI-2 Long (Connors intraday) ──────
def strat_rsi2(day_df, ctx):
    df = day_df.copy()
    df["E200"] = ema(df["Close"], 200)
    df["RSI2"] = rsi(df["Close"], 2)
    post = _post_orb(df)
    for i in range(len(post)):
        cur = post.iloc[i]
        if pd.isna(cur["E200"]):
            continue
        if cur["Close"] < cur["E200"]:
            continue
        if cur["RSI2"] < 10:
            entry = float(cur["Close"])
            atr_now = (post.iloc[max(0, i - 14):i + 1]["High"]
                       - post.iloc[max(0, i - 14):i + 1]["Low"]).mean()
            stop = entry - 1.5 * atr_now if atr_now > 0 else entry * 0.99
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * 1.5  # mean-reversion -> shorter R:R
            return Sig(post.index[i], entry, stop, target, rr_ratio=1.5, note="rsi2")
    return None


# ────── 08. Bollinger Band Reentry Long ──────
def strat_bb_reentry(day_df, ctx):
    df = day_df.copy()
    n = 20
    sigma = 2.0
    ma = df["Close"].rolling(n).mean()
    sd = df["Close"].rolling(n).std()
    df["LB"] = ma - sigma * sd
    df["UB"] = ma + sigma * sd
    df["MB"] = ma
    post = _post_orb(df)
    breached = False
    for i in range(len(post)):
        cur = post.iloc[i]
        if pd.isna(cur["LB"]):
            continue
        if not breached:
            if cur["Close"] < cur["LB"]:
                breached = True
            continue
        if cur["Close"] > cur["LB"]:
            entry = float(cur["Close"])
            stop = float(post.iloc[max(0, i - 5):i + 1]["Low"].min())
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = float(cur["MB"])
            if target <= entry:
                continue
            return Sig(post.index[i], entry, stop, target,
                       rr_ratio=(target - entry) / risk, note="bb_reentry")
    return None


# ────── 09. ORB Fade (false-breakout reversal Long) ──────
def strat_orb_fade(day_df, ctx):
    """Bullish ORB false-breakdown: gap below ORB low → reclaim ORB low → Long."""
    o = _orb_15m(day_df)
    if o is None:
        return None
    orb_h, orb_l = o
    post = _post_orb(day_df)
    breached_down = False
    for i in range(len(post)):
        cur = post.iloc[i]
        if not breached_down:
            if cur["Low"] < orb_l and cur["Close"] < orb_l:
                breached_down = True
            continue
        if cur["Close"] > orb_l:
            entry = float(cur["Close"])
            stop = float(min(post.iloc[max(0, i - 3):i + 1]["Low"].min(), orb_l - 0.05))
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = float((orb_l + orb_h) / 2)  # mid-ORB
            if target <= entry:
                target = entry + risk * 1.5
            return Sig(post.index[i], entry, stop, target,
                       rr_ratio=(target - entry) / risk, note="orb_fade")
    return None


# ────── 10. Z-Score Reversion Long ──────
def strat_zscore(day_df, ctx):
    df = day_df.copy()
    n = 20
    ma = df["Close"].rolling(n).mean()
    sd = df["Close"].rolling(n).std()
    df["Z"] = (df["Close"] - ma) / sd.replace(0, np.nan)
    post = _post_orb(df)
    for i in range(len(post)):
        cur = post.iloc[i]
        if pd.isna(cur["Z"]):
            continue
        if cur["Z"] < -2.0:
            entry = float(cur["Close"])
            stop = entry * (1 - 0.012)  # 1.2% hard stop
            target = float(ma.loc[post.index[i]])
            if target <= entry:
                continue
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            return Sig(post.index[i], entry, stop, target,
                       rr_ratio=(target - entry) / risk, note="zscore")
    return None


# ────── 11. NR7 Open ± 30%·ATR Breakout Long ──────
def strat_nr7(day_df, ctx):
    """Trade only if PREVIOUS day was an NR7 (narrow range relative to last 7 days)."""
    if not ctx.get("is_nr7"):
        return None
    atr_d = ctx.get("atr_daily", 0.0)
    open_px = ctx.get("today_open")
    if open_px is None or atr_d <= 0:
        return None
    trigger = open_px + 0.30 * atr_d
    post = _post_orb(day_df)
    for i in range(len(post)):
        cur = post.iloc[i]
        if cur["High"] >= trigger and cur["Close"] > open_px:
            entry = float(max(cur["Open"], trigger))
            stop = float(open_px - 0.30 * atr_d)
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * 2.0
            return Sig(post.index[i], entry, stop, target, rr_ratio=2.0, note="nr7")
    return None


# ────── 12. IB-60 Breakout Long ──────
def strat_ib_breakout(day_df, ctx):
    """09:30-10:30 = IB. Breakout above IB high in 10:30-11:00 → Long."""
    ib = day_df.between_time("09:30", "10:29")
    if len(ib) < 6:
        return None
    ib_h = float(ib["High"].max())
    ib_l = float(ib["Low"].min())
    ib_mid = (ib_h + ib_l) / 2
    after = day_df.between_time("10:30", "10:55")
    for i in range(len(after)):
        cur = after.iloc[i]
        if cur["Close"] > ib_h:
            entry = float(cur["Close"])
            stop = ib_mid
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + (ib_h - ib_l)  # 100% extension
            return Sig(after.index[i], entry, stop, target,
                       rr_ratio=(target - entry) / risk, note="ib_brk")
    return None


# ────── 13. Intraday Momentum (open-09:45 ret > 0.5%) ──────
def strat_intraday_momo(day_df, ctx):
    open_bar = day_df.between_time("09:30", "09:34")
    last_bar = day_df.between_time("09:40", "09:44")
    if len(open_bar) == 0 or len(last_bar) == 0:
        return None
    o0 = float(open_bar.iloc[0]["Open"])
    c0 = float(last_bar.iloc[-1]["Close"])
    ret = (c0 - o0) / o0
    if ret < 0.005:
        return None
    # enter at first 09:45+ bar
    post = _post_orb(day_df)
    if len(post) == 0:
        return None
    bar = post.iloc[0]
    entry = float(bar["Open"])
    stop = float(min(open_bar.iloc[0]["Low"], last_bar.iloc[-1]["Low"]))
    risk = entry - stop
    if risk < MIN_RISK:
        return None
    target = entry + risk * 2.0
    return Sig(post.index[0], entry, stop, target, rr_ratio=2.0, note="momo")


# ────── 14. Vol-Targeted EMA20 Cross ──────
def strat_voltarget_ema(day_df, ctx):
    df = day_df.copy()
    df["E20"] = ema(df["Close"], 20)
    df["ATR14"] = atr(df, 14)
    post = _post_orb(df)
    for i in range(3, len(post)):
        prev = post.iloc[i - 1]
        cur = post.iloc[i]
        if prev["Close"] <= prev["E20"] and cur["Close"] > cur["E20"]:
            atr_v = float(cur["ATR14"]) if not pd.isna(cur["ATR14"]) else 0
            if atr_v <= 0:
                continue
            entry = float(cur["Close"])
            stop = entry - 1.5 * atr_v
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            target = entry + risk * 2.0
            return Sig(post.index[i], entry, stop, target, rr_ratio=2.0, note="vt_ema")
    return None


STRATEGIES: List[tuple] = [
    ("01_Casper_RR3",      strat_casper,         "ORB+FVG strict, RR=3 (production)"),
    ("02_Casper_RR2",      strat_casper_rr2,     "ORB+FVG strict, RR=2 (sanity)"),
    ("03_VWAP_Pullback",   strat_vwap_pullback,  "VWAP first pullback Long"),
    ("04_EMA_9_21",        strat_ema_cross,      "EMA 9/21 golden cross + RSI>=50"),
    ("05_MACD_Fast",       strat_macd_fast,      "MACD 5/34/5 cross above zero"),
    ("06_Holy_Grail",      strat_holy_grail,     "ADX>=25 + EMA20 pullback bounce"),
    ("07_RSI2",            strat_rsi2,           "Connors RSI-2 < 10 above EMA200"),
    ("08_BB_Reentry",      strat_bb_reentry,     "BB(20,2) lower-band breach reentry"),
    ("09_ORB_Fade",        strat_orb_fade,       "ORB false-breakdown reclaim Long"),
    ("10_ZScore",          strat_zscore,         "Rolling 20-bar z-score < -2"),
    ("11_NR7_Brk",         strat_nr7,            "NR7 day Open + 0.3·ATR breakout"),
    ("12_IB60_Brk",        strat_ib_breakout,    "60-min IB breakout (10:30 onward)"),
    ("13_Momentum",        strat_intraday_momo,  "First 15-min ret>+0.5% → Long"),
    ("14_VT_EMA20",        strat_voltarget_ema,  "Vol-targeted EMA20 cross + 1.5ATR stop"),
    # ── ICT Phase 1 variants ──
    ("15_Casper_KZ",       strat_casper_ict_killzone, "Casper + AM_MACRO killzone only"),
    ("16_Casper_Disp",     strat_casper_ict_disp,     "Casper + Displacement filter (ATR≥1, wick<50%)"),
    ("17_Casper_KZ_Disp",  strat_casper_ict_combo,    "Casper + KZ + Displacement (combo)"),
    ("18_Casper_RR2_KZ_D", strat_casper_rr2_ict_combo,"Casper RR2 + KZ + Displacement"),
    # ── ICT Phase 2 variants ──
    ("19_Casper_Sweep",    strat_casper_sweep,        "Casper + sweep+CHoCH gate"),
    ("20_Casper_Swp_KZ",   strat_casper_sweep_kz,     "Casper + KZ + sweep+CHoCH"),
    ("21_Casper_FullICT",  strat_casper_full_ict,     "Casper + KZ + Disp + Sweep (full)"),
    ("22_Casper_RR2_Full", strat_casper_rr2_full_ict, "Casper RR2 + full ICT stack"),
]


# ──────────────────── EXECUTION ENGINE ─────────────────────────
@dataclass
class Trade:
    strategy: str
    date: str
    entry_t: str
    entry_price: float
    stop: float
    target: float
    exit_t: str
    exit_price: float
    exit_reason: str
    shares: int
    gross_pnl: float
    commission: float
    slippage: float
    net_pnl: float
    r_multiple: float
    result: str  # WIN / LOSS / BE


def simulate_trade(strategy_name, day_df, sig, capital, rr_be_move=True):
    if sig is None:
        return None
    after = day_df[day_df.index >= sig.entry_time].between_time("09:45", "15:55")
    if len(after) == 0:
        return None

    eff_entry = sig.entry_price * (1 + SLIP_BUY)
    shares = int(capital / eff_entry)
    if shares < 1:
        return None
    risk_ps = eff_entry - sig.stop
    if risk_ps <= 0:
        return None

    stop = sig.stop
    target = sig.target
    sl_moved = False
    # BE = eff_entry × (1 + brokerage_round_trip + slip_buy + slip_sell)
    be_price = eff_entry * (1 + BROKERAGE * 2 + SLIP_BUY + SLIP_TP)

    exit_price = None
    exit_time = None
    exit_reason = None

    for k in range(len(after)):
        bar = after.iloc[k]
        bt = after.index[k]
        ct = bt.time()

        if rr_be_move and ct >= BE_MOVE_TIME and not sl_moved:
            sl_moved = True
            stop = max(stop, be_price)

        if ct >= FORCE_CLOSE_TIME:
            exit_price = float(bar["Close"])
            exit_time = bt
            exit_reason = "time_force"
            break

        if bar["Low"] <= stop:
            exit_price = stop
            exit_time = bt
            exit_reason = "be_stop" if sl_moved else "stop_loss"
            break
        if bar["High"] >= target:
            exit_price = target
            exit_time = bt
            exit_reason = "take_profit"
            break

    if exit_price is None:
        exit_price = float(after.iloc[-1]["Close"])
        exit_time = after.index[-1]
        exit_reason = "eod"

    # 청산 사유별 슬리피지 (실거래 차등)
    if exit_reason == "take_profit":
        slip_exit = SLIP_TP
    elif exit_reason in ("stop_loss", "be_stop"):
        slip_exit = SLIP_STOP
    else:
        slip_exit = SLIP_TIME

    eff_exit = exit_price * (1 - slip_exit)

    gross = (eff_exit - eff_entry) * shares
    # 거래수수료: 양 사이드 0.25%
    brokerage = (eff_entry + eff_exit) * shares * BROKERAGE
    # SEC + FINRA TAF (매도 시만)
    sec_taf = (eff_exit * shares * SEC_RATE_SELL) + (shares * TAF_PER_SHARE_SELL)
    comm = brokerage + sec_taf
    slip = (sig.entry_price * SLIP_BUY + exit_price * slip_exit) * shares
    net = gross - comm
    r_mult = net / (risk_ps * shares) if risk_ps * shares > 0 else 0

    if exit_reason == "take_profit":
        result = "WIN"
    elif exit_reason in ("stop_loss", "be_stop"):
        result = "LOSS" if net < -0.01 else "BE"
    else:
        result = "WIN" if net > 0 else ("BE" if abs(net) < 0.5 else "LOSS")

    return Trade(
        strategy=strategy_name,
        date=str(after.index[0].date()),
        entry_t=sig.entry_time.strftime("%H:%M"),
        entry_price=round(eff_entry, 2),
        stop=round(sig.stop, 2),
        target=round(sig.target, 2),
        exit_t=exit_time.strftime("%H:%M") if exit_time else "-",
        exit_price=round(exit_price, 2),
        exit_reason=exit_reason,
        shares=shares,
        gross_pnl=round(gross, 2),
        commission=round(comm, 2),
        slippage=round(slip, 2),
        net_pnl=round(net, 2),
        r_multiple=round(r_mult, 2),
        result=result,
    )


def run_strategy(name, sig_fn, days, data, vix_filter=True, trend_filter=True):
    capital = INITIAL_CAPITAL
    trades: List[Trade] = []
    cap_history = [(days[0], capital)]
    skipped = {"vix": 0, "no_signal": 0, "no_data": 0}

    tqqq = data["tqqq"]
    tqqq_d = data["tqqq_d"]
    qqq_d = data["qqq_d"]
    vix_d = data["vix_d"]

    for d in days:
        # context
        ctx = {}
        if vix_filter:
            v = vix_d[vix_d.index.date <= d]
            if len(v) > 0:
                vv = float(v.iloc[-1]["Close"])
                if not (VIX_LOW <= vv <= VIX_HIGH):
                    skipped["vix"] += 1
                    continue

        # daily ATR-HL average for ORB-width filter
        recent_d = tqqq_d[tqqq_d.index.date <= d].tail(20)
        ctx["avg_dr"] = float((recent_d["High"] - recent_d["Low"]).mean()) if len(recent_d) >= 5 else 0

        # NR7 context
        if len(recent_d) >= 8:
            ranges = (recent_d["High"] - recent_d["Low"]).values
            today_ranges = ranges[:-1][-7:]  # last 7 days excluding today
            yesterday_range = ranges[-1] if len(ranges) > 0 else None
            # NR7 = yesterday's range was narrower than each of preceding 6 trading days
            if len(today_ranges) >= 7:
                ctx["is_nr7"] = bool(today_ranges[-1] == today_ranges.min())
            else:
                ctx["is_nr7"] = False
            ctx["atr_daily"] = float(np.mean(today_ranges)) if len(today_ranges) > 0 else 0
        else:
            ctx["is_nr7"] = False
            ctx["atr_daily"] = 0

        # today open
        today_data = tqqq[tqqq["date"] == d]
        if len(today_data) == 0:
            skipped["no_data"] += 1
            continue
        ctx["today_open"] = float(today_data.iloc[0]["Open"])

        # signal
        sig = sig_fn(today_data, ctx)
        if sig is None:
            skipped["no_signal"] += 1
            continue

        trade = simulate_trade(name, today_data, sig, capital)
        if trade is None:
            skipped["no_signal"] += 1
            continue
        capital += trade.net_pnl
        trades.append(trade)
        cap_history.append((d, capital))

    return trades, capital, cap_history, skipped


# ──────────────────── MARKET-REGIME LABELING ─────────────────────────
def classify_day(qqq_5m, qqq_d, day):
    """Label a day as TREND_UP, TREND_DOWN, RANGE, or VOLATILE."""
    today = qqq_5m[qqq_5m["date"] == day]
    if len(today) < 50:
        return "UNKNOWN"
    o = float(today.iloc[0]["Open"])
    c = float(today.iloc[-1]["Close"])
    h = float(today["High"].max())
    l = float(today["Low"].min())
    rng_pct = (h - l) / o * 100 if o > 0 else 0
    body_pct = (c - o) / o * 100 if o > 0 else 0
    body_ratio = abs(body_pct) / rng_pct if rng_pct > 0 else 0
    # body_ratio > 0.6 → strong directional day; < 0.3 → range
    if rng_pct > 4.0 and body_ratio > 0.6:
        return "TREND_UP" if body_pct > 0 else "TREND_DOWN"
    if body_ratio > 0.6:
        return "TREND_UP" if body_pct > 0 else "TREND_DOWN"
    if body_ratio < 0.30:
        return "RANGE"
    return "MIXED"


# ──────────────────── METRICS ─────────────────────────
def metrics(trades, cap_hist, days_total, regime_map=None):
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0, "trades_per_day": 0.0, "win_rate": 0.0,
            "total_return_pct": 0.0, "cagr_pct": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "avg_r": 0.0,
            "max_dd_pct": 0.0, "sharpe": 0.0, "sortino": 0.0,
            "avg_hold_min": 0.0, "trend_up_winrate": np.nan,
            "trend_down_winrate": np.nan, "range_winrate": np.nan,
            "final_capital": INITIAL_CAPITAL,
        }
    wins = sum(1 for t in trades if t.result == "WIN")
    losses = sum(1 for t in trades if t.result == "LOSS")
    win_sum = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    loss_sum = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    pf = win_sum / loss_sum if loss_sum > 0 else float('inf')
    avg_w = (win_sum / max(wins, 1)) if wins > 0 else 0
    avg_l = (-loss_sum / max(losses, 1)) if losses > 0 else 0
    wr = wins / n
    expectancy = wr * avg_w + (1 - wr) * avg_l
    avg_r = np.mean([t.r_multiple for t in trades])

    caps = pd.Series([c for _, c in cap_hist])
    pk = caps.expanding().max()
    dd_series = (caps - pk) / pk * 100
    mdd = dd_series.min()
    final_cap = caps.iloc[-1]
    total_ret = (final_cap - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    # trade-by-trade R series
    rs = np.array([t.r_multiple for t in trades])
    sharpe = (rs.mean() / rs.std()) * math.sqrt(252) if rs.std() > 0 else 0
    downside = rs[rs < 0]
    dn_std = downside.std() if len(downside) > 1 else 0
    sortino = (rs.mean() / dn_std) * math.sqrt(252) if dn_std > 0 else 0

    # CAGR (252 trading days)
    period_days = days_total
    if period_days > 0 and final_cap > 0:
        cagr = ((final_cap / INITIAL_CAPITAL) ** (252 / period_days) - 1) * 100
    else:
        cagr = 0

    # avg holding (assume 5m bars between entry/exit)
    holds = []
    for t in trades:
        try:
            et = datetime.strptime(t.entry_t, "%H:%M")
            xt = datetime.strptime(t.exit_t, "%H:%M")
            holds.append((xt - et).seconds / 60.0)
        except Exception:
            pass
    avg_hold = float(np.mean(holds)) if holds else 0

    # regime breakdown
    if regime_map:
        def wr_subset(label):
            sub = [t for t in trades if regime_map.get(t.date) == label]
            if not sub:
                return float('nan')
            w = sum(1 for t in sub if t.result == "WIN")
            return w / len(sub)
        tu_wr = wr_subset("TREND_UP")
        td_wr = wr_subset("TREND_DOWN")
        r_wr = wr_subset("RANGE")
    else:
        tu_wr = td_wr = r_wr = float('nan')

    return {
        "n_trades": n,
        "trades_per_day": round(n / days_total, 3) if days_total else 0,
        "win_rate": round(wr * 100, 1),
        "total_return_pct": round(total_ret, 2),
        "cagr_pct": round(cagr, 2),
        "profit_factor": round(pf, 2) if pf != float('inf') else 99.99,
        "expectancy": round(expectancy, 2),
        "avg_r": round(avg_r, 2),
        "max_dd_pct": round(mdd, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "avg_hold_min": round(avg_hold, 1),
        "trend_up_winrate": round(tu_wr * 100, 1) if not np.isnan(tu_wr) else None,
        "trend_down_winrate": round(td_wr * 100, 1) if not np.isnan(td_wr) else None,
        "range_winrate": round(r_wr * 100, 1) if not np.isnan(r_wr) else None,
        "final_capital": round(final_cap, 2),
    }


# ──────────────────── MAIN ─────────────────────────
def main():
    print("=" * 80)
    print("  Intraday Strategy Comparison — KIS 정밀 비용 모델")
    print("=" * 80)
    print(f"  Brokerage:   {BROKERAGE*100:.3f}% per side  (KIS 온라인 미국주식)")
    print(f"  Slippage:    BUY {SLIP_BUY*100:.3f}%  TP {SLIP_TP*100:.3f}%  "
          f"STOP {SLIP_STOP*100:.3f}%  EOD {SLIP_TIME*100:.3f}%")
    print(f"  SEC+TAF:     {SEC_RATE_SELL*100:.5f}% of sale + ${TAF_PER_SHARE_SELL:.6f}/share")
    print(f"  환전:        USD 잔고 내 매매 가정 (per-trade 0)")
    print(f"  Initial cap: ${INITIAL_CAPITAL:,.0f}  Max 1 trade/day")
    print()

    data = fetch_data()
    tqqq = data["tqqq"]
    qqq = data["qqq"]
    common_days = sorted(set(tqqq["date"].unique()) & set(qqq["date"].unique()))
    print(f"[main] common days: {len(common_days)}  range {common_days[0]} ~ {common_days[-1]}")

    # regime map
    print("[main] classifying market regime per day …")
    regime = {str(d): classify_day(qqq, data["qqq_d"], d) for d in common_days}
    counts = pd.Series(list(regime.values())).value_counts()
    print("  regime counts:", dict(counts))

    results = {}
    print("\n[main] running strategies …")
    for name, fn, desc in STRATEGIES:
        print(f"  ▶ {name}: {desc}")
        trades, final_cap, cap_hist, skipped = run_strategy(name, fn, common_days, data)
        m = metrics(trades, cap_hist, len(common_days), regime_map=regime)
        results[name] = {"desc": desc, "metrics": m, "trades": [asdict(t) for t in trades],
                          "skipped": skipped}
        print(f"    trades={m['n_trades']:>3}  WR={m['win_rate']:>5.1f}%  "
              f"PF={m['profit_factor']:>5.2f}  Ret={m['total_return_pct']:>+6.2f}%  "
              f"MDD={m['max_dd_pct']:>+6.2f}%  Sharpe={m['sharpe']:>5.2f}")

    # save JSON
    out_dir = os.path.join(ROOT, "scripts", "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "intraday_compare_results.json")
    with open(out_path, "w") as f:
        json.dump({"period_days": len(common_days),
                   "regime_counts": dict(counts),
                   "results": results}, f, indent=2, default=str)
    print(f"\n[main] saved → {out_path}")

    # summary table
    print("\n" + "=" * 110)
    print("  COMPARISON TABLE")
    print("=" * 110)
    header = f"{'Strategy':<22s} {'Trd':>4s} {'Tr/d':>5s} {'WR%':>6s} {'Ret%':>7s} {'PF':>5s} {'AvgR':>6s} {'MDD%':>7s} {'Shrp':>5s} {'Sort':>5s} {'Hld':>5s}"
    print(header)
    print("-" * 110)
    for name, _, _ in STRATEGIES:
        m = results[name]["metrics"]
        print(f"{name:<22s} {m['n_trades']:>4d} {m['trades_per_day']:>5.2f} "
              f"{m['win_rate']:>6.1f} {m['total_return_pct']:>+7.2f} "
              f"{m['profit_factor']:>5.2f} {m['avg_r']:>+6.2f} "
              f"{m['max_dd_pct']:>+7.2f} {m['sharpe']:>5.2f} {m['sortino']:>5.2f} "
              f"{m['avg_hold_min']:>5.1f}")

    # regime breakdown
    print("\n" + "=" * 110)
    print("  REGIME BREAKDOWN (Win Rate %, only when trades happened in that regime)")
    print("=" * 110)
    print(f"{'Strategy':<22s} {'TR_UP':>8s} {'TR_DN':>8s} {'RANGE':>8s}")
    print("-" * 60)
    for name, _, _ in STRATEGIES:
        m = results[name]["metrics"]
        u = f"{m['trend_up_winrate']:.1f}%" if m['trend_up_winrate'] is not None else " - "
        d = f"{m['trend_down_winrate']:.1f}%" if m['trend_down_winrate'] is not None else " - "
        r = f"{m['range_winrate']:.1f}%" if m['range_winrate'] is not None else " - "
        print(f"{name:<22s} {u:>8s} {d:>8s} {r:>8s}")

    return results


if __name__ == "__main__":
    main()
