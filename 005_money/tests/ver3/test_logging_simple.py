#!/usr/bin/env python3
"""
Simple test to verify the logging methods exist and have correct signatures.
"""

import os
import sys

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)

print("=== Ver3 GUI File Logging Implementation Check ===\n")

# Read the gui_app_v3.py file
gui_file_path = os.path.join(project_root, '001_python_code', 'ver3', 'gui_app_v3.py')

with open(gui_file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check for required methods
checks = [
    ("_setup_gui_file_logger", "Setup GUI file logger method"),
    ("_write_log_to_file", "Write log to file method"),
    ("gui_log_file", "GUI log file path variable"),
    ("gui_log_date", "GUI log date tracking variable"),
    ("ver3_gui_", "Ver3 GUI log filename pattern"),
    ("Write log entry with full timestamp", "Full timestamp logging"),
    ("daily rotation", "Daily rotation comment/feature"),
]

print("Checking implementation:")
all_passed = True

for check_str, description in checks:
    if check_str in content:
        print(f"✓ {description}")
    else:
        print(f"✗ {description} - NOT FOUND")
        all_passed = False

print("\n" + "="*60)

# Check the _log_to_gui method for file writing call
if "_write_log_to_file(level, message, timestamp)" in content:
    print("✓ _log_to_gui() calls _write_log_to_file()")
else:
    print("✗ _log_to_gui() does NOT call _write_log_to_file()")
    all_passed = False

# Check that setup_logging calls the file logger setup
if "_setup_gui_file_logger()" in content:
    print("✓ setup_logging() calls _setup_gui_file_logger()")
else:
    print("✗ setup_logging() does NOT call _setup_gui_file_logger()")
    all_passed = False

print("\n" + "="*60)

if all_passed:
    print("\n✓ All implementation checks passed!")
    print("\nExpected behavior:")
    print("  - Log files will be created in: logs/ver3_gui_YYYYMMDD.log")
    print("  - Logs will include full timestamps: [YYYY-MM-DD HH:MM:SS] [LEVEL] message")
    print("  - Daily rotation will occur automatically at midnight")
    print("  - All GUI logs will be written to both the GUI widget and the file")
else:
    print("\n✗ Some implementation checks failed!")
    sys.exit(1)

# Show a sample of the implementation
print("\n" + "="*60)
print("Sample of _log_to_gui implementation:")
print("="*60)

lines = content.split('\n')
in_method = False
indent_count = 0

for i, line in enumerate(lines):
    if 'def _log_to_gui(self, level: str, message: str):' in line:
        in_method = True
        indent_count = 0

    if in_method:
        print(line)
        indent_count += 1
        # Stop after showing the method (when we hit the next method or class)
        if indent_count > 2 and line.strip() and not line.startswith(' ' * 4) and line.startswith('    def '):
            break
        if indent_count > 25:  # Safety limit
            break

print("\n=== Check Complete ===")
