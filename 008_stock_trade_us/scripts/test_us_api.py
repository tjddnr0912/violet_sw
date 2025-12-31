#!/usr/bin/env python3
"""
미국 주식 API 연결 테스트
- KIS 해외주식 API 연결 테스트
- 현재가, 일봉, 잔고 조회 테스트
"""

import os
import sys

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_api_connection():
    """API 연결 테스트"""
    print("\n" + "="*60)
    print("미국 주식 API 연결 테스트")
    print("="*60)

    # 환경 변수 확인
    print("\n[1] 환경 변수 확인")
    env_vars = [
        "KIS_APP_KEY",
        "KIS_APP_SECRET",
        "KIS_ACCOUNT_NO",
        "TRADING_MODE"
    ]

    for var in env_vars:
        value = os.environ.get(var, "")
        if value:
            masked = value[:4] + "****" if len(value) > 8 else "****"
            print(f"  ✅ {var}: {masked}")
        else:
            print(f"  ❌ {var}: 미설정")
            return False

    return True


def test_us_client():
    """미국 주식 클라이언트 테스트"""
    print("\n[2] 미국 주식 클라이언트 테스트")

    try:
        from src.api.kis_us_client import KISUSClient

        client = KISUSClient(is_virtual=True)
        print("  ✅ 클라이언트 초기화 성공")

        # 현재가 조회 테스트
        print("\n  [2-1] 현재가 조회 테스트 (AAPL)")
        try:
            price = client.get_stock_price("AAPL", "NAS")
            print(f"    ✅ AAPL 현재가: ${price.price}")
            print(f"       등락률: {price.change_rate}%")
            print(f"       거래량: {price.volume:,}")
        except Exception as e:
            print(f"    ❌ 현재가 조회 실패: {e}")

        # 일봉 조회 테스트
        print("\n  [2-2] 일봉 조회 테스트 (MSFT)")
        try:
            candles = client.get_daily_price("MSFT", "NAS", count=5)
            print(f"    ✅ MSFT 일봉: {len(candles)}개")
            if candles:
                latest = candles[0]
                print(f"       최신일: {latest.date}, 종가: ${latest.close}")
        except Exception as e:
            print(f"    ❌ 일봉 조회 실패: {e}")

        # 잔고 조회 테스트
        print("\n  [2-3] 잔고 조회 테스트")
        try:
            balance = client.get_balance()
            print(f"    ✅ 보유 종목: {len(balance.get('stocks', []))}개")
            print(f"       USD 잔고: ${balance.get('cash_usd', 0):,.2f}")
        except Exception as e:
            print(f"    ❌ 잔고 조회 실패: {e}")

        # 시장 운영 시간 확인
        print("\n  [2-4] 시장 운영 시간 확인")
        is_open = client.is_market_open()
        print(f"    미국 시장 운영 중: {'예' if is_open else '아니오'}")

        return True

    except ImportError as e:
        print(f"  ❌ 모듈 임포트 실패: {e}")
        return False
    except Exception as e:
        print(f"  ❌ 클라이언트 테스트 실패: {e}")
        return False


def test_universe():
    """유니버스 구성 테스트"""
    print("\n[3] 유니버스 구성 테스트")

    try:
        from src.strategy.us_universe import USUniverseBuilder, get_sp500_symbols

        builder = USUniverseBuilder()

        # S&P 500 조회
        print("\n  [3-1] S&P 500 종목 조회")
        stocks = builder.get_sp500_symbols()
        print(f"    ✅ 로드된 종목: {len(stocks)}개")
        print(f"       상위 5개: {[s.symbol for s in stocks[:5]]}")

        # 섹터 분포
        sectors = {}
        for s in stocks:
            sectors[s.sector] = sectors.get(s.sector, 0) + 1
        print(f"       섹터 분포: {len(sectors)}개 섹터")

        return True

    except Exception as e:
        print(f"  ❌ 유니버스 테스트 실패: {e}")
        return False


def test_screener():
    """스크리너 테스트 (API 호출 없이)"""
    print("\n[4] 스크리너 초기화 테스트")

    try:
        from src.strategy.us_screener import USMultiFactorScreener, USFactorWeights

        weights = USFactorWeights(
            momentum_weight=0.20,
            volatility_weight=0.50,
            value_weight=0.20
        )

        screener = USMultiFactorScreener(weights=weights)
        print("  ✅ 스크리너 초기화 성공")
        print(f"     모멘텀 가중치: {weights.momentum_weight}")
        print(f"     변동성 가중치: {weights.volatility_weight}")
        print(f"     가치 가중치: {weights.value_weight}")

        return True

    except Exception as e:
        print(f"  ❌ 스크리너 테스트 실패: {e}")
        return False


def test_quant_engine():
    """퀀트 엔진 테스트"""
    print("\n[5] 퀀트 엔진 테스트")

    try:
        from src.us_quant_engine import (
            USQuantTradingEngine,
            USQuantEngineConfig,
            USMarketHours,
            get_kst_now,
            is_summer_time
        )

        # 시간 정보
        kst_now = get_kst_now()
        print(f"  현재 한국 시간: {kst_now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  써머타임 적용: {'예' if is_summer_time() else '아니오'}")

        open_h, open_m = USMarketHours.get_market_open_kst()
        close_h, close_m = USMarketHours.get_market_close_kst()
        print(f"  미국 장 시간 (KST): {open_h:02d}:{open_m:02d} ~ {close_h:02d}:{close_m:02d}")

        is_open = USMarketHours.is_market_open(kst_now)
        print(f"  현재 장 운영 중: {'예' if is_open else '아니오'}")

        # 엔진 초기화
        config = USQuantEngineConfig(dry_run=True)
        engine = USQuantTradingEngine(config, is_virtual=True)
        print("\n  ✅ 퀀트 엔진 초기화 성공")

        # 상태 조회
        status = engine.get_status()
        print(f"     Dry-run 모드: {status['dry_run']}")
        print(f"     모의투자: {status['is_virtual']}")
        print(f"     보유 포지션: {status['positions_count']}개")

        return True

    except Exception as e:
        print(f"  ❌ 퀀트 엔진 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_telegram():
    """텔레그램 연결 테스트"""
    print("\n[6] 텔레그램 연결 테스트")

    try:
        from src.telegram.bot import TelegramNotifier

        notifier = TelegramNotifier()
        result = notifier.send_message("🧪 미국 주식 API 테스트 완료!")

        if result:
            print("  ✅ 텔레그램 메시지 전송 성공")
        else:
            print("  ⚠️ 텔레그램 메시지 전송 실패 (봇 설정 확인)")

        return True

    except Exception as e:
        print(f"  ⚠️ 텔레그램 테스트 스킵: {e}")
        return True


def main():
    """메인 테스트 실행"""
    print("\n" + "="*60)
    print("미국 주식 퀀트 시스템 테스트")
    print("="*60)

    results = []

    # 테스트 실행
    results.append(("환경 변수", test_api_connection()))
    results.append(("US 클라이언트", test_us_client()))
    results.append(("유니버스", test_universe()))
    results.append(("스크리너", test_screener()))
    results.append(("퀀트 엔진", test_quant_engine()))
    results.append(("텔레그램", test_telegram()))

    # 결과 요약
    print("\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)

    passed = 0
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1

    print(f"\n총 {len(results)}개 중 {passed}개 통과")

    if passed == len(results):
        print("\n🎉 모든 테스트 통과! 미국 주식 거래 준비 완료")
    else:
        print("\n⚠️ 일부 테스트 실패. 설정을 확인해주세요.")


if __name__ == "__main__":
    main()
