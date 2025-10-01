#!/usr/bin/env python3
"""
Elite GUI 기능 테스트 스크립트
모든 새로운 기능이 제대로 작동하는지 확인
"""

import tkinter as tk
from gui_app import TradingBotGUI
from strategy import TradingStrategy, calculate_exit_levels

def test_strategy_signals():
    """전략 신호 생성 테스트"""
    print("=" * 60)
    print("1. 전략 신호 생성 테스트")
    print("=" * 60)

    try:
        strategy = TradingStrategy()

        # BTC 시장 데이터 분석
        print("\n[BTC 분석 중...]")
        analysis = strategy.analyze_market_data('BTC', interval='1h')

        if analysis:
            print(f"✅ 분석 성공!")
            print(f"  - 현재가: {analysis['current_price']:,.0f}원")
            print(f"  - RSI: {analysis['rsi']:.1f}")
            print(f"  - MACD: {analysis['macd_line']:.2f}")
            print(f"  - ATR: {analysis['atr_percent']:.2f}%")
            print(f"  - ADX: {analysis['adx']:.1f}")
            print(f"  - Stochastic K: {analysis['stoch_k']:.1f}, D: {analysis['stoch_d']:.1f}")

            # 가중치 신호 생성
            print("\n[가중치 신호 생성 중...]")
            signals = strategy.generate_weighted_signals(analysis)

            print(f"✅ 신호 생성 성공!")
            print(f"  - MA 신호: {signals['ma_signal']:+.2f}")
            print(f"  - RSI 신호: {signals['rsi_signal']:+.2f}")
            print(f"  - MACD 신호: {signals['macd_signal']:+.2f}")
            print(f"  - BB 신호: {signals['bb_signal']:+.2f}")
            print(f"  - Volume 신호: {signals['volume_signal']:+.2f}")
            print(f"  - Stochastic 신호: {signals['stoch_signal']:+.2f}")
            print(f"\n  - 종합 신호: {signals['overall_signal']:+.2f}")
            print(f"  - 신뢰도: {signals['confidence']:.2f}")
            print(f"  - 최종 액션: {signals['final_action']}")
            print(f"  - 시장 국면: {signals['regime']}")
            print(f"  - 변동성: {signals['volatility_level']}")
            print(f"  - 이유: {signals['reason']}")

            # ATR 기반 리스크 관리
            print("\n[ATR 기반 리스크 레벨 계산 중...]")
            exit_levels = calculate_exit_levels(
                entry_price=analysis['current_price'],
                atr=analysis['atr'],
                direction='LONG',
                volatility_level=signals['volatility_level']
            )

            print(f"✅ 리스크 레벨 계산 성공!")
            print(f"  - 진입가: {analysis['current_price']:,.0f}원")
            print(f"  - 손절가: {exit_levels['stop_loss']:,.0f}원 ({((exit_levels['stop_loss'] - analysis['current_price']) / analysis['current_price'] * 100):+.2f}%)")
            print(f"  - 익절1: {exit_levels['take_profit_1']:,.0f}원 ({((exit_levels['take_profit_1'] - analysis['current_price']) / analysis['current_price'] * 100):+.2f}%)")
            print(f"  - 익절2: {exit_levels['take_profit_2']:,.0f}원 ({((exit_levels['take_profit_2'] - analysis['current_price']) / analysis['current_price'] * 100):+.2f}%)")
            print(f"  - R:R 비율1: 1:{exit_levels['rr_ratio_1']:.2f}")
            print(f"  - R:R 비율2: 1:{exit_levels['rr_ratio_2']:.2f}")

            return True
        else:
            print("❌ 분석 실패: 데이터 없음")
            return False

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy_presets():
    """전략 프리셋 테스트"""
    print("\n" + "=" * 60)
    print("2. 전략 프리셋 테스트")
    print("=" * 60)

    presets = {
        'Balanced Elite': {'macd': 0.35, 'ma': 0.25, 'rsi': 0.20, 'bb': 0.10, 'volume': 0.10},
        'MACD + RSI Filter': {'macd': 0.40, 'rsi': 0.30, 'ma': 0.20, 'bb': 0.10, 'volume': 0.00},
        'Trend Following': {'macd': 0.40, 'ma': 0.30, 'rsi': 0.15, 'bb': 0.05, 'volume': 0.10},
        'Mean Reversion': {'rsi': 0.35, 'bb': 0.25, 'macd': 0.15, 'ma': 0.15, 'volume': 0.10},
    }

    try:
        strategy = TradingStrategy()
        analysis = strategy.analyze_market_data('BTC', interval='1h')

        if not analysis:
            print("❌ 분석 데이터 없음")
            return False

        for preset_name, weights in presets.items():
            print(f"\n[{preset_name}]")
            signals = strategy.generate_weighted_signals(analysis, weights_override=weights)

            print(f"  종합 신호: {signals['overall_signal']:+.2f}")
            print(f"  신뢰도: {signals['confidence']:.2f}")
            print(f"  액션: {signals['final_action']}")

        print("\n✅ 모든 프리셋 테스트 완료!")
        return True

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return False

