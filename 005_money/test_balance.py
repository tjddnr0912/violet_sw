#!/usr/bin/env python3
"""
잔고 조회 기능 테스트 스크립트
"""

import sys
from config_manager import ConfigManager
from bithumb_api import BithumbAPI
from trading_bot import TradingBot
from logger import TradingLogger

def test_balance_inquiry():
    """잔고 조회 기능 테스트"""
    print("=" * 60)
    print("🧪 잔고 조회 기능 테스트")
    print("=" * 60)

    # 설정 로드
    config_manager = ConfigManager()
    config = config_manager.get_config()

    print(f"\n📋 현재 설정:")
    print(f"   - Dry Run 모드: {config['safety']['dry_run']}")
    print(f"   - 거래 코인: {config['trading'].get('coin', 'BTC')}")

    # API 초기화
    api_key = config['api'].get('connect_key', '')
    secret_key = config['api'].get('secret_key', '')

    if not api_key or api_key in ['YOUR_CONNECT_KEY', 'your_connect_key']:
        print("\n⚠️  API 키가 설정되지 않았습니다.")
        print("   실제 잔고 조회를 테스트하려면 config.json에 API 키를 설정하세요.")
        print("   현재는 모의 거래 모드로 테스트합니다.\n")

    # TradingBot 초기화 (자체적으로 설정과 API를 로드)
    bot = TradingBot()

    print("\n" + "=" * 60)
    print("💰 잔고 조회 테스트")
    print("=" * 60)

    # KRW 잔고 조회
    print("\n1️⃣  KRW 잔고 조회")
    krw_balance = bot.get_current_balance("KRW")
    print(f"   결과: {krw_balance:,.0f} KRW")

    # BTC 잔고 조회
    print("\n2️⃣  BTC 잔고 조회")
    btc_balance = bot.get_current_balance("BTC")
    print(f"   결과: {btc_balance:.8f} BTC")

    # ETH 잔고 조회
    print("\n3️⃣  ETH 잔고 조회")
    eth_balance = bot.get_current_balance("ETH")
    print(f"   결과: {eth_balance:.8f} ETH")

    # XRP 잔고 조회
    print("\n4️⃣  XRP 잔고 조회")
    xrp_balance = bot.get_current_balance("XRP")
    print(f"   결과: {xrp_balance:.8f} XRP")

    print("\n" + "=" * 60)
    print("✅ 테스트 완료")
    print("=" * 60)

    if config['safety']['dry_run']:
        print("\n💡 참고:")
        print("   - 현재 모의 거래 모드(dry_run=True)로 실행 중입니다.")
        print("   - 표시된 잔고는 가상 잔고입니다.")
        print("   - 실제 잔고를 조회하려면 config.json에서 dry_run을 false로 설정하세요.")
    else:
        print("\n💡 참고:")
        print("   - 현재 실제 거래 모드(dry_run=False)로 실행 중입니다.")
        print("   - 표시된 잔고는 빗썸 API를 통해 조회한 실제 잔고입니다.")
        print("   - API 키가 올바르지 않으면 0원으로 표시될 수 있습니다.")

if __name__ == "__main__":
    try:
        test_balance_inquiry()
    except KeyboardInterrupt:
        print("\n\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)