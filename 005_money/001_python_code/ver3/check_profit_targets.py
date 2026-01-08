#!/usr/bin/env python3
"""
Check profit targets for current positions.

This script shows:
- Current position details
- First target price (BB middle - 50% exit)
- Second target price (BB upper - 100% exit)
- Stop-loss price
- Distance to each target
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
base_path = Path(__file__).parent.parent
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

from lib.api.bithumb_api import get_candlestick, get_ticker
from ver3.strategy_v3 import StrategyV3
from ver3.config_v3 import get_version_config


def check_profit_targets():
    """Check profit targets for all current positions."""
    print("=" * 80)
    print("익절 목표가 확인")
    print("=" * 80)

    # Load current positions
    positions_file = Path('logs/positions_v3.json')
    if not positions_file.exists():
        print("\n❌ No positions file found")
        return

    with open(positions_file, 'r') as f:
        positions = json.load(f)

    if not positions:
        print("\n📭 No active positions")
        return

    # Initialize strategy
    config = get_version_config()
    strategy = StrategyV3(config, None)

    print(f"\n현재 보유 포지션: {len(positions)}개\n")

    for ticker, pos in positions.items():
        print("=" * 80)
        print(f"[{ticker}]")
        print("=" * 80)

        # Get current price
        ticker_data = get_ticker(ticker)
        if not ticker_data:
            print(f"❌ Failed to get ticker data for {ticker}\n")
            continue

        current_price = float(ticker_data.get('closing_price', 0))
        entry_price = pos['entry_price']
        stop_loss = pos['stop_loss']

        # Get analysis for target prices
        analysis = strategy.analyze_market(ticker, interval='4h')
        target_prices = analysis.get('target_prices', {})

        if not target_prices:
            print(f"❌ Failed to calculate target prices for {ticker}\n")
            continue

        first_target = target_prices.get('first_target', 0)
        second_target = target_prices.get('second_target', 0)

        # Calculate percentages
        current_pnl_pct = ((current_price - entry_price) / entry_price) * 100
        first_target_pct = ((first_target - entry_price) / entry_price) * 100
        second_target_pct = ((second_target - entry_price) / entry_price) * 100
        stop_loss_pct = ((stop_loss - entry_price) / entry_price) * 100

        # Calculate distance to targets
        to_first_target = ((first_target - current_price) / current_price) * 100
        to_second_target = ((second_target - current_price) / current_price) * 100
        to_stop_loss = ((current_price - stop_loss) / current_price) * 100

        print(f"\n📊 Position Information:")
        print(f"  진입가:       {entry_price:,.0f} KRW")
        print(f"  현재가:       {current_price:,.0f} KRW")
        print(f"  현재 수익률:  {current_pnl_pct:+.2f}%")
        print(f"  보유량:       {pos['size']:.8f} {ticker}")

        print(f"\n🎯 Profit Targets:")
        print(f"  1차 익절 (BB Middle - 50% 매도):")
        print(f"    목표가:     {first_target:,.0f} KRW ({first_target_pct:+.2f}% from entry)")
        print(f"    거리:       {to_first_target:+.2f}%")
        if current_price >= first_target:
            print(f"    ✅ 도달! 50% 익절 실행 대기")
        else:
            print(f"    ⏳ 미도달 ({first_target - current_price:,.0f} KRW 상승 필요)")

        print(f"\n  2차 익절 (BB Upper - 100% 매도):")
        print(f"    목표가:     {second_target:,.0f} KRW ({second_target_pct:+.2f}% from entry)")
        print(f"    거리:       {to_second_target:+.2f}%")
        if current_price >= second_target:
            print(f"    ✅ 도달! 전체 청산 실행 대기")
        else:
            print(f"    ⏳ 미도달 ({second_target - current_price:,.0f} KRW 상승 필요)")

        print(f"\n⛔ Stop-Loss:")
        print(f"  손절가:       {stop_loss:,.0f} KRW ({stop_loss_pct:+.2f}% from entry)")
        print(f"  거리:         -{to_stop_loss:.2f}%")
        if current_price <= stop_loss:
            print(f"  🚨 손절 발동!")
        else:
            print(f"  ✅ 안전 ({current_price - stop_loss:,.0f} KRW 여유)")

        # Status flags
        first_target_hit = pos.get('first_target_hit', False)
        second_target_hit = pos.get('second_target_hit', False)

        print(f"\n📌 Status Flags:")
        print(f"  1차 익절 완료: {'✅ Yes' if first_target_hit else '❌ No'}")
        print(f"  2차 익절 완료: {'✅ Yes' if second_target_hit else '❌ No'}")

        print()

    print("=" * 80)
    print("익절 로직 설명")
    print("=" * 80)
    print("""
1차 익절 (First Target - BB Middle):
  - 조건: 현재가가 볼린저 밴드 중간선에 도달
  - 실행: 포지션의 50% 매도
  - 효과: 안정적인 수익 확보
  - 추가: 손절가가 본전(진입가)으로 이동 → 위험 제거

2차 익절 (Second Target - BB Upper):
  - 조건: 현재가가 볼린저 밴드 상단선에 도달 (1차 익절 후)
  - 실행: 남은 포지션 100% 매도 (전체 청산)
  - 효과: 추가 수익 극대화

익절 시나리오 예시:
  진입: 100,000원 (100% 포지션)
  → 1차 익절: 105,000원 (50% 매도, 50% 보유, 손절가 100,000원으로 이동)
  → 2차 익절: 110,000원 (남은 50% 매도, 포지션 청산)
  → 총 수익: (105,000 × 0.5 + 110,000 × 0.5) / 100,000 - 1 = +7.5%

다음 체크 사이클(15분마다)에 자동으로 익절 실행됩니다.
""")
    print("=" * 80)


if __name__ == "__main__":
    check_profit_targets()
