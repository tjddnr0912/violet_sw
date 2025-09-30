import time
import schedule
import signal
import sys
from datetime import datetime
from trading_bot import TradingBot
from logger import TradingLogger
from config_manager import ConfigManager
import config

# 전역 변수
trading_bot = None
logger = None

def signal_handler(signum, frame):
    """
    종료 시그널 처리
    """
    if logger:
        logger.logger.info("\n\n프로그램 종료 신호를 받았습니다.")
        if trading_bot:
            report = trading_bot.generate_daily_report()
            logger.logger.info(f"\n최종 리포트:\n{report}")
    print("\n프로그램을 안전하게 종료합니다.")
    sys.exit(0)

def job():
    """
    주기적으로 실행될 매매 결정 작업
    """
    global trading_bot, logger

    try:
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n========== {current_time} ===========")

        if not trading_bot:
            logger.log_error("거래 봇이 초기화되지 않았습니다.")
            return

        # 거래 사이클 실행
        trading_bot.run_trading_cycle()

    except Exception as e:
        if logger:
            logger.log_error("거래 사이클 실행 중 오류 발생", e)
        else:
            print(f"거래 사이클 오류: {e}")

def daily_report_job():
    """
    일일 리포트 생성 및 카운터 리셋
    """
    global trading_bot, logger

    try:
        if trading_bot and logger:
            report = trading_bot.generate_daily_report()
            logger.logger.info(f"\n일일 리포트:\n{report}")
            trading_bot.reset_daily_counters()

    except Exception as e:
        if logger:
            logger.log_error("일일 리포트 생성 중 오류", e)

def setup_schedule(config_data: dict) -> None:
    """
    스케줄 설정 (기존 스케줄 클리어 후 재설정)
    """
    # 기존 스케줄 클리어
    schedule.clear()

    schedule_config = config_data['schedule']

    # 초 단위 체크가 설정된 경우
    if 'check_interval_seconds' in schedule_config:
        seconds = schedule_config['check_interval_seconds']
        if seconds < 60:
            # 초 단위 스케줄링
            schedule.every(seconds).seconds.do(job)
            print(f"⏰ {seconds}초마다 체크")
        elif seconds < 3600:
            # 분 단위 스케줄링
            minutes = seconds // 60
            schedule.every(minutes).minutes.do(job)
            print(f"⏰ {minutes}분마다 체크")
        else:
            # 시간 단위 스케줄링
            hours = seconds // 3600
            schedule.every(hours).hours.do(job)
            print(f"⏰ {hours}시간마다 체크")
    else:
        # 기존 분 단위 설정
        if schedule_config['check_interval_minutes'] > 0:
            schedule.every(schedule_config['check_interval_minutes']).minutes.do(job)
            print(f"⏰ {schedule_config['check_interval_minutes']}분마다 체크")

    # 일일 체크 스케줄
    if schedule_config.get('daily_check_time'):
        schedule.every().day.at(schedule_config['daily_check_time']).do(job)
        print(f"⏰ 매일 {schedule_config['daily_check_time']}에 체크")

    # 일일 리포트 스케줄
    schedule.every().day.at("23:59").do(daily_report_job)

