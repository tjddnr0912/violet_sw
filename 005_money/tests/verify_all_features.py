#!/usr/bin/env python3
"""
전체 기능 통합 검증 스크립트
모든 주요 기능이 정상 작동하는지 확인
"""

import sys
import os

def verify_imports():
    """모든 필수 모듈 import 검증"""
    print("\n" + "=" * 80)
    print("1. 모듈 Import 검증")
    print("=" * 80)

    modules_to_test = [
        ('pandas', 'pandas'),
        ('requests', 'requests'),
        ('numpy', 'numpy'),
        ('matplotlib', 'matplotlib.pyplot'),
        ('mplfinance', 'mplfinance'),
        ('config', 'config'),
        ('bithumb_api', 'bithumb_api'),
        ('strategy', 'strategy'),
        ('logger', 'logger'),
        ('config_manager', 'config_manager'),
        ('gui_trading_bot', 'gui_trading_bot'),
        ('chart_widget', 'chart_widget'),
    ]

    failed = []
    for name, module_path in modules_to_test:
        try:
            __import__(module_path)
            print(f"  ✅ {name}")
        except ImportError as e:
            print(f"  ❌ {name}: {e}")
            failed.append(name)

    return len(failed) == 0


def verify_api_functions():
    """API 함수 검증"""
    print("\n" + "=" * 80)
    print("2. API 함수 검증")
    print("=" * 80)

    try:
        from bithumb_api import BithumbAPI, get_candlestick, get_ticker

        # 공개 API 테스트
        print("  📡 공개 API 테스트...")
        ticker_data = get_ticker('BTC')
        if ticker_data:
            print(f"    ✅ get_ticker() - BTC 현재가: {ticker_data.get('closing_price')}원")
        else:
            print(f"    ❌ get_ticker() 실패")
            return False

        candle_data = get_candlestick('BTC', '24h')
        if candle_data is not None and not candle_data.empty:
            print(f"    ✅ get_candlestick() - 데이터 {len(candle_data)}개 캔들")
        else:
            print(f"    ❌ get_candlestick() 실패")
            return False

        # 비공개 API (환경변수 확인만)
        print("  🔐 비공개 API 설정 확인...")
        connect_key = os.getenv("BITHUMB_CONNECT_KEY")
        secret_key = os.getenv("BITHUMB_SECRET_KEY")

        if connect_key and secret_key and \
           connect_key not in ["YOUR_CONNECT_KEY", "your_connect_key"] and \
           secret_key not in ["YOUR_SECRET_KEY", "your_secret_key"]:
            print(f"    ✅ API 키 설정됨")
        else:
            print(f"    ⚠️  API 키 미설정 (모의 거래 모드)")

        return True

    except Exception as e:
        print(f"  ❌ API 함수 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_strategy_functions():
    """전략 함수 검증"""
    print("\n" + "=" * 80)
    print("3. 전략 함수 검증")
    print("=" * 80)

    try:
        import pandas as pd
        import numpy as np
        from strategy import (
            calculate_moving_average,
            calculate_rsi,
            calculate_bollinger_bands,
            calculate_volume_ratio
        )

        # 테스트 데이터 생성
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        test_data = pd.DataFrame({
            'close': np.random.randn(50).cumsum() + 100,
            'volume': np.random.randint(1000, 10000, 50)
        }, index=dates)

        # MA 계산
        ma = calculate_moving_average(test_data, 10)
        print(f"  ✅ calculate_moving_average() - 최근 MA: {ma.iloc[-1]:.2f}")

        # RSI 계산
        rsi = calculate_rsi(test_data, 14)
        print(f"  ✅ calculate_rsi() - 최근 RSI: {rsi.iloc[-1]:.2f}")

        # 볼린저 밴드 계산
        upper, middle, lower = calculate_bollinger_bands(test_data, 20, 2)
        print(f"  ✅ calculate_bollinger_bands() - Upper: {upper.iloc[-1]:.2f}, Lower: {lower.iloc[-1]:.2f}")

        # 거래량 비율 계산
        vol_ratio = calculate_volume_ratio(test_data, 10)
        print(f"  ✅ calculate_volume_ratio() - 최근 비율: {vol_ratio.iloc[-1]:.2f}")

        return True

    except Exception as e:
        print(f"  ❌ 전략 함수 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_chart_widget():
    """차트 위젯 검증"""
    print("\n" + "=" * 80)
    print("4. 차트 위젯 검증")
    print("=" * 80)

    try:
        from chart_widget import ChartWidget
        import tkinter as tk

        print("  🎨 ChartWidget 클래스 로드...")

        # 테스트용 config
        test_config = {
            'trading': {'target_ticker': 'BTC', 'trade_amount_krw': 10000},
            'strategy': {
                'candlestick_interval': '24h',
                'short_ma_window': 5,
                'long_ma_window': 20,
                'rsi_period': 14,
                'rsi_overbought': 70,
                'rsi_oversold': 30
            }
        }

        # 필수 메서드 확인
        required_methods = [
            'setup_ui',
            'create_chart',
            'load_data',
            'calculate_indicators',
            'calculate_signals',
            'update_chart',
            'refresh_chart'
        ]

        for method in required_methods:
            if hasattr(ChartWidget, method):
                print(f"    ✅ {method}() 메서드 존재")
            else:
                print(f"    ❌ {method}() 메서드 없음")
                return False

        print("  ✅ ChartWidget 검증 완료")
        return True

    except Exception as e:
        print(f"  ❌ 차트 위젯 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_signal_history_widget():
    """신호 히스토리 위젯 검증"""
    print("\n" + "=" * 80)
    print("5. 신호 히스토리 위젯 검증")
    print("=" * 80)

    try:
        from signal_history_widget import SignalHistoryWidget

        print("  📋 SignalHistoryWidget 클래스 로드...")

        # 필수 메서드 확인
        required_methods = [
            'setup_ui',
            'get_available_dates',
            'parse_log_file',
            'signal_to_text',
            'apply_filter',
            'calculate_statistics',
            'refresh_history'
        ]

        for method in required_methods:
            if hasattr(SignalHistoryWidget, method):
                print(f"    ✅ {method}() 메서드 존재")
            else:
                print(f"    ❌ {method}() 메서드 없음")
                return False

        # 로그 파싱 테스트
        widget = object.__new__(SignalHistoryWidget)
        widget.log_dir = 'logs'

        # 최근 로그 파일 찾기
        import os
        from datetime import datetime
        log_files = [f for f in os.listdir('logs') if f.startswith('trading_') and f.endswith('.log')]
        if log_files:
            latest_log = sorted(log_files)[-1]
            date = latest_log.replace('trading_', '').replace('.log', '')
            signals = widget.parse_log_file(date)
            print(f"  ✅ 로그 파싱 성공: {len(signals)}개 신호 발견 (최근 24시간)")
            if signals:
                first_time = signals[0]['timestamp']
                last_time = signals[-1]['timestamp']
                print(f"  ✅ 시간 범위: {first_time} ~ {last_time}")
        else:
            print("  ⚠️  로그 파일 없음 (정상 - 첫 실행 시)")

        print("  ✅ SignalHistoryWidget 검증 완료")
        return True

    except Exception as e:
        print(f"  ❌ 신호 히스토리 위젯 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_gui():
    """GUI 검증 (초기화만)"""
    print("\n" + "=" * 80)
    print("6. GUI 초기화 검증")
    print("=" * 80)

    try:
        import tkinter as tk
        from gui_app import TradingBotGUI

        print("  🖥️  Tkinter 루트 생성...")
        root = tk.Tk()

        print("  🤖 TradingBotGUI 초기화...")
        app = TradingBotGUI(root)

        print("  ✅ GUI 초기화 성공")

        # 차트 위젯 존재 확인
        if hasattr(app, 'chart_widget'):
            print("  ✅ 차트 위젯 통합됨")
        else:
            print("  ❌ 차트 위젯 없음")
            return False

        # 신호 히스토리 위젯 존재 확인
        if hasattr(app, 'signal_history_widget'):
            print("  ✅ 신호 히스토리 위젯 통합됨")
        else:
            print("  ❌ 신호 히스토리 위젯 없음")
            return False

        # 노트북 탭 확인
        if hasattr(app, 'notebook'):
            tab_count = app.notebook.index('end')
            print(f"  ✅ 노트북 탭 수: {tab_count}개")
        else:
            print("  ❌ 노트북 위젯 없음")
            return False

        # GUI 종료
        root.destroy()

        return True

    except Exception as e:
        print(f"  ❌ GUI 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_config():
    """설정 관리 검증"""
    print("\n" + "=" * 80)
    print("7. 설정 관리 검증")
    print("=" * 80)

    try:
        from config_manager import ConfigManager
        import config

        print("  📝 ConfigManager 초기화...")
        cm = ConfigManager()

        current_config = cm.get_config()
        print(f"    ✅ 설정 로드 성공")
        print(f"    - 타겟 코인: {current_config['trading']['target_ticker']}")
        print(f"    - 캔들 간격: {current_config['strategy']['candlestick_interval']}")
        print(f"    - 거래 금액: {current_config['trading']['trade_amount_krw']}원")

        # config.py 검증
        if config.validate_config():
            print(f"  ✅ config.py 검증 통과")
        else:
            print(f"  ⚠️  config.py 검증 경고 (API 키 미설정 가능)")

        return True

    except Exception as e:
        print(f"  ❌ 설정 관리 검증 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 검증 함수"""
    print("\n" + "=" * 100)
    print(" " * 30 + "🚀 빗썸 자동매매 봇 전체 기능 검증")
    print("=" * 100)

    results = []

    # 1. 모듈 Import
    results.append(("모듈 Import", verify_imports()))

    # 2. API 함수
    results.append(("API 함수", verify_api_functions()))

    # 3. 전략 함수
    results.append(("전략 함수", verify_strategy_functions()))

    # 4. 차트 위젯
    results.append(("차트 위젯", verify_chart_widget()))

    # 5. 신호 히스토리 위젯
    results.append(("신호 히스토리 위젯", verify_signal_history_widget()))

    # 6. GUI
    results.append(("GUI 초기화", verify_gui()))

    # 7. 설정 관리
    results.append(("설정 관리", verify_config()))

    # 결과 요약
    print("\n" + "=" * 100)
    print(" " * 40 + "📊 검증 결과 요약")
    print("=" * 100)

    for name, result in results:
        status = "✅ 통과" if result else "❌ 실패"
        print(f"  {name:20s} : {status}")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    print("\n" + "=" * 100)
    print(f" " * 35 + f"총 {passed}/{total}개 검증 통과")
    print("=" * 100)

    if passed == total:
        print("\n✅ 모든 기능이 정상 작동합니다!")
        print("\n📝 사용 방법:")
        print("  - GUI 실행: ./run.sh --gui 또는 python gui_app.py")
        print("  - CLI 실행: ./run.sh 또는 python main.py")
        print("  - 차트 탭: GUI에서 '📊 실시간 차트' 탭 클릭")
        return 0
    else:
        print("\n❌ 일부 기능에 문제가 있습니다.")
        return 1


if __name__ == "__main__":
    sys.exit(main())