def test_gui_components():
    """GUI 컴포넌트 로드 테스트"""
    print("\n" + "=" * 60)
    print("3. GUI 컴포넌트 로드 테스트")
    print("=" * 60)

    try:
        print("\n[GUI 윈도우 생성 중...]")
        root = tk.Tk()
        app = TradingBotGUI(root)

        # 필수 컴포넌트 확인
        required_components = [
            'strategy_preset_var',
            'indicator_vars',
            'indicator_leds',
            'indicator_value_labels',
            'regime_var',
            'volatility_var',
            'trend_strength_var',
            'recommendation_var',
            'overall_signal_var',
            'signal_strength_bar',
            'confidence_bar',
            'entry_price_var',
            'stop_loss_price_var',
            'tp1_price_var',
            'tp2_price_var',
            'rr_ratio_var'
        ]

        print("\n[필수 컴포넌트 확인 중...]")
        all_ok = True
        for comp in required_components:
            if hasattr(app, comp):
                print(f"  ✅ {comp}")
            else:
                print(f"  ❌ {comp} - 없음!")
                all_ok = False

        # 지표 개수 확인
        print(f"\n[지표 개수 확인]")
        print(f"  - 지표 변수: {len(app.indicator_vars)}개")
        print(f"  - LED: {len(app.indicator_leds)}개")
        print(f"  - 값 레이블: {len(app.indicator_value_labels)}개")

        expected_indicators = ['ma', 'rsi', 'bb', 'volume', 'macd', 'atr', 'stochastic', 'adx']
        for ind in expected_indicators:
            if ind in app.indicator_vars:
                print(f"  ✅ {ind}")
            else:
                print(f"  ❌ {ind} - 없음!")
                all_ok = False

        # 기본 interval 확인
        print(f"\n[기본 설정 확인]")
        default_interval = app.candle_interval_var.get()
        print(f"  - 캔들 간격: {default_interval}")
        if default_interval == '1h':
            print("  ✅ 기본 간격 1h 설정됨!")
        else:
            print(f"  ⚠️ 기본 간격이 {default_interval}입니다 (1h 권장)")

        # 전략 프리셋 확인
        preset = app.strategy_preset_var.get()
        print(f"  - 전략 프리셋: {preset}")
        if preset == 'Balanced Elite':
            print("  ✅ 기본 프리셋 Balanced Elite!")

        root.destroy()

        if all_ok:
            print("\n✅ GUI 컴포넌트 모두 정상!")
            return True
        else:
            print("\n❌ 일부 컴포넌트 누락!")
            return False

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """메인 테스트 실행"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "Elite Trading Bot GUI Test" + " " * 22 + "║")
    print("╚" + "=" * 58 + "╝")

    results = []

    # 테스트 실행
    results.append(("전략 신호 생성", test_strategy_signals()))
    results.append(("전략 프리셋", test_strategy_presets()))
    results.append(("GUI 컴포넌트", test_gui_components()))

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, result in results:
        if result:
            print(f"✅ {name}: PASS")
            passed += 1
        else:
            print(f"❌ {name}: FAIL")
            failed += 1

    print(f"\n총 {passed + failed}개 테스트 중 {passed}개 통과, {failed}개 실패")

    if failed == 0:
        print("\n🎉 모든 테스트 통과! GUI를 실행할 준비가 되었습니다.")
        print("\n실행 방법:")
        print("  python gui_app.py")
        print("  또는")
        print("  ./run.sh --gui")
    else:
        print("\n⚠️ 일부 테스트 실패. 로그를 확인하세요.")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
