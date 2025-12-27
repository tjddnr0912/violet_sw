#!/usr/bin/env python3
"""
퀀트 시스템 통합 데몬
- 자동매매 엔진
- 전략 자동 관리 (모니터링, 최적화)
- 텔레그램 알림
"""

import sys
import os

# 프로젝트 루트 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
os.chdir(project_root)

# 프로젝트 .env 파일 로드
from dotenv import load_dotenv
from pathlib import Path
env_path = Path(project_root) / ".env"
load_dotenv(env_path, override=True)

import logging
import signal
import threading
from datetime import datetime

# 로그 디렉토리 생성
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/daemon_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class QuantDaemon:
    """퀀트 시스템 통합 데몬"""

    def __init__(self, dry_run: bool = True, is_virtual: bool = True):
        self.dry_run = dry_run
        self.is_virtual = is_virtual
        self.running = False
        self.threads = []

    def start_trading_engine(self):
        """자동매매 엔진 시작"""
        from src.quant_engine import QuantTradingEngine, QuantEngineConfig
        from src.scheduler import WeightConfig

        # 최적 가중치 로드
        weights = WeightConfig.load()

        config = QuantEngineConfig(
            universe_size=200,
            target_stock_count=weights.get('target_count', 15),
            dry_run=self.dry_run
        )

        engine = QuantTradingEngine(config=config, is_virtual=self.is_virtual)

        def run_engine():
            try:
                engine.start()
            except Exception as e:
                logger.error(f"트레이딩 엔진 오류: {e}")

        thread = threading.Thread(target=run_engine, name="TradingEngine", daemon=True)
        thread.start()
        self.threads.append(thread)
        logger.info("자동매매 엔진 시작됨")

    def start_auto_manager(self):
        """자동 관리 스케줄러 시작"""
        from src.scheduler import AutoStrategyManager

        manager = AutoStrategyManager()

        def run_manager():
            try:
                manager.start()
            except Exception as e:
                logger.error(f"자동 관리 오류: {e}")

        thread = threading.Thread(target=run_manager, name="AutoManager", daemon=True)
        thread.start()
        self.threads.append(thread)
        logger.info("자동 관리 스케줄러 시작됨")

    def start_telegram_bot(self):
        """텔레그램 봇 시작"""
        from src.telegram.bot import TelegramBotHandler

        bot = TelegramBotHandler()

        def run_bot():
            try:
                bot.start()
            except Exception as e:
                logger.error(f"텔레그램 봇 오류: {e}")

        thread = threading.Thread(target=run_bot, name="TelegramBot", daemon=True)
        thread.start()
        self.threads.append(thread)
        logger.info("텔레그램 봇 시작됨")

    def send_startup_notification(self):
        """시작 알림 전송"""
        from src.telegram import get_notifier

        notifier = get_notifier()

        mode = "🧪 모의투자" if self.is_virtual else "💰 실전투자"
        dry_run = "✅ Dry-Run" if self.dry_run else "🔴 실제 주문"

        message = f"""
🚀 <b>퀀트 시스템 시작</b>
━━━━━━━━━━━━━━━━━━━━

{mode} | {dry_run}

<b>활성화된 서비스:</b>
• 자동매매 엔진
• 전략 자동 관리
• 텔레그램 봇

<b>자동 관리 일정:</b>
• 월간 모니터링: 매월 1일 09:00
• 반기 최적화: 1월/7월

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        notifier.send_message(message.strip())

    def start(self):
        """데몬 시작"""
        self.running = True

        print("\n" + "=" * 60)
        print("     퀀트 시스템 통합 데몬 시작")
        print("=" * 60)
        print(f"\n모드: {'모의투자' if self.is_virtual else '실전투자'}")
        print(f"Dry-Run: {self.dry_run}")
        print("\n시작 중...")

        try:
            # 각 서비스 시작
            self.start_trading_engine()
            self.start_auto_manager()
            self.start_telegram_bot()

            # 시작 알림
            self.send_startup_notification()

            print("\n✅ 모든 서비스 시작 완료")
            print("   Ctrl+C로 종료\n")
            print("=" * 60)

            # 시그널 핸들러 등록
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

            # 메인 루프
            while self.running:
                # 스레드 상태 체크
                for thread in self.threads:
                    if not thread.is_alive():
                        logger.warning(f"스레드 종료됨: {thread.name}")

                import time
                time.sleep(10)

        except KeyboardInterrupt:
            self.stop()

    def _signal_handler(self, signum, frame):
        """시그널 핸들러"""
        logger.info(f"시그널 수신: {signum}")
        self.stop()

    def stop(self):
        """데몬 중지"""
        self.running = False

        from src.telegram import get_notifier
        notifier = get_notifier()
        notifier.send_message("🛑 퀀트 시스템이 종료되었습니다.")

        logger.info("데몬 종료 중...")
        print("\n데몬 종료됨")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='퀀트 시스템 통합 데몬')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Dry-run 모드 (기본값)')
    parser.add_argument('--no-dry-run', action='store_true',
                        help='실제 주문 모드')
    parser.add_argument('--virtual', action='store_true', default=True,
                        help='모의투자 (기본값)')
    parser.add_argument('--real', action='store_true',
                        help='실전투자')

    args = parser.parse_args()

    dry_run = not args.no_dry_run
    is_virtual = not args.real

    if args.real:
        confirm = input("⚠️ 실전투자 모드입니다. 계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소됨")
            return

    daemon = QuantDaemon(dry_run=dry_run, is_virtual=is_virtual)
    daemon.start()


if __name__ == "__main__":
    main()