def main():
    """
    메인 실행 함수
    """
    global trading_bot, logger

    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("🤖 빗썸 자동매매 봇")
    print("="*50)

    try:
        # 설정 관리자 초기화
        config_manager = ConfigManager()

        # 명령행 인수 파싱
        args = config_manager.parse_arguments()

        # 설정 표시 요청 시
        if args.show_config:
            print("\n📋 현재 설정:")
            config_manager.show_current_config()
            return

        # 설정 리셋 요청 시
        if args.reset_config:
            config_manager.reset_config()
            print("✅ 설정이 기본값으로 리셋되었습니다.")
            return

        # 커스텀 설정 파일 로드
        if args.config_file:
            if not config_manager.load_config_from_file(args.config_file):
                return

        # 명령행 인수 적용
        config_manager.apply_arguments(args)

        # 대화형 설정 모드
        if args.interactive:
            config_manager.interactive_config()

        # 설정 저장 요청 시
        if args.save_config:
            config_manager.save_config_to_file(args.save_config)
            return

        # 포트폴리오/계정 정보 표시 요청 시
        if args.show_portfolio or args.show_account or args.export_portfolio:
            # 임시 봇 생성 (설정 적용 전)
            config.TRADING_CONFIG.update(config_manager.get_config()['trading'])
            config.STRATEGY_CONFIG.update(config_manager.get_config()['strategy'])
            config.SCHEDULE_CONFIG.update(config_manager.get_config()['schedule'])
            config.SAFETY_CONFIG.update(config_manager.get_config()['safety'])

            if not config.validate_config():
                print("❌ 설정 검증 실패.")
                return

            temp_bot = TradingBot()

            if not temp_bot.authenticate():
                print("❌ API 인증 실패. API 키를 확인해주세요.")
                return

            if args.show_portfolio:
                print("\n📊 포트폴리오 현황:")
                print(temp_bot.get_portfolio_status_text())
                return

            if args.show_account:
                print("\n🏦 계정 상세 정보:")
                print("⚠️  계정 정보 조회 기능이 보안상의 이유로 비활성화되었습니다.")
                print("   → 거래 내역은 --show-transactions 옵션으로 확인할 수 있습니다.")
                print("   → 또는 GUI 모드에서 '거래 내역' 탭을 이용하세요.")
                return

            if args.export_portfolio:
                print("⚠️  포트폴리오 내보내기 기능이 보안상의 이유로 비활성화되었습니다.")
                print("   → 거래 내역은 --export-transactions 옵션으로 내보낼 수 있습니다.")
                print("   → 또는 GUI 모드에서 '거래 내역' 탭의 내보내기 기능을 이용하세요.")
                return

        # 최종 설정 가져오기
        final_config = config_manager.get_config()

        # 설정 검증 (동적 설정 사용)
        config.TRADING_CONFIG.update(final_config['trading'])
        config.STRATEGY_CONFIG.update(final_config['strategy'])
        config.SCHEDULE_CONFIG.update(final_config['schedule'])
        config.SAFETY_CONFIG.update(final_config['safety'])

        if not config.validate_config():
            print("❌ 설정 검증 실패. 프로그램을 종료합니다.")
            return

        # 로거 초기화
        logger = TradingLogger(final_config['logging']['log_dir'])

        # 거래 봇 초기화 (업데이트된 설정 사용)
        trading_bot = TradingBot()

        # 초기 인증
        if not trading_bot.authenticate():
            logger.log_error("초기 인증 실패. 프로그램을 종료합니다.")
            return

        # 설정 정보 출력
        print("\n📋 실행 설정:")
        print(f"💰 매매 대상: {final_config['trading']['target_ticker']}")
        print(f"💵 거래 금액: {final_config['trading']['trade_amount_krw']:,}원")
        mode_str = "⚠️ 모의 거래" if final_config['safety']['dry_run'] else "🔴 실제 거래"
        if final_config['safety'].get('test_mode', False):
            mode_str += " + 🧪 테스트 모드 (내역 기록 안함)"
        print(f"🤖 모드: {mode_str}")
        print(f"📊 전략: MA({final_config['strategy']['short_ma_window']},{final_config['strategy']['long_ma_window']}), RSI({final_config['strategy']['rsi_period']})")

        # 계정 현황 표시
        print(trading_bot.display_startup_account_info())

        # 로그 파일 위치 정보
        print(f"\n📝 거래 로그 파일:")
        print(f"  ├─ 텍스트 로그: logs/trading_{datetime.now().strftime('%Y%m%d')}.log")
        print(f"  ├─ JSON 거래내역: transaction_history.json")
        print(f"  └─ 📊 마크다운 테이블: {trading_bot.get_markdown_log_path()}")

        # 스케줄 설정
        setup_schedule(final_config)

        logger.logger.info("거래 봇이 성공적으로 시작되었습니다.")
        logger.logger.info(f"설정: {final_config}")

        # 첫 실행
        print("\n🚀 거래 봇을 시작합니다...")
        job()

        print("\n⏸️  중단하려면 Ctrl+C를 누르세요")
        print("="*50)

        # 메인 루프
        while True:
            schedule.run_pending()
            time.sleep(1)

    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        if logger:
            logger.log_error("메인 프로그램 실행 중 오류", e)
        print(f"실행 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()