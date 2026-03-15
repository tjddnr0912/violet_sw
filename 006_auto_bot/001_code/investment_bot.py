#!/usr/bin/env python3
"""
Investment Bot - 뉴스·투자 분석 통합 오케스트레이터
----------------------------------------------------
뉴스봇(매일) + 버핏봇(월~금) + 섹터봇(일요일)을 하나의 프로세스에서 관리

실행 방법:
  python investment_bot.py              # 스케줄 모드 (전체 통합)
  python investment_bot.py --test       # 테스트 모드 (업로드 스킵)
"""

import os
import sys
import time
import logging
import argparse
import schedule
from datetime import datetime

from dotenv import load_dotenv

# Suppress gRPC/ALTS warnings from Google API
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
load_dotenv(override=True)

# 로그 디렉토리 생성
os.makedirs('./logs', exist_ok=True)
log_filename = f"./logs/investment_bot_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description='Investment Bot - News + Buffett + Sector Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
스케줄:
  매일  07:00  뉴스 수집·요약·업로드
  월~금 07:30  버핏의 투자 노트
  일    09:00  주간 뉴스 요약
  매월1일 10:00  월간 뉴스 요약
  일    13:00~18:00  11개 섹터별 투자 분석
  일    18:30  주간 섹터 요약 알림
  일    19:00  종합 투자 평가 보고서

개별 실행은 각 봇 직접 호출:
  python main.py --mode once [--test]
  python buffett_bot.py --once [--test]
  python weekly_sector_bot.py --once [--test]
  python weekly_sector_bot.py --comprehensive [--test]
  python weekly_sector_bot.py --sector 1 [--test]
        """
    )
    parser.add_argument('--test', action='store_true', help='Test mode (skip upload)')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Investment Bot - Orchestrator Starting")
    logger.info("=" * 60)

    # === 뉴스봇 초기화 ===
    from main import NewsBot
    news_bot = NewsBot()
    logger.info("NewsBot initialized")

    # === 섹터봇 초기화 ===
    from weekly_sector_bot import WeeklySectorBot
    sector_bot = WeeklySectorBot(test_mode=args.test)

    # === 버핏봇 초기화 ===
    from buffett_bot import BuffettBot
    buffett_bot = BuffettBot(test_mode=args.test)

    # === 스케줄 등록 ===

    # 뉴스봇: 매일 07:00 일간 뉴스
    schedule.every().day.at("07:00").do(
        _safe_run, "NewsDaily", news_bot.run_daily_task
    )
    logger.info("Scheduled: News Daily at 07:00")

    # 버핏봇: 월~금 07:30
    for day in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']:
        getattr(schedule.every(), day).at("07:30").do(
            _safe_run, "Buffett", buffett_bot.run
        )
    logger.info("Scheduled: Buffett Bot Mon-Fri 07:30")

    # 뉴스봇: 일요일 09:00 주간 뉴스 요약
    schedule.every().sunday.at("09:00").do(
        _safe_run, "NewsWeekly", news_bot.run_weekly_task
    )
    logger.info("Scheduled: News Weekly at Sunday 09:00")

    # 뉴스봇: 매일 10:00 월간 체크 (1일에만 실행)
    schedule.every().day.at("10:00").do(
        _safe_run, "NewsMonthlyCheck", news_bot._check_and_run_monthly
    )
    logger.info("Scheduled: News Monthly check at 10:00 (runs on 1st only)")

    # 섹터봇: 일요일 13:00~18:00 (11개 섹터)
    from sector_bot import SECTORS
    for sector in SECTORS:
        schedule.every().sunday.at(sector.scheduled_time).do(
            _safe_run, f"Sector-{sector.id}({sector.name})",
            sector_bot.process_sector, sector.id
        )
        logger.info(f"Scheduled: {sector.name} at Sunday {sector.scheduled_time}")

    # 섹터봇: 일요일 18:30 주간 요약 알림
    schedule.every().sunday.at("18:30").do(
        _safe_run, "WeeklySummary", sector_bot._send_weekly_summary
    )
    logger.info("Scheduled: Weekly Summary at Sunday 18:30")

    # 종합 보고서: 일요일 19:00
    schedule.every().sunday.at("19:00").do(
        _safe_run, "ComprehensiveReport", sector_bot.generate_comprehensive_report
    )
    logger.info("Scheduled: Comprehensive Report at Sunday 19:00")

    total_jobs = len(schedule.get_jobs())
    logger.info("=" * 60)
    logger.info(f"All {total_jobs} schedules registered. Waiting...")
    logger.info("=" * 60)

    # === 스케줄 루프 ===
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Stopped by user")


def _safe_run(name: str, func, *args, **kwargs):
    """스케줄 작업을 안전하게 실행 (예외 발생해도 프로세스 유지)"""
    logger.info(f"[{name}] Triggered")
    try:
        func(*args, **kwargs)
        logger.info(f"[{name}] Completed")
    except Exception as e:
        logger.error(f"[{name}] Failed: {e}", exc_info=True)


if __name__ == '__main__':
    main()
