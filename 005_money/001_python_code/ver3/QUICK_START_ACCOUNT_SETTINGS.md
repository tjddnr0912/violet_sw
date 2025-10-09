# Quick Start: Account Information & Settings

**For Ver3 Portfolio Multi-Coin Strategy GUI**

## What's New

### Account Information Panel
Shows your current account status:
- **KRW Balance** - Available cash
- **Holdings** - Each coin you're trading with:
  - Average price paid
  - Quantity held
  - Current P&L percentage (green = profit, red = loss)
  - Current value in KRW

### Settings Panel
Configure your trading strategy:
- **Portfolio Tab** - Max positions, position size, risk limits
- **Entry Tab** - When to enter trades (scores, thresholds)
- **Exit Tab** - When to exit trades (stop-loss, profit targets)
- **Risk Tab** - Daily limits and safety controls

### Persistent Settings
Your settings are **automatically saved** and restored when you restart the program!

## How to Use

### View Account Information

1. **Start the GUI:**
   ```bash
   cd 005_money
   python 001_python_code/ver3/gui_app_v3.py
   ```

2. **Navigate to Portfolio Overview tab** (first tab, already selected)

3. **Look at the left panel** - "💰 Account Information"
   - Top shows your KRW balance
   - Below shows each coin you're holding (if any)
   - P&L shows profit/loss percentage in color

4. **No data?**
   - Start the bot to begin trading
   - Account info updates every 5 seconds while bot runs

### Change Settings

1. **Look at the right panel** - "⚙️ Settings"

2. **Click tabs to navigate:**
   - **Portfolio** - General portfolio settings
   - **Entry Scoring** - Entry signal settings
   - **Exit Scoring** - Exit signal settings
   - **Risk Management** - Safety limits

3. **Modify any values** (e.g., change Max Positions from 2 to 3)

4. **Click "✅ Apply Settings" button** at the bottom
   - Settings are validated
   - If valid: Saved and applied
   - If invalid: Error message shows what to fix

5. **Want defaults?** Click "↻ Reset to Defaults" button

### Settings Examples

**Example 1: More Conservative (Lower Risk)**
- Max Positions: 1
- Min Entry Score: 3 (higher = more selective)
- Daily Loss Limit: 3%
- Max Daily Trades: 5

**Example 2: More Aggressive (Higher Risk)**
- Max Positions: 3
- Min Entry Score: 2 (lower = less selective)
- Daily Loss Limit: 7%
- Max Daily Trades: 15

**Example 3: Tighter Stop-Loss**
- Chandelier ATR Multiplier: 2.0 (lower = tighter stop)
- Risk per trade: higher, but stopped quicker

**Example 4: Higher Profit Targets**
- TP1 Target: 3% (first exit at +3%)
- TP2 Target: 5% (final exit at +5%)

## Understanding the Display

### Account Info Panel

```
┌──────────────────────────────┐
│ 💰 Account Information       │
├──────────────────────────────┤
│ KRW Balance: 950,000 KRW     │
│ Last update: 14:32:15        │
│                              │
│ 🪙 Holdings:                 │
│                              │
│ ┌──────────────────────┐    │
│ │ BTC         +2.31%   │    │
│ │ Avg: 95,000,000 KRW  │    │
│ │ Qty: 0.0012          │    │
│ │ Value: 116,760 KRW   │    │
│ └──────────────────────┘    │
│                              │
│ ┌──────────────────────┐    │
│ │ ETH         -1.22%   │    │
│ │ Avg: 4,100,000 KRW   │    │
│ │ Qty: 0.0523          │    │
│ │ Value: 211,738 KRW   │    │
│ └──────────────────────┘    │
└──────────────────────────────┘
```

### Settings Panel (Portfolio Tab)

```
┌──────────────────────────────────┐
│ ⚙️ Settings                      │
├──────────────────────────────────┤
│ [Portfolio] [Entry] [Exit] [Risk]│
│                                  │
│ Max Positions: [2] ▼             │
│ (Max simultaneous positions)     │
│                                  │
│ Position Size (KRW): [50000]    │
│ (Amount per trade)               │
│                                  │
│ Max Portfolio Risk %: [6.0] ▼    │
│ (Total portfolio risk limit)     │
│                                  │
│ [↻ Reset to Defaults]            │
│              [✅ Apply Settings]  │
└──────────────────────────────────┘
```

## Where Settings Are Saved

- **File:** `001_python_code/ver3/user_preferences_v3.json`
- **Backups:** `001_python_code/ver3/preference_backups/`
- **Format:** JSON (human-readable, can edit manually if needed)

## When Settings Are Applied

### Automatically Loaded:
- ✅ Every time you start the GUI
- ✅ Settings from last session restored

### Manually Saved:
- ✅ When you click "Apply Settings" button
- ✅ When you change coin selection (coin list auto-saved)

## Safety Notes

1. **Bot must be stopped** to change settings
   - If bot is running, you'll get a warning
   - Stop bot → Change settings → Restart bot

2. **Settings are validated** before applying
   - Invalid values rejected with clear error message
   - Previous values kept if validation fails

3. **Backups created** before each save
   - Last 10 versions kept automatically
   - Can recover if needed

4. **Dry-run mode recommended** for testing
   - Test settings safely without real trades
   - Toggle in control panel (top right)

## Common Questions

**Q: Will my settings persist after closing the program?**
A: Yes! Settings are saved to `user_preferences_v3.json` and automatically loaded on next startup.

**Q: Can I have different settings for different coins?**
A: Not currently. Settings apply to all coins in your portfolio. Future enhancement planned.

**Q: What if I mess up my settings?**
A: Click "Reset to Defaults" button to restore factory settings. Or manually delete `user_preferences_v3.json` file.

**Q: Why is my balance not showing?**
A: Make sure the bot is running. Account info updates every 5 seconds while bot is active.

**Q: Can I edit the JSON file directly?**
A: Yes, but be careful! File is validated on load. Invalid format will revert to defaults.

**Q: Where are the backups stored?**
A: `001_python_code/ver3/preference_backups/` - Files named like `user_preferences_v3_backup_20251008_143215.json`

## Tips

1. **Start with defaults** - Use default settings first to understand behavior
2. **Small changes** - Adjust one parameter at a time to see effects
3. **Test in dry-run** - Always test new settings in dry-run mode first
4. **Monitor results** - Check Portfolio Overview and Transaction History tabs
5. **Document changes** - Keep notes of what settings work best for you

## Troubleshooting

**Problem:** "Settings applied" but nothing changed
**Solution:** Stop and restart the bot for settings to take effect

**Problem:** Can't click Apply Settings button
**Solution:** Check validation errors. Red text shows what's invalid.

**Problem:** Preferences file not found
**Solution:** Normal on first run. File created when you first apply settings.

**Problem:** Account info shows 0 KRW
**Solution:**
- In dry-run mode: Start bot to simulate trades
- In live mode: Check API connection

**Problem:** Holdings not showing
**Solution:** No positions open yet. Holdings appear when you enter trades.

## Need Help?

- **View logs:** Check Logs tab for error messages
- **Test components:** Run `python 001_python_code/ver3/test_account_settings_gui.py`
- **Documentation:** See `ACCOUNT_SETTINGS_IMPLEMENTATION.md` for technical details

---

**Happy Trading!** 🚀📈💰
