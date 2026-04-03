# Casper Trading Bot - Design Spec

> Date: 2026-04-02
> Status: Approved

## Overview

TQQQ/SQQQ Long-Only 자동매매 봇. Casper 전략 (ORB + FVG + Pullback, R:R 1:2) 기반.
24시간 터미널 상주, 뉴욕장 09:30~11:00 ET 매매, 나머지 시간 대기.

## State Machine

```
WAITING → PRE_MARKET → ORB_FORMING → SCANNING → POSITION_OPEN → DONE_TODAY → WAITING
```

| State | Time (ET) | Action |
|-------|-----------|--------|
| WAITING | ~08:00 | 60s sleep loop |
| PRE_MARKET | 08:00~09:29 | VIX, QQQ MA20, macro event filters |
| ORB_FORMING | 09:30~09:44 | Collect 5m bars, compute ORB high/low |
| SCANNING | 09:45~10:55 | Check breakout + FVG per 5m bar |
| POSITION_OPEN | Entry~Exit | Monitor SL/TP/BE-move/force-close |
| DONE_TODAY | Post-trade | Save trade, wait for next day |

## Module Map

| Module | Responsibility | Lines |
|--------|---------------|-------|
| `run_bot.py` | Entry point | ~50 |
| `src/bot.py` | State machine + main loop | ~200 |
| `src/core/orb.py` | ORB calculation | ~80 |
| `src/core/fvg.py` | FVG detection | ~80 |
| `src/core/strategy.py` | Signal engine | ~150 |
| `src/core/position.py` | Position management | ~150 |
| `src/core/risk.py` | Filters + circuit breaker | ~120 |
| `src/api/kis_auth.py` | KIS token management | ~120 |
| `src/api/kis_client.py` | KIS REST client | ~150 |
| `src/api/kis_order.py` | Order execution | ~120 |
| `src/data/market_data.py` | Price data fetcher | ~150 |
| `src/data/trade_store.py` | Persistent trade history | ~120 |
| `src/telegram/notifier.py` | Telegram alerts | ~80 |
| `src/utils/config.py` | Config loader | ~60 |
| `src/utils/logger.py` | Logging setup | ~40 |
| `src/utils/time_utils.py` | Timezone utilities | ~80 |

## Key Decisions

1. **Long Only**: TQQQ (bull) / SQQQ (bear). No short selling.
2. **Paper/Live**: `.env` TRADING_MODE switches URL + order path.
3. **Persistence**: `data/trades/trades_YYYY.json` — never deleted, loaded on startup for CB state.
4. **Error Recovery**: 3 retries → DONE_TODAY on failure → auto-resume next day.
5. **KIS API for live quotes**: yfinance fallback for paper mode.
6. **All files < 1000 lines, functions < 200 lines**.
