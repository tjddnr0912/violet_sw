#!/usr/bin/env python3
"""
System Verification Script
Performs final checks before manual GUI testing
"""

import sys
import os

# Setup path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def check_imports():
    """Verify all critical imports"""
    print_header("Checking Imports")

    checks = [
        ("pandas", "Data processing"),
        ("numpy", "Numerical operations"),
        ("matplotlib", "Chart plotting"),
        ("tkinter", "GUI framework"),
    ]

    all_ok = True
    for module, description in checks:
        try:
            __import__(module)
            print(f"✓ {module:20s} - {description}")
        except ImportError as e:
            print(f"✗ {module:20s} - MISSING: {e}")
            all_ok = False

    return all_ok

def check_project_modules():
    """Verify project modules"""
    print_header("Checking Project Modules")

    modules = [
        ("data_manager", "DataManager"),
        ("indicator_calculator", "IndicatorCalculator"),
        ("chart_column", "ChartColumn"),
        ("multi_chart_tab", "MultiTimeframeChartTab"),
        ("gui_app", "TradingBotGUI"),
        ("config", "STRATEGY_CONFIG"),
        ("bithumb_api", "get_candlestick"),
    ]

    all_ok = True
    for module_name, class_name in modules:
        try:
            module = __import__(module_name)
            if hasattr(module, class_name):
                print(f"✓ {module_name:25s} - {class_name} found")
            else:
                print(f"⚠ {module_name:25s} - {class_name} NOT FOUND")
                all_ok = False
        except Exception as e:
            print(f"✗ {module_name:25s} - Error: {e}")
            all_ok = False

    return all_ok

def check_config():
    """Verify configuration"""
    print_header("Checking Configuration")

    try:
        from config import STRATEGY_CONFIG

        if 'multi_chart_config' in STRATEGY_CONFIG:
            print("✓ multi_chart_config found in STRATEGY_CONFIG")

            mc_config = STRATEGY_CONFIG['multi_chart_config']
            required_keys = [
                'refresh_interval_seconds',
                'cache_ttl_seconds',
                'api_rate_limit_seconds',
                'default_column1_interval',
                'available_intervals'
            ]

            missing = []
            for key in required_keys:
                if key in mc_config:
                    print(f"  ✓ {key}: {mc_config[key]}")
                else:
                    print(f"  ✗ {key}: MISSING")
                    missing.append(key)

            if missing:
                print(f"\n⚠ Missing config keys: {missing}")
                return False

            return True
        else:
            print("✗ multi_chart_config NOT FOUND in STRATEGY_CONFIG")
            return False
    except Exception as e:
        print(f"✗ Error checking config: {e}")
        return False

def check_files():
    """Verify critical files exist"""
    print_header("Checking Critical Files")

    files = [
        "data_manager.py",
        "indicator_calculator.py",
        "chart_column.py",
        "multi_chart_tab.py",
        "gui_app.py",
        "config.py",
        "bithumb_api.py",
        "strategy.py",
        "TESTING_GUIDE.md",
        "DEBUG_REPORT.md",
    ]

    all_ok = True
    for filename in files:
        filepath = os.path.join(script_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"✓ {filename:30s} ({size:,} bytes)")
        else:
            print(f"✗ {filename:30s} NOT FOUND")
            all_ok = False

    return all_ok

def test_instantiation():
    """Test basic instantiation"""
    print_header("Testing Component Instantiation")

    try:
        print("Testing DataManager...")
        from data_manager import DataManager
        dm = DataManager("BTC")
        print("✓ DataManager('BTC') created successfully")
    except Exception as e:
        print(f"✗ DataManager error: {e}")
        return False

    try:
        print("Testing IndicatorCalculator...")
        from indicator_calculator import IndicatorCalculator
        ic = IndicatorCalculator()
        print("✓ IndicatorCalculator() created successfully")
    except Exception as e:
        print(f"✗ IndicatorCalculator error: {e}")
        return False

    return True

def check_fixes():
    """Verify critical fixes are in place"""
    print_header("Verifying Critical Fixes")

    # Check fix #9: chart_column.py should NOT have pack() call
    try:
        with open(os.path.join(script_dir, 'chart_column.py'), 'r') as f:
            content = f.read()

        # Look for the problematic line
        if 'self.main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)' in content:
            print("✗ Fix #9 NOT APPLIED: chart_column.py still has pack() call")
            return False
        else:
            print("✓ Fix #9 VERIFIED: chart_column.py pack() call removed")
    except Exception as e:
        print(f"⚠ Could not verify Fix #9: {e}")

    # Check fix #10: multi_chart_tab.py should use self.coin_symbol
    try:
        with open(os.path.join(script_dir, 'multi_chart_tab.py'), 'r') as f:
            content = f.read()

        # Look for the fixed line
        if 'f"MultiTimeframeChartTab initialized for {self.coin_symbol}"' in content:
            print("✓ Fix #10 VERIFIED: multi_chart_tab.py uses self.coin_symbol")
        elif 'f"MultiTimeframeChartTab initialized for {coin_symbol}"' in content:
            print("✗ Fix #10 NOT APPLIED: multi_chart_tab.py missing 'self.'")
            return False
        else:
            print("⚠ Fix #10 uncertain: Could not find expected line")
    except Exception as e:
        print(f"⚠ Could not verify Fix #10: {e}")

    return True

def main():
    """Run all verification checks"""
    print("\n" + "=" * 60)
    print("  MULTI-TIMEFRAME CHART SYSTEM VERIFICATION")
    print("=" * 60)

    results = {}

    results['Dependencies'] = check_imports()
    results['Project Modules'] = check_project_modules()
    results['Configuration'] = check_config()
    results['Critical Files'] = check_files()
    results['Instantiation'] = test_instantiation()
    results['Bug Fixes'] = check_fixes()

    # Summary
    print_header("VERIFICATION SUMMARY")

    all_passed = True
    for category, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{category:25s}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL CHECKS PASSED - System Ready for Manual Testing!")
        print("\nNext steps:")
        print("  1. Run: ./launch_gui_test.sh")
        print("  2. Click '📊 멀티 타임프레임' tab")
        print("  3. Follow TESTING_GUIDE.md checklist")
        print("=" * 60)
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Review errors above")
        print("\nSee DEBUG_REPORT.md for troubleshooting")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
