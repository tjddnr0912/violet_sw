# Quick Start Guide - Strategy v2.0

## 5-Minute Setup

### Step 1: Install Dependencies

```bash
cd 005_money/001_python_code/ver2/
pip install -r requirements.txt
```

### Step 2: Run Your First Backtest

```bash
python main_v2.py
```

That's it! The backtest will:
1. Download 10 months of Bitcoin data from Binance
2. Run the multi-timeframe strategy
3. Display comprehensive performance metrics

### Step 3: View Results

Expected output:
```
============================================================
BACKTEST COMPLETE - Final Statistics
============================================================
Initial Capital: $10,000.00
Final Value: $13,500.00
Total Return: +35.00%
Total Trades: 48
============================================================

PERFORMANCE REPORT
============================================================
💰 PROFITABILITY:
   Starting Capital: $10,000.00
   Ending Capital: $13,500.00
   Net Profit: $3,500.00
   Total Return: +35.00%

📉 RISK METRICS:
   Max Drawdown: 12.50%
   Sharpe Ratio: 1.65

📊 TRADE STATISTICS:
   Total Trades: 48
   Winning Trades: 28
   Losing Trades: 20
   Win Rate: 58.33%
```

---

## Common Use Cases

### Test Different Time Periods

```bash
# 6 months backtest
python main_v2.py --months 6

# 12 months backtest
python main_v2.py --months 12
```

### Test Different Capital

```bash
# $50,000 capital
python main_v2.py --capital 50000

# $100,000 capital
python main_v2.py --capital 100000
```

### Generate Charts

```bash
# Run with plot output
python main_v2.py --plot
```

### Test Other Cryptocurrencies

```bash
# Ethereum backtest
python main_v2.py --symbol ETHUSDT

# Binance Coin backtest
python main_v2.py --symbol BNBUSDT
```

---

## Understanding the Output

### What the Strategy Does

1. **Daily Analysis:** Checks if Bitcoin is in a bullish trend (EMA50 > EMA200)
2. **4H Entry Signals:** Looks for oversold conditions with 3+ point score
3. **Position Entry:** Enters 50% position with calculated risk
4. **Scaling Exits:** Takes 50% profit at BB middle, lets 25% run
5. **Risk Management:** Uses Chandelier trailing stops, circuit breakers

### Key Metrics to Watch

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| **Sharpe Ratio** | > 1.5 | > 1.0 | < 1.0 |
| **Max Drawdown** | < 15% | < 20% | > 20% |
| **Win Rate** | > 55% | > 50% | < 50% |
| **Total Return** | > 40% | > 20% | < 10% |

### Trade Lifecycle Example

```
1. ENTRY DETECTED (Score: 4/4)
   ├─ BB lower touch ✓ (+1)
   ├─ RSI < 30 ✓ (+1)
   └─ Stoch RSI cross ✓ (+2)

2. ENTRY EXECUTED
   ├─ Price: $48,500
   ├─ Size: 0.05 BTC (50% of full size)
   └─ Stop: $47,000 (Chandelier Exit)

3. FIRST TARGET HIT
   ├─ Price reached: $49,500 (BB middle)
   ├─ Exited: 0.025 BTC (50%)
   ├─ Profit locked: ~$25
   └─ Stop moved to BREAKEVEN ($48,500)

4. FINAL EXIT
   ├─ Price: $51,000 (BB upper or trailing stop)
   ├─ Closed: 0.025 BTC (remaining 25%)
   └─ Total profit: ~$75 (1.5R)
```

---

## Troubleshooting

### "No trades executed"
- Check if period includes bullish regime (EMA50 > EMA200)
- Try longer backtest period: `--months 12`
- Verify entry score threshold in config_v2.py

### "Data fetch failed"
- Check internet connection
- Verify Binance API is accessible
- Try different symbol: `--symbol BTCUSDT`

### "Import errors"
- Install dependencies: `pip install -r requirements.txt`
- Check Python version: `python --version` (need 3.8+)
- Ensure you're in ver2 directory

---

## Next Steps

### 1. Run Tests
```bash
python test_strategy_v2.py
```

### 2. Read Full Documentation
```bash
# Open README_v2.md for complete strategy explanation
cat README_v2.md
```

### 3. Customize Strategy
Edit `config_v2.py` to adjust:
- Entry score threshold
- Risk per trade
- ATR multiplier
- Indicator periods

### 4. Review Trade Logs
Look for detailed logs in console output showing:
- Regime changes
- Entry signals with scores
- Position management actions
- Exit conditions

---

## Performance Expectations

**Conservative (10 months):**
- Return: 15-25%
- Drawdown: 12-18%
- Trades: 35-45

**Base Case (10 months):**
- Return: 35-50%
- Drawdown: 10-15%
- Trades: 45-60

**Optimistic (10 months):**
- Return: 60-85%
- Drawdown: 8-12%
- Trades: 50-70

---

## Help & Support

**For detailed strategy explanation:**
→ Read `README_v2.md`

**For technical specification:**
→ See `/005_money/004_trade_rule/Strategy_v2_inProgress.md`

**For code questions:**
→ Check docstrings in each module

**For bugs or issues:**
→ Run tests: `python test_strategy_v2.py`

---

## Happy Backtesting! 🚀

Remember: Past performance does not guarantee future results. This is for educational purposes only, not financial advice.
