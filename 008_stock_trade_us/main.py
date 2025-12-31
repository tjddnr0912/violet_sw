#!/usr/bin/env python3
"""
주식 자동매매 시스템 - 메인 실행 파일
한국투자증권 API 기반

Usage:
    python main.py                    # 기본 실행 (모의투자, dry-run)
    python main.py --live             # 실제 주문 실행
    python main.py --real             # 실전투자 모드
    python main.py --stocks 005930,000660  # 종목 지정
    python main.py --strategy rsi     # 전략 선택
    python main.py --interval 15      # 분석 주기 (분)
    python main.py --status           # 시스템 상태 확인
    python main.py --test             # API 연결 테스트
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# logs 디렉토리 생성
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)

from src.engine import TradingEngine, EngineConfig
from src.api import KISClient
from src.strategy import create_strategy
from src.telegram import TelegramNotifier, TelegramBot

load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_api_connection() -> bool:
    """API 연결 테스트"""
    print("\n" + "=" * 50)
    print("API 연결 테스트")
    print("=" * 50)

    try:
        client = KISClient(is_virtual=True)

        # 키 검증
        if not client.auth.validate_credentials():
            print("❌ API 키가 설정되지 않았습니다.")
            print("\n.env 파일에 다음 항목을 설정하세요:")
            print("  KIS_APP_KEY=your_app_key")
            print("  KIS_APP_SECRET=your_app_secret")
            print("  KIS_ACCOUNT_NO=12345678-01")
            return False

        print("✓ API 키 확인됨")

        # 토큰 발급 테스트
        print("\n토큰 발급 테스트...")
        token = client.auth.get_access_token()
        print(f"✓ 토큰 발급 성공 (길이: {len(token)})")

        # 시세 조회 테스트
        print("\n시세 조회 테스트 (삼성전자)...")
        price = client.get_stock_price("005930")
        print(f"✓ {price.name}: {price.price:,}원 ({price.change_rate:+.2f}%)")

        print("\n" + "=" * 50)
        print("✅ API 연결 테스트 성공!")
        print("=" * 50)
        return True

    except Exception as e:
        print(f"\n❌ API 테스트 실패: {e}")
        return False


def test_telegram() -> bool:
    """텔레그램 연결 테스트"""
    print("\n" + "=" * 50)
    print("텔레그램 연결 테스트")
    print("=" * 50)

    notifier = TelegramNotifier()

    if not notifier.validate_config():
        print("❌ 텔레그램 설정이 없습니다.")
        print("\n.env 파일에 다음 항목을 설정하세요:")
        print("  TELEGRAM_BOT_TOKEN=your_bot_token")
        print("  TELEGRAM_CHAT_ID=your_chat_id")
        return False

    print("텔레그램 테스트 메시지 전송 중...")

    success = notifier.notify_system("테스트", {
        "상태": "연결 테스트",
        "시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    if success:
        print("✅ 텔레그램 테스트 성공!")
    else:
        print("❌ 텔레그램 전송 실패")

    return success


def show_status(is_virtual: bool = True):
    """시스템 상태 표시"""
    print("\n" + "=" * 50)
    print("시스템 상태")
    print("=" * 50)

    try:
        client = KISClient(is_virtual=is_virtual)
        mode = "모의투자" if is_virtual else "실전투자"

        print(f"\n📊 모드: {mode}")

        # API 상태
        if client.auth.validate_credentials():
            print("✓ API 키: 설정됨")
            try:
                client.auth.get_access_token()
                print("✓ API 연결: 정상")
            except:
                print("✗ API 연결: 실패")
        else:
            print("✗ API 키: 미설정")

        # 텔레그램 상태
        notifier = TelegramNotifier()
        if notifier.validate_config():
            print("✓ 텔레그램: 설정됨")
        else:
            print("✗ 텔레그램: 미설정")

        # 잔고 조회
        print("\n💰 계좌 정보:")
        try:
            balance = client.get_balance()
            print(f"  예수금: {balance['cash']:,}원")
            print(f"  총평가: {balance['total_eval']:,}원")
            print(f"  총손익: {balance['total_profit']:+,}원")

            if balance['stocks']:
                print(f"\n  보유종목: {len(balance['stocks'])}개")
                for stock in balance['stocks'][:5]:
                    emoji = "📈" if stock.profit >= 0 else "📉"
                    print(f"    {emoji} {stock.name}: {stock.qty}주 ({stock.profit_rate:+.2f}%)")
        except Exception as e:
            print(f"  ❌ 조회 실패: {e}")

    except Exception as e:
        print(f"❌ 상태 조회 실패: {e}")


def show_price(stock_codes: list, is_virtual: bool = True):
    """종목 시세 표시"""
    print("\n" + "=" * 50)
    print("종목 시세")
    print("=" * 50)

    try:
        client = KISClient(is_virtual=is_virtual)

        for code in stock_codes:
            try:
                price = client.get_stock_price(code)
                emoji = "🔺" if price.change > 0 else ("🔻" if price.change < 0 else "➖")

                print(f"\n{price.name} ({code})")
                print(f"  현재가: {price.price:,}원")
                print(f"  전일비: {emoji} {price.change:+,}원 ({price.change_rate:+.2f}%)")
                print(f"  거래량: {price.volume:,}주")
            except Exception as e:
                print(f"\n{code}: 조회 실패 - {e}")

    except Exception as e:
        print(f"❌ 시세 조회 실패: {e}")


def analyze_stock(stock_code: str, strategy_type: str = "composite"):
    """종목 분석"""
    print("\n" + "=" * 50)
    print(f"종목 분석: {stock_code}")
    print("=" * 50)

    try:
        import pandas as pd
        client = KISClient(is_virtual=True)
        strategy = create_strategy(strategy_type)

        # 현재가
        price_info = client.get_stock_price(stock_code)
        print(f"\n📊 {price_info.name} ({stock_code})")
        print(f"현재가: {price_info.price:,}원 ({price_info.change_rate:+.2f}%)")

        # 데이터 조회
        history = client.get_stock_history(stock_code, period="D", count=60)

        if not history:
            print("❌ 데이터 조회 실패")
            return

        df = pd.DataFrame(history)
        df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # 분석
        print(f"\n📈 전략: {strategy.config.name}")
        signal = strategy.analyze(df)

        signal_emoji = {
            "STRONG_BUY": "🟢🟢",
            "BUY": "🟢",
            "HOLD": "⚪",
            "SELL": "🔴",
            "STRONG_SELL": "🔴🔴"
        }

        print(f"신호: {signal_emoji.get(signal.signal.name, '')} {signal.signal.name}")
        print(f"강도: {signal.strength:.2f}")
        print(f"사유: {signal.reason}")

        # 지표값
        print("\n📉 주요 지표:")
        for key, value in signal.indicators.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"❌ 분석 실패: {e}")
        import traceback
        traceback.print_exc()


def run_bot():
    """텔레그램 봇 실행"""
    print("\n" + "=" * 50)
    print("텔레그램 봇 시작")
    print("=" * 50)

    try:
        client = KISClient(is_virtual=True)
        bot = TelegramBot(kis_client=client)

        if not bot.validate_config():
            print("❌ 텔레그램 설정이 필요합니다.")
            return

        print("봇이 실행됩니다. 종료하려면 Ctrl+C를 누르세요.")
        bot.run()

    except KeyboardInterrupt:
        print("\n봇 종료")
    except Exception as e:
        print(f"❌ 봇 실행 실패: {e}")


def run_trading(args):
    """자동매매 실행"""
    print("\n" + "=" * 50)
    print("자동매매 시스템 시작")
    print("=" * 50)

    # 설정
    stock_codes = args.stocks.split(",") if args.stocks else ["005930"]

    config = EngineConfig(
        stock_codes=stock_codes,
        capital=args.capital,
        interval_minutes=args.interval,
        dry_run=not args.live,
        strategy_type=args.strategy,
        max_stocks=args.max_stocks
    )

    is_virtual = not args.real

    # 모드 표시
    mode = "실전투자" if args.real else "모의투자"
    live_mode = "실제 주문" if args.live else "DRY RUN (주문 안 함)"

    print(f"\n📊 모드: {mode}")
    print(f"💹 실행: {live_mode}")
    print(f"📈 전략: {args.strategy}")
    print(f"🎯 종목: {', '.join(stock_codes)}")
    print(f"⏱️  주기: {args.interval}분")
    print(f"💰 자본: {args.capital:,}원")

    if args.live and not args.real:
        print("\n⚠️  주의: 모의투자 환경에서 실제 주문이 실행됩니다!")
    elif args.live and args.real:
        print("\n🚨 경고: 실전투자 환경에서 실제 주문이 실행됩니다!")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != "yes":
            print("취소되었습니다.")
            return

    print("\n시작합니다... (Ctrl+C로 종료)")
    print("=" * 50)

    try:
        engine = TradingEngine(config=config, is_virtual=is_virtual)
        engine.start()
    except KeyboardInterrupt:
        print("\n\n종료됩니다...")
    except Exception as e:
        print(f"\n❌ 실행 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="주식 자동매매 시스템 (한국투자증권 API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py --test              API 연결 테스트
  python main.py --status            계좌 상태 확인
  python main.py --price 005930      종목 시세 조회
  python main.py --analyze 005930    종목 분석
  python main.py                     자동매매 시작 (dry-run)
  python main.py --live              실제 주문 실행
  python main.py --bot               텔레그램 봇 실행
        """
    )

    # 실행 모드
    parser.add_argument("--test", action="store_true", help="API 연결 테스트")
    parser.add_argument("--test-telegram", action="store_true", help="텔레그램 연결 테스트")
    parser.add_argument("--status", action="store_true", help="시스템 상태 확인")
    parser.add_argument("--price", type=str, help="종목 시세 조회 (쉼표로 구분)")
    parser.add_argument("--analyze", type=str, help="종목 분석")
    parser.add_argument("--bot", action="store_true", help="텔레그램 봇 실행")

    # 거래 설정
    parser.add_argument("--stocks", type=str, default="005930",
                        help="거래 종목 (쉼표로 구분, 기본: 005930)")
    parser.add_argument("--strategy", type=str, default="composite",
                        choices=["ma_crossover", "rsi", "macd", "composite"],
                        help="전략 선택 (기본: composite)")
    parser.add_argument("--interval", type=int, default=30,
                        help="분석 주기 (분, 기본: 30)")
    parser.add_argument("--capital", type=int, default=1_000_000,
                        help="투자 자본금 (기본: 1,000,000)")
    parser.add_argument("--max-stocks", type=int, default=5,
                        help="최대 보유 종목 수 (기본: 5)")

    # 실행 모드
    parser.add_argument("--live", action="store_true",
                        help="실제 주문 실행 (기본: dry-run)")
    parser.add_argument("--real", action="store_true",
                        help="실전투자 모드 (기본: 모의투자)")

    args = parser.parse_args()

    # 명령어 실행
    if args.test:
        test_api_connection()
    elif args.test_telegram:
        test_telegram()
    elif args.status:
        show_status(is_virtual=not args.real)
    elif args.price:
        codes = args.price.split(",")
        show_price(codes, is_virtual=not args.real)
    elif args.analyze:
        analyze_stock(args.analyze, args.strategy)
    elif args.bot:
        run_bot()
    else:
        run_trading(args)


if __name__ == "__main__":
    main()
