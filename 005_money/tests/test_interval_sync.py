#!/usr/bin/env python3
"""
캔들 간격과 지표 동기화 테스트
"""

import sys
from config import get_config
from strategy import TradingStrategy
from logger import TradingLogger

def test_interval_sync():
    """캔들 간격에 따른 지표 설정 테스트"""
    print("=" * 70)
    print("📊 캔들 간격과 지표 동기화 테스트")
    print("=" * 70)

    # 설정 로드
    config = get_config()
    logger = TradingLogger()
    strategy = TradingStrategy(logger)

    # 테스트할 간격들
    intervals = ['1h', '6h', '12h', '24h']

    for interval in intervals:
        print(f"\n{'='*70}")
        print(f"🕐 캔들 간격: {interval}")
        print(f"{'='*70}")

        # 간격별 지표 설정 가져오기
        indicator_config = strategy._get_indicator_config_for_interval(interval)

        print(f"\n📈 지표 설정:")
        print(f"  - 단기 이동평균 (Short MA): {indicator_config['short_ma_window']} 캔들")
        print(f"  - 장기 이동평균 (Long MA): {indicator_config['long_ma_window']} 캔들")
        print(f"  - RSI 기간: {indicator_config['rsi_period']} 캔들")
        print(f"  - 분석 기간: {indicator_config['analysis_period']} 캔들")

        # 권장 체크 주기
        check_periods = config['schedule'].get('interval_check_periods', {})
        if interval in check_periods:
            recommended_minutes = check_periods[interval]
            if recommended_minutes >= 60:
                hours = recommended_minutes // 60
                period_str = f"{hours}시간"
            else:
                period_str = f"{recommended_minutes}분"

            print(f"\n⏰ 권장 체크 주기: {period_str}")

        # 실제 시간 계산
        interval_minutes = {
            '1h': 60,
            '6h': 360,
            '12h': 720,
            '24h': 1440
        }

        if interval in interval_minutes:
            total_minutes = interval_minutes[interval] * indicator_config['long_ma_window']
            hours = total_minutes // 60
            days = hours // 24

            print(f"\n📅 실제 분석 기간:")
            print(f"  - 장기 MA 기준: {indicator_config['long_ma_window']} × {interval}")
            if days > 0:
                print(f"  - 총 {days}일 {hours % 24}시간")
            else:
                print(f"  - 총 {hours}시간")

        # 시장 데이터 분석 시뮬레이션 (BTC 예시)
        print(f"\n🔍 BTC 시장 분석 테스트:")
        try:
            analysis = strategy.analyze_market_data('BTC', interval)
            if analysis:
                print(f"  ✅ 성공 - {interval} 캔들 데이터 분석 완료")
                print(f"  - 현재 가격: {analysis['current_price']:,.0f} KRW")
                print(f"  - 단기 MA: {analysis['short_ma']:,.0f} KRW")
                print(f"  - 장기 MA: {analysis['long_ma']:,.0f} KRW")
                print(f"  - RSI: {analysis['rsi']:.2f}")
                print(f"  - 사용된 지표: MA({indicator_config['short_ma_window']}, {indicator_config['long_ma_window']}), RSI({indicator_config['rsi_period']})")
            else:
                print(f"  ❌ 실패 - 데이터를 가져올 수 없습니다")
        except Exception as e:
            print(f"  ❌ 오류: {e}")

    print("\n" + "=" * 70)
    print("✅ 테스트 완료")
    print("=" * 70)

    print("\n💡 사용 방법:")
    print("  CLI: python run.py --candle-interval 1h --interval 15m")
    print("  GUI: '캔들 간격' 드롭다운에서 선택")
    print("\n⚠️  주의:")
    print("  - 캔들 간격을 변경하면 지표 설정이 자동으로 조정됩니다")
    print("  - 체크 주기는 캔들 간격보다 짧게 설정하는 것이 좋습니다")
    print("  - 예: 1h 캔들 → 15분마다 체크, 24h 캔들 → 4시간마다 체크")

if __name__ == "__main__":
    try:
        test_interval_sync()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)