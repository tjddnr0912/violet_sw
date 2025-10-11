"""
Simple validation script for dual profit-taking system implementation.

Checks:
1. Config files have the required fields
2. Code files have been updated with profit target mode logic
3. User preferences structure supports new fields
"""

import json
from pathlib import Path


def check_config_v3():
    """Check that config_v3.py has profit target mode."""
    print("\n=== Checking config_v3.py ===")

    config_file = Path(__file__).parent / 'config_v3.py'
    content = config_file.read_text()

    checks = [
        ("profit_target_mode", "EXIT_CONFIG['profit_target_mode']"),
        ("tp1_percentage", "EXIT_CONFIG['tp1_percentage']"),
        ("tp2_percentage", "EXIT_CONFIG['tp2_percentage']"),
    ]

    for field, expected in checks:
        if expected in content:
            print(f"  ✓ Found: {expected}")
        else:
            print(f"  ✗ Missing: {expected}")
            return False

    return True


def check_strategy_v2():
    """Check that strategy_v2.py supports both modes."""
    print("\n=== Checking strategy_v2.py ===")

    strategy_file = Path(__file__).parent.parent / 'ver2' / 'strategy_v2.py'
    content = strategy_file.read_text()

    checks = [
        "profit_target_mode",
        "percentage_based",
        "bb_based",
        "tp1_percentage",
        "tp2_percentage",
        "entry_price: Optional[float]",
    ]

    for check in checks:
        if check in content:
            print(f"  ✓ Found: {check}")
        else:
            print(f"  ✗ Missing: {check}")
            return False

    return True


def check_live_executor_v3():
    """Check that Position class stores profit target mode."""
    print("\n=== Checking live_executor_v3.py ===")

    executor_file = Path(__file__).parent / 'live_executor_v3.py'
    content = executor_file.read_text()

    checks = [
        "profit_target_mode: str = 'bb_based'",
        "tp1_percentage: float",
        "tp2_percentage: float",
        "'profit_target_mode': self.profit_target_mode",
        "profit_target_mode=data.get('profit_target_mode'",
    ]

    for check in checks:
        if check in content:
            print(f"  ✓ Found: {check}")
        else:
            print(f"  ✗ Missing: {check}")
            return False

    return True


def check_settings_panel():
    """Check that settings panel has GUI controls."""
    print("\n=== Checking settings_panel_widget.py ===")

    settings_file = Path(__file__).parent / 'widgets' / 'settings_panel_widget.py'
    content = settings_file.read_text()

    checks = [
        "profit_target_mode",
        "Radiobutton",
        "BB-based",
        "Percentage-based",
        "_on_profit_mode_changed",
        "self.tp1_spinbox",
        "self.tp2_spinbox",
    ]

    for check in checks:
        if check in content:
            print(f"  ✓ Found: {check}")
        else:
            print(f"  ✗ Missing: {check}")
            return False

    return True


def check_preference_manager():
    """Check that preference manager supports profit target mode."""
    print("\n=== Checking preference_manager_v3.py ===")

    pref_file = Path(__file__).parent / 'preference_manager_v3.py'
    content = pref_file.read_text()

    checks = [
        "'profit_target_mode': 'bb_based'",
        "config['EXIT_CONFIG'].get('profit_target_mode'",
        "merged_config['EXIT_CONFIG']['profit_target_mode']",
    ]

    for check in checks:
        if check in content:
            print(f"  ✓ Found: {check}")
        else:
            print(f"  ✗ Missing: {check}")
            return False

    return True


def check_portfolio_manager():
    """Check that portfolio manager passes entry price for target calculation."""
    print("\n=== Checking portfolio_manager_v3.py ===")

    portfolio_file = Path(__file__).parent / 'portfolio_manager_v3.py'
    content = portfolio_file.read_text()

    checks = [
        "position.profit_target_mode",
        "position.tp1_percentage",
        "position.tp2_percentage",
        "_calculate_target_prices(price_data, entry_price)",
    ]

    for check in checks:
        if check in content:
            print(f"  ✓ Found: {check}")
        else:
            print(f"  ✗ Missing: {check}")
            return False

    return True


def check_user_preferences():
    """Check if user_preferences_v3.json can be loaded."""
    print("\n=== Checking user_preferences_v3.json ===")

    pref_file = Path(__file__).parent / 'user_preferences_v3.json'

    if not pref_file.exists():
        print(f"  ⚠ File doesn't exist yet (will be created on first save)")
        return True

    try:
        with open(pref_file, 'r') as f:
            prefs = json.load(f)

        print(f"  ✓ File exists and is valid JSON")

        # Check if it has exit_scoring section
        if 'exit_scoring' in prefs:
            print(f"  ✓ Has exit_scoring section")
            exit_scoring = prefs['exit_scoring']

            # These may or may not exist in old preferences
            if 'profit_target_mode' in exit_scoring:
                print(f"  ✓ Has profit_target_mode: {exit_scoring['profit_target_mode']}")
            else:
                print(f"  ⚠ Missing profit_target_mode (will be added on next save)")

            if 'tp1_target' in exit_scoring:
                print(f"  ✓ Has tp1_target: {exit_scoring['tp1_target']}%")

            if 'tp2_target' in exit_scoring:
                print(f"  ✓ Has tp2_target: {exit_scoring['tp2_target']}%")

        return True

    except json.JSONDecodeError as e:
        print(f"  ✗ JSON decode error: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all validation checks."""
    print("="*70)
    print("DUAL PROFIT-TAKING SYSTEM IMPLEMENTATION VALIDATION")
    print("="*70)

    all_passed = True

    checks = [
        ("Config V3", check_config_v3),
        ("Strategy V2", check_strategy_v2),
        ("Live Executor V3", check_live_executor_v3),
        ("Settings Panel", check_settings_panel),
        ("Preference Manager", check_preference_manager),
        ("Portfolio Manager", check_portfolio_manager),
        ("User Preferences", check_user_preferences),
    ]

    results = []
    for name, check_func in checks:
        try:
            passed = check_func()
            results.append((name, passed))
            all_passed = all_passed and passed
        except Exception as e:
            print(f"\n✗ Error checking {name}: {e}")
            results.append((name, False))
            all_passed = False

    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:10} {name}")

    print("="*70)

    if all_passed:
        print("\n✓ ALL VALIDATION CHECKS PASSED!")
        print("\nImplementation Summary:")
        print("  • Config supports both BB-based and percentage-based modes")
        print("  • Strategy calculates targets based on selected mode")
        print("  • Position locks in mode when opened")
        print("  • Settings panel provides GUI controls")
        print("  • Preferences persist to JSON file")
        print("\nNext Steps:")
        print("  1. Test GUI: Run the Ver3 GUI and check Settings panel")
        print("  2. Test mode switching: Change from BB to Percentage mode")
        print("  3. Test persistence: Restart app and verify settings load")
        print("  4. Test position locking: Open position, change mode, verify old position uses old mode")
    else:
        print("\n✗ SOME VALIDATION CHECKS FAILED")
        print("Review the errors above and fix the issues")

    return all_passed


if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
