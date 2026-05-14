"""체크리스트 38개 항목 일괄 실행 - PASS/FAIL 한눈에 보기"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

INLINE_CHECKS = [
    (1, "휴장일 20260501/20250501 포함",
     "from src.utils.market_calendar import KNOWN_HOLIDAYS as H; assert '20260501' in H and '20250501' in H"),
    (2, "2026 핵심 휴장일",
     "from src.utils.market_calendar import KNOWN_HOLIDAYS as H; req=['20260101','20260216','20260217','20260218','20260302','20260501','20260505','20260524','20260525','20260817','20260924','20260925','20260926','20261005','20261009','20261225','20261231']; assert all(d in H for d in req)"),
    (3, "주말 휴장",
     "from datetime import datetime; from src.utils.market_calendar import is_trading_day; assert is_trading_day(datetime(2026,5,16))==False and is_trading_day(datetime(2026,5,17))==False"),
    (4, "근로자의 날 휴장",
     "from datetime import datetime; from src.utils.market_calendar import is_trading_day, clear_cache; clear_cache(); assert is_trading_day(datetime(2026,5,1))==False"),
    (5, "평일 거래일",
     "from datetime import datetime; from src.utils.market_calendar import is_trading_day, clear_cache; clear_cache(); assert is_trading_day(datetime(2026,5,14))==True"),
    (6, "KIS API fallback 안전",
     "from src.utils.market_calendar import _update_holidays_from_api; assert _update_holidays_from_api()==False"),
    (9, "converters 기본 동작",
     "from src.utils.converters import safe_float, safe_int, format_currency; assert safe_float(None,7)==7 and safe_int('123.45')==123 and '1,234,567' in format_currency(1234567)"),
    (10, "error_formatter Timeout",
     "from src.utils.error_formatter import format_user_error; assert '잔고' in format_user_error(TimeoutError('x'),'잔고')"),
    (12, "PendingOrder 라운드트립",
     "from src.quant_modules.state_manager import PendingOrder; o=PendingOrder(code='005930',name='S',order_type='BUY',quantity=1,price=0,reason='t'); o2=PendingOrder.from_dict(o.to_dict()); assert o2.code=='005930' and o2.quantity==1"),
    (15, "TakeProfit 3.5R/6R",
     "from src.strategy.quant import TakeProfitManager as T; tp1,tp2=T.calculate_targets(50000,46500); assert abs(tp1-62250)<1 and abs(tp2-71000)<1"),
    (17, "PortfolioManager",
     "from src.strategy.quant import PortfolioManager, Position; from datetime import datetime; p=PortfolioManager(total_capital=10_000_000); pos=Position(code='005930',name='S',entry_price=50000,current_price=50000,quantity=1,entry_date=datetime.now(),stop_loss=46500,take_profit_1=60000,take_profit_2=70000); p.positions[pos.code]=pos; assert '005930' in p.positions and len(p.positions)==1"),
    (19, "notifier 임포트",
     "from src.telegram import get_notifier; n=get_notifier(); assert hasattr(n,'notify_buy') and hasattr(n,'notify_sell') and hasattr(n,'notify_error')"),
    (20, "validators 기본",
     "from src.telegram.validators import InputValidator as V; ok,_=V.validate_stock_code('005930'); assert ok; ok,_,_=V.validate_on_off('on'); assert ok; ok,_,_=V.validate_positive_int('10',1,100); assert ok"),
    (31, "핵심 모듈 임포트",
     "import src.quant_engine, src.quant_modules, src.telegram.bot, src.api.kis_client, src.api.kis_quant, src.strategy.quant, src.utils, src.core.system_controller, src.scheduler.auto_manager"),
    (33, "config JSON 정합",
     "import json; [json.load(open(f)) for f in ['config/system_config.json','config/optimal_weights.json']]"),
    (35, "engine_state schema",
     "import json; d=json.load(open('data/quant/engine_state.json')); assert 'positions' in d and 'last_rebalance_month' in d and 'updated_at' in d"),
    (36, "daily_history schema",
     "import json; d=json.load(open('data/quant/daily_history.json')); assert isinstance(d.get('snapshots'),list) and 'initial_capital' in d"),
    (37, "transaction_journal schema",
     "import json; d=json.load(open('data/quant/transaction_journal.json')); assert isinstance(d.get('transactions'),list)"),
]

PYTEST_CHECKS = [
    (7, "balance_helpers", "tests/test_balance_helpers.py::TestParseBalance"),
    (8, "daily_tracker", "tests/test_daily_tracker.py"),
    (14, "screener factors", "tests/test_quant_strategy.py::TestValueFactorCalculator tests/test_quant_strategy.py::TestMomentumFactorCalculator tests/test_quant_strategy.py::TestQualityFactorCalculator tests/test_quant_strategy.py::TestCompositeScoreCalculator"),
    (18, "daily_tracker tx atomic", "tests/test_daily_tracker.py::TestDailyTracker::test_log_transaction tests/test_daily_tracker.py::TestDailyTracker::test_atomic_write_transactions"),
    (38, "pytest core regression", "tests/test_balance_helpers.py tests/test_daily_tracker.py tests/test_quant_strategy.py::TestValueFactorCalculator tests/test_quant_strategy.py::TestMomentumFactorCalculator tests/test_quant_strategy.py::TestQualityFactorCalculator tests/test_quant_strategy.py::TestCompositeScoreCalculator"),
]

SCRIPT_CHECKS = [
    (11, "retry max_retries", "scripts/check_retry.py"),
    (13, "state recover", "scripts/check_state_recover.py"),
    (16, "stop loss range", "scripts/check_stop_loss_range.py"),
    (21, "rebalance holiday", "scripts/check_rebalance_holiday.py"),
    (22, "first trading day", "scripts/check_rebalance_first_trading_day.py"),
    (23, "same month skip", "scripts/check_rebalance_same_month_skip.py"),
    (24, "urgent rebalance", "scripts/check_urgent_rebalance.py"),
    (25, "order no real call", "scripts/check_order_no_real_call.py"),
    (26, "generate rebalance empty", "scripts/check_generate_rebalance_empty.py"),
    (27, "position monitor stop", "scripts/check_position_monitor_stop.py"),
    (28, "position monitor tp", "scripts/check_position_monitor_tp.py"),
    (29, "state roundtrip", "scripts/check_state_roundtrip.py"),
    (30, "schedule initial holiday", "scripts/check_schedule_initial_holiday.py"),
    (34, "factor weights normalized", "scripts/check_factor_weights_normalized.py"),
]

ENTRY_COMPILE = (32, "main.py compile", "python -m py_compile main.py")


PY = sys.executable

def run(cmd, env=None):
    cmd = cmd.replace("python -m ", f"{PY} -m ").replace("python ", f"{PY} ")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT, env=env)
    return r.returncode, r.stdout, r.stderr


def main():
    results = []
    # inline
    for num, name, code in INLINE_CHECKS:
        rc, out, err = run(f"python -c \"{code}\"")
        results.append((num, name, rc == 0, err if rc else ""))
    # pytest
    for num, name, target in PYTEST_CHECKS:
        rc, out, err = run(f"python -m pytest {target} -q --tb=no")
        results.append((num, name, rc == 0, err if rc else ""))
    # entry compile
    num, name, cmd = ENTRY_COMPILE
    rc, _, err = run(cmd)
    results.append((num, name, rc == 0, err if rc else ""))
    # scripts
    for num, name, script in SCRIPT_CHECKS:
        rc, out, err = run(f"python {script}")
        results.append((num, name, rc == 0, err if rc else ""))

    results.sort()
    passed = sum(1 for _, _, ok, _ in results if ok)
    failed = len(results) - passed
    for num, name, ok, err in results:
        flag = "PASS" if ok else "FAIL"
        line = f"#{num:>2} [{flag}] {name}"
        if not ok:
            line += f"  →  {err.strip().splitlines()[-1][:120] if err else ''}"
        print(line)
    print()
    print(f"=== Total: {passed}/{len(results)} PASS, {failed} FAIL ===")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
