#!/usr/bin/env python3
"""Wrapper script to call the actual run.py in 003_Execution_script/"""
import os
import sys
import subprocess

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Call the actual run.py with all arguments
actual_script = os.path.join(script_dir, '003_Execution_script', 'run.py')
sys.exit(subprocess.call([sys.executable, actual_script] + sys.argv[1:]))
