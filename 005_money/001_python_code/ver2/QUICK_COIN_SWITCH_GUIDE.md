# Quick Coin Switch Guide

**How to change from BTC to any other cryptocurrency in 30 seconds**

---

## Step 1: Open Config File

```bash
cd 005_money
nano 001_python_code/ver2/config_v2.py
```

Or use any text editor:
- VSCode: `code 001_python_code/ver2/config_v2.py`
- vim: `vim 001_python_code/ver2/config_v2.py`

---

## Step 2: Find TRADING_CONFIG

Press `Ctrl+W` (in nano) or `Ctrl+F` (in VSCode) and search for:
```
TRADING_CONFIG
```

---

## Step 3: Change Symbol

Find this line (around line 258):
```python
'symbol': 'BTC',
```

Change it to your desired coin:

**Available Options (4 major coins):**
```python
'symbol': 'BTC',    # Bitcoin (default)
'symbol': 'ETH',    # Ethereum
'symbol': 'XRP',    # Ripple
'symbol': 'SOL',    # Solana
```

---

## Step 4: Save and Exit

**Nano:**
- Press `Ctrl+X`
- Press `Y` to confirm
- Press `Enter`

**VSCode/Other:**
- Press `Ctrl+S` or `Cmd+S`
- Close the file

---

## Step 5: Verify (Optional)

Run the test to make sure your coin is supported:

```bash
source .venv/bin/activate
python -c "from ver2.config_v2 import validate_symbol; print(validate_symbol('ETH'))"
```

Should output: `(True, '')`

---

## Step 6: Start Trading

Run the bot normally:

```bash
python 001_python_code/main.py --version ver2
```

The bot will now trade your selected cryptocurrency instead of BTC!

---

## Available Coins

**Total:** 4 major cryptocurrencies with high liquidity

**Supported Coins:**
```
BTC  - Bitcoin (Market leader, highest liquidity)
ETH  - Ethereum (Smart contracts, 2nd largest)
XRP  - Ripple (High volume, fast payments)
SOL  - Solana (Modern L1, growing ecosystem)
```

**Why only 4 coins?**
- High liquidity ensures reliable order execution
- Reduced manipulation risk
- Proven track record with real utility
- Sufficient trading volume for technical analysis

**See implementation:** Check `AVAILABLE_COINS` in `config_v2.py` (line 15)

---

## Troubleshooting

### "Symbol 'XXX' is not supported"

**Solution:** Check if your coin is in the `AVAILABLE_COINS` list.

```bash
python -c "from ver2.config_v2 import AVAILABLE_COINS; print('XXX' in AVAILABLE_COINS)"
```

### "Insufficient data for coin"

**Solution:** Some coins may have limited historical data. Try a different coin from the popular list.

### "API Error"

**Solution:** Verify coin symbol is uppercase and spelled correctly.

---

## Quick Examples

### Switch to Ethereum
```bash
# Edit config
sed -i "s/'symbol': 'BTC'/'symbol': 'ETH'/g" 001_python_code/ver2/config_v2.py

# Run bot
python 001_python_code/main.py --version ver2
```

### Switch to Ripple
```bash
# Edit config
sed -i "s/'symbol': 'BTC'/'symbol': 'XRP'/g" 001_python_code/ver2/config_v2.py

# Run bot
python 001_python_code/main.py --version ver2
```

---

## That's It!

You're now trading a different cryptocurrency. The strategy works identically across all coins - the only difference is which asset you're trading.

**Remember:**
- Higher-priced coins (BTC, ETH) may require higher `trade_amount_krw`
- Lower-priced coins (XRP, DOGE) can be traded with smaller amounts
- Adjust `trade_amount_krw` in the same `TRADING_CONFIG` section based on your budget

---

**Need help?** Check `MULTI_COIN_IMPLEMENTATION_SUMMARY.md` for detailed documentation.
