# Ver3 GUI File Logging Implementation

## Overview
Ver3 GUI now saves all log messages to a file in addition to displaying them in the GUI text widget. This enables debugging and historical log analysis even after the GUI is closed.

## Implementation Details

### Log File Location
- **Path**: `logs/ver3_gui_YYYYMMDD.log`
- **Example**: `logs/ver3_gui_20251009.log`
- **Encoding**: UTF-8 (supports Korean and special characters)

### Log File Format
```
=== Ver3 GUI Log Started at 2025-10-09 14:30:00 ===
[2025-10-09 14:30:01] [INFO] Bot started successfully
[2025-10-09 14:30:05] [WARNING] API keys not set - balance query unavailable
[2025-10-09 14:30:10] [INFO] Coins updated to: BTC, ETH, XRP
[2025-10-09 14:31:00] [ERROR] Failed to query balance: Connection timeout
```

### Features

1. **Dual Output**: All logs are written to both:
   - GUI text widget (with color coding)
   - Log file (with full timestamps)

2. **Daily Rotation**:
   - New log file created automatically each day
   - Date check performed on each log write
   - Automatic header added to new files

3. **Full Timestamps**:
   - GUI display: `[HH:MM:SS]` (short format)
   - Log file: `[YYYY-MM-DD HH:MM:SS]` (full format)

4. **Error Handling**:
   - File logging failures don't crash the GUI
   - Errors printed to console for debugging
   - GUI continues to function normally

5. **Log Levels**:
   - `INFO`: General information
   - `WARNING`: Non-critical issues
   - `ERROR`: Critical problems

## Modified Code

### Modified Methods

1. **`setup_logging()`** (line 1020-1030)
   - Added call to `_setup_gui_file_logger()`

2. **`_log_to_gui(level, message)`** (line 1038-1056)
   - Added call to `_write_log_to_file()`
   - Now writes to both GUI and file

### New Methods

1. **`_setup_gui_file_logger()`** (line 986-1004)
   - Creates logs directory if needed
   - Initializes log file path with current date
   - Writes header to new log files

2. **`_write_log_to_file(level, message, timestamp)`** (line 1006-1036)
   - Handles daily rotation logic
   - Writes formatted log entries
   - Includes error handling

## Usage

### For Users
No action required. File logging is automatic when Ver3 GUI starts.

### For Developers

#### Reading Logs Programmatically
```python
import os
from datetime import datetime

# Today's log file
today = datetime.now().strftime('%Y%m%d')
log_file = f'logs/ver3_gui_{today}.log'

if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-8') as f:
        logs = f.readlines()
        for line in logs:
            print(line.strip())
```

#### Filtering Logs by Level
```python
import re

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if '[ERROR]' in line:
            print(line.strip())
```

#### Analyzing Log Patterns
```bash
# Count errors in today's log
grep -c "\[ERROR\]" logs/ver3_gui_$(date +%Y%m%d).log

# Show last 20 log entries
tail -n 20 logs/ver3_gui_$(date +%Y%m%d).log

# Find all warnings
grep "\[WARNING\]" logs/ver3_gui_*.log
```

## Testing

Run the simple implementation check:
```bash
cd 005_money
python 001_python_code/ver3/test_logging_simple.py
```

## Troubleshooting

### Problem: Log file not created
**Solution**: Check that:
- `logs/` directory exists (created automatically)
- Write permissions are correct
- No disk space issues

### Problem: Logs missing
**Solution**:
- Check the correct date in filename
- Verify `_log_to_gui()` is being called (not bypassed)
- Check console for file write errors

### Problem: Encoding errors (garbled Korean text)
**Solution**: File is opened with UTF-8 encoding, should work correctly. If viewing in a text editor, ensure editor uses UTF-8.

## File Structure

```
005_money/
├── logs/
│   ├── ver3_gui_20251009.log  # Today's GUI log
│   ├── ver3_gui_20251008.log  # Yesterday's GUI log
│   ├── trading_20251009.log   # Bot execution logs (separate)
│   └── ...
└── 001_python_code/
    └── ver3/
        ├── gui_app_v3.py      # Modified file
        └── ...
```

## Integration with Existing Logs

- **Ver3 GUI logs**: `logs/ver3_gui_YYYYMMDD.log` (GUI events, user actions)
- **Bot execution logs**: `logs/trading_YYYYMMDD.log` (trading decisions, API calls)
- **Transaction history**: `logs/transaction_history.json` (trade records)
- **Positions**: `logs/positions_v3.json` (current positions)

All logs are complementary and serve different purposes.

## Performance Impact

- **Minimal**: File writes are buffered by OS
- **Non-blocking**: No locks or delays
- **Async safe**: Queue-based logging ensures thread safety
- **Memory**: Log files rotate daily, preventing unbounded growth

## Future Enhancements (Optional)

1. **Log file compression**: Compress old logs to save space
2. **Log level filtering**: Allow users to set minimum log level
3. **Log viewer widget**: Built-in log file browser in GUI
4. **Remote logging**: Send logs to remote server for monitoring
5. **Log search**: Search across multiple log files

## Related Files

- `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/gui_app_v3.py` (modified)
- `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/lib/core/logger.py` (reference)
- `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/gui_app_v2.py` (reference)

## Changelog

- **2025-10-09**: Initial implementation of file logging for Ver3 GUI
  - Added `_setup_gui_file_logger()` method
  - Added `_write_log_to_file()` method
  - Modified `_log_to_gui()` to write to file
  - Modified `setup_logging()` to initialize file logger
  - Implemented daily log rotation
  - Full timestamp support in log files
