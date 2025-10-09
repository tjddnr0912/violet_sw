# Ver3 GUI File Logging - Quick Start

## What Changed?

Ver3 GUI now **automatically saves all logs to a file** for debugging and analysis.

## Log File Location

```
logs/ver3_gui_20251009.log
```

Where `20251009` is today's date (YYYYMMDD format).

## How to Use

### 1. Start Ver3 GUI Normally
```bash
cd 005_money
python 001_python_code/ver3/gui_app_v3.py
```

That's it! Logs are automatically written to the file.

### 2. View Live Logs
```bash
# Watch logs in real-time
tail -f logs/ver3_gui_$(date +%Y%m%d).log
```

### 3. Search for Errors
```bash
# Find all errors in today's log
grep ERROR logs/ver3_gui_$(date +%Y%m%d).log
```

### 4. View Last 50 Lines
```bash
# Show recent activity
tail -n 50 logs/ver3_gui_$(date +%Y%m%d).log
```

## Log Levels

| Level | Meaning | Example |
|-------|---------|---------|
| `INFO` | Normal operation | "Bot started successfully" |
| `WARNING` | Non-critical issue | "API keys not set" |
| `ERROR` | Critical problem | "Failed to query balance" |

## Log Format

```
[2025-10-09 14:30:00] [INFO] Bot started successfully
[2025-10-09 14:31:15] [WARNING] API client not initialized
[2025-10-09 14:32:30] [ERROR] Connection timeout
```

- **Full timestamp**: Date and time for historical analysis
- **Log level**: INFO, WARNING, or ERROR
- **Message**: Detailed description

## Daily Rotation

- New log file created each day automatically
- Old logs are preserved (not overwritten)
- Example:
  - `ver3_gui_20251009.log` (today)
  - `ver3_gui_20251008.log` (yesterday)
  - `ver3_gui_20251007.log` (2 days ago)

## Benefits

1. **Debugging**: Review logs after GUI is closed
2. **Historical Analysis**: Track bot behavior over time
3. **Error Tracking**: Find patterns in errors
4. **Audit Trail**: Complete record of user actions
5. **Support**: Share logs for troubleshooting

## Common Use Cases

### Debugging Bot Issues
```bash
# Find when bot stopped
grep "Bot stopped" logs/ver3_gui_*.log

# Check for API errors
grep "API" logs/ver3_gui_$(date +%Y%m%d).log | grep ERROR
```

### Performance Monitoring
```bash
# Count total log entries
wc -l logs/ver3_gui_$(date +%Y%m%d).log

# Find coin updates
grep "Coins updated" logs/ver3_gui_*.log
```

### Sharing Logs for Support
```bash
# Copy today's log for sharing
cp logs/ver3_gui_$(date +%Y%m%d).log ~/Desktop/
```

## No Action Required

File logging is **automatic** and **always on**. You don't need to configure anything.

## Troubleshooting

### Q: Where are my logs?
**A**: Check `005_money/logs/` directory. Log file name includes today's date.

### Q: Can I disable file logging?
**A**: Not recommended. File logging has minimal performance impact and is essential for debugging.

### Q: How much disk space do logs use?
**A**: Typically 1-10 MB per day of active use. Old logs can be manually deleted if needed.

### Q: Are logs automatically deleted?
**A**: No. You can manually delete old logs if needed:
```bash
# Delete logs older than 30 days
find logs/ -name "ver3_gui_*.log" -mtime +30 -delete
```

## Related Documentation

- `GUI_FILE_LOGGING_IMPLEMENTATION.md` - Technical details
- `001_python_code/lib/core/logger.py` - Logging utilities
- `logs/trading_YYYYMMDD.log` - Bot execution logs (separate)

---

**Note**: This feature was added on 2025-10-09 to improve debugging capabilities.
