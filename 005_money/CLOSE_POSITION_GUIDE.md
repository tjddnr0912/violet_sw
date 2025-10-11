# 📘 Manual Position Closer Guide

Quick reference guide for manually closing positions in Ver3 Trading Bot.

## 🚀 Quick Start

```bash
# Show help (always available)
./close_position.sh -help

# Interactive mode (easiest)
./close_position.sh

# Close specific coin
./close_position.sh XRP

# Close all positions
./close_position.sh -all
```

---

## 📖 Usage Examples

### Example 1: Interactive Mode (Recommended for Beginners)

```bash
$ ./close_position.sh
```

**What happens**:
1. Shows all current positions with P&L
2. Displays interactive menu:
   - Option 1: Close specific coin
   - Option 2: Close all positions
   - Option 3: Exit
3. You choose and confirm

**Output**:
```
================================================================================
CURRENT POSITIONS
================================================================================

XRP
  Entry Price:         3,707 KRW
  Current Price:       3,750 KRW
  Size:         13.48794907 XRP
  Position:              50%
  Entry Count:             2 times
  P&L:              +1.16%

ETH
  Entry Price:         5,896,000 KRW
  Current Price:       5,850,000 KRW
  Size:         0.00848033 ETH
  Position:             100%
  Entry Count:             1 times
  P&L:              -0.78%

================================================================================

Select action:
  1. Close specific coin
  2. Close all positions
  3. Exit

Enter choice (1/2/3): 1
Enter coin to close (e.g., SOL): XRP

⚠️  About to close position:
   Coin: XRP
   Size: 13.48794907
   Entry: 3,707 KRW
   Current: 3,750 KRW
   P&L: +1.16%
   Mode: DRY-RUN

Confirm close XRP? (yes/no): yes
✅ Successfully closed XRP position
```

---

### Example 2: Close Specific Coin

```bash
$ ./close_position.sh SOL
```

**What happens**:
1. Directly targets SOL position
2. Shows P&L
3. Asks for confirmation
4. Closes and updates files

**Output**:
```
Closing SOL position...

⚠️  About to close position:
   Coin: SOL
   Size: 0.16903313
   Entry: 295,800 KRW
   Current: 290,500 KRW
   P&L: -1.79%
   Mode: DRY-RUN

Confirm close SOL? (yes/no): yes
✅ Successfully closed SOL position
```

---

### Example 3: Close All Positions

```bash
$ ./close_position.sh -all
```

**What happens**:
1. Shows all positions
2. Confirms closing ALL
3. Closes one by one
4. Shows success count

**Output**:
```
⚠️  About to close ALL 3 positions:
   - SOL
   - ETH
   - XRP
   Mode: DRY-RUN

Confirm close all positions? (yes/no): yes

Closing SOL...
✅ Successfully closed SOL position

Closing ETH...
✅ Successfully closed ETH position

Closing XRP...
✅ Successfully closed XRP position

✅ Closed 3/3 positions
```

---

## 🔄 Workflow: Changing Coins Safely

**Scenario**: You want to change from [ETH, XRP, SOL] to [BTC, ETH]

### Step-by-Step Guide

#### **Step 1: Check Current Positions**
```bash
./close_position.sh
```
→ Shows: ETH (50K), XRP (50K), SOL (50K)

#### **Step 2: Close All Positions**
```bash
./close_position.sh -all
```
→ Type "yes" to confirm

#### **Step 3: Verify Positions = 0**
```bash
cat logs/positions_v3.json
```
→ Should show: `{}`

#### **Step 4: Change Coins in GUI**
1. Open Ver3 GUI
2. Go to Settings → Portfolio
3. Uncheck XRP and SOL
4. Check BTC
5. Click "Apply Settings"

#### **Step 5: Restart Bot**
1. Stop bot (if running)
2. Start bot
3. Bot now monitors [BTC, ETH] only

---

## ⚠️ Important Notes

### **DRY-RUN vs LIVE Mode**

- **Default**: DRY-RUN (simulated trades, no real money)
- **Change to LIVE**: Edit `config_v3.py`
  ```python
  EXECUTION_CONFIG = {
      'dry_run': False,  # Set to False for real trading
      ...
  }
  ```

### **What Gets Updated**

When you close a position:
1. ✅ `positions_v3.json` - Position removed
2. ✅ Trading log - Manual close recorded
3. ✅ P&L statistics - Updated
4. ✅ Portfolio count - Decremented

### **What Doesn't Get Updated**

- ❌ Portfolio Overview GUI (update on next cycle)
- ❌ Bithumb balance (if DRY-RUN mode)

---

## 🆘 Troubleshooting

### **Problem: "No position found for XRP"**

**Cause**: XRP was already closed (externally or by bot)

**Solution**:
```bash
# Check positions file
cat logs/positions_v3.json

# If XRP is still there, remove manually:
vi logs/positions_v3.json
# Delete the XRP entry
```

---

### **Problem: "Virtual environment not found"**

**Cause**: `.venv` folder missing

**Solution**:
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

### **Problem: Script not executable**

**Cause**: Missing execute permission

**Solution**:
```bash
chmod +x close_position.sh
```

---

## 📂 Related Files

- **Script**: `/005_money/close_position.sh`
- **Python backend**: `/001_python_code/ver3/manual_close_position.py`
- **Positions file**: `/logs/positions_v3.json`
- **Trading log**: `/logs/trading_YYYYMMDD.log`

---

## 🎯 Quick Reference

| Command | Description |
|---------|-------------|
| `./close_position.sh -help` | Show help message |
| `./close_position.sh` | Interactive mode (menu) |
| `./close_position.sh XRP` | Close XRP position only |
| `./close_position.sh -all` | Close ALL positions |
| `cat logs/positions_v3.json` | View current positions |

---

## 💡 Tips

1. **Always check P&L first**: Run interactive mode to see current status
2. **Use -all for coin changes**: Safest way to switch coins
3. **Verify empty positions**: Check `positions_v3.json` before coin change
4. **Keep logs**: Manual closes are logged for auditing

---

## 📞 Need Help?

If you forget how to use:
```bash
./close_position.sh -help
```

This guide is always available at:
`/005_money/CLOSE_POSITION_GUIDE.md`

---

**Happy Trading! 🚀**
