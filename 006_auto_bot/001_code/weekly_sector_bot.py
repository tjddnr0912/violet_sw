#!/usr/bin/env python3
"""
Weekly Sector Investment Bot
----------------------------
매주 일요일 9개 섹터별 투자정보를 자동 수집/분석하여 OgusInvest 블로그에 업로드

실행 방법:
  python weekly_sector_bot.py --once      # 즉시 전체 실행
  python weekly_sector_bot.py --resume    # 중단 후 재개
  python weekly_sector_bot.py --sector 1  # 특정 섹터만 실행
  python weekly_sector_bot.py --test      # 테스트 (업로드 스킵)
  python weekly_sector_bot.py             # 스케줄 모드 (일요일 자동)
"""

import os
import sys
import time
import logging
import argparse
import schedule
from datetime import datetime, timedelta
from typing import Optional, List

from dotenv import load_dotenv

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sector_bot import (
    SectorConfig,
    SECTORS,
    SectorSearcher,
    SectorAnalyzer,
    SectorWriter,
    StateManager,
)
from shared.blogger_uploader import BloggerUploader
from shared.telegram_notifier import TelegramNotifier
from shared.claude_html_converter import convert_md_to_html_via_claude

# Load environment variables
load_dotenv(override=True)

# 로그 디렉토리 생성 (logging 설정 전에 수행)
os.makedirs('./logs', exist_ok=True)

# 날짜별 로그 파일명 생성
log_filename = f"./logs/sector_bot_{datetime.now().strftime('%Y%m%d')}.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class WeeklySectorBot:
    """주간 섹터 투자정보 봇"""

    def __init__(self, test_mode: bool = False):
        """
        Initialize bot

        Args:
            test_mode: True면 블로그 업로드 스킵
        """
        self.test_mode = test_mode

        # Validate configuration
        SectorConfig.validate()

        # Initialize components
        self.searcher = SectorSearcher()
        self.analyzer = SectorAnalyzer()
        self.writer = SectorWriter()
        self.state_manager = StateManager()

        # Blogger
        if not test_mode:
            self.blogger = BloggerUploader(
                blog_id=SectorConfig.BLOGGER_BLOG_ID,
                credentials_path=SectorConfig.BLOGGER_CREDENTIALS_PATH,
                token_path=SectorConfig.BLOGGER_TOKEN_PATH,
            )
        else:
            self.blogger = None

        # Telegram
        if SectorConfig.TELEGRAM_ENABLED:
            self.telegram = TelegramNotifier(
                bot_token=SectorConfig.TELEGRAM_BOT_TOKEN,
                chat_id=SectorConfig.TELEGRAM_CHAT_ID,
            )
        else:
            self.telegram = None

        logger.info(f"WeeklySectorBot initialized (test_mode={test_mode})")

    def process_sector(self, sector_id: int) -> dict:
        """
        단일 섹터 처리 (검색 → 분석 → 저장 → 업로드)

        Args:
            sector_id: 처리할 섹터 ID

        Returns:
            처리 결과 딕셔너리
        """
        sector = SectorConfig.get_sector_by_id(sector_id)
        logger.info(f"=== Processing Sector {sector_id}: {sector.name} ===")

        result = {
            'sector_id': sector_id,
            'sector_name': sector.name,
            'success': False,
            'blog_url': None,
            'error': None
        }

        try:
            # 1. 검색
            logger.info(f"[{sector.name}] Step 1: Searching...")
            search_result = self.searcher.search_sector(sector)

            if not search_result['success']:
                raise Exception(f"Search failed: {search_result.get('error')}")

            logger.info(f"[{sector.name}] Search: {len(search_result['content'])} chars, {len(search_result['sources'])} sources")

            # 2. 분석
            logger.info(f"[{sector.name}] Step 2: Analyzing...")
            analysis_result = self.analyzer.analyze_sector(sector, search_result)

            if not analysis_result['success']:
                raise Exception(f"Analysis failed: {analysis_result.get('error')}")

            logger.info(f"[{sector.name}] Analysis: {len(analysis_result['analysis'])} chars")

            # 3. 마크다운 저장
            logger.info(f"[{sector.name}] Step 3: Saving markdown...")
            title = self.analyzer.generate_title(sector)
            save_result = self.writer.save_analysis(
                sector=sector,
                analysis_result=analysis_result,
                title=title
            )

            if not save_result['success']:
                raise Exception(f"Save failed: {save_result.get('error')}")

            logger.info(f"[{sector.name}] Saved: {save_result['filepath']}")

            # 4. HTML 변환 및 블로그 업로드
            if not self.test_mode:
                logger.info(f"[{sector.name}] Step 4: Converting to HTML...")
                try:
                    html_content = convert_md_to_html_via_claude(
                        save_result['content'],
                        include_investment_disclaimer=True
                    )
                    logger.info(f"[{sector.name}] HTML: {len(html_content)} chars")
                except Exception as e:
                    logger.warning(f"[{sector.name}] HTML conversion failed, using markdown: {e}")
                    html_content = None

                logger.info(f"[{sector.name}] Step 5: Uploading to blog...")
                labels = SectorConfig.get_sector_labels(sector)

                upload_result = self.blogger.upload_post(
                    title=title,
                    content=html_content if html_content else save_result['content'],
                    labels=labels,
                    is_draft=False,
                    is_markdown=(html_content is None)
                )

                if not upload_result['success']:
                    raise Exception(f"Upload failed: {upload_result.get('message')}")

                result['blog_url'] = upload_result.get('url')
                logger.info(f"[{sector.name}] Uploaded: {result['blog_url']}")
            else:
                logger.info(f"[{sector.name}] Test mode - skipping upload")

            # 완료
            result['success'] = True
            self.state_manager.mark_sector_completed(sector_id, result['blog_url'])

            # Telegram 알림
            self._send_completion_notification(sector, result)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{sector.name}] Error: {error_msg}")
            result['error'] = error_msg
            self.state_manager.mark_sector_failed(sector_id, error_msg)

        return result

    def run_all_sectors(self, start_from_id: int = 1) -> List[dict]:
        """
        전체 섹터 순차 처리

        Args:
            start_from_id: 시작 섹터 ID

        Returns:
            각 섹터 처리 결과 리스트
        """
        logger.info(f"=== Running all sectors (starting from {start_from_id}) ===")

        results = []
        for sector in SECTORS:
            if sector.id < start_from_id:
                continue

            result = self.process_sector(sector.id)
            results.append(result)

            # 섹터 간 대기 (API 속도 제한 방지)
            if sector.id < len(SECTORS):
                wait_time = 30  # 30초 대기
                logger.info(f"Waiting {wait_time}s before next sector...")
                time.sleep(wait_time)

        # 전체 완료 알림
        self._send_summary_notification(results)

        return results

    def run_scheduled(self) -> None:
        """스케줄 모드로 실행"""
        logger.info("=== Starting scheduled mode ===")

        # 각 섹터별 스케줄 등록
        for sector in SECTORS:
            schedule.every().sunday.at(sector.scheduled_time).do(
                self._scheduled_sector_job,
                sector_id=sector.id
            )
            logger.info(f"Scheduled: {sector.name} at Sunday {sector.scheduled_time}")

        # 일요일 18:00에 전체 완료 알림
        schedule.every().sunday.at("18:00").do(self._send_weekly_summary)

        logger.info("Schedule registered. Waiting for Sunday...")

        # 스케줄 루프
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크

    def _scheduled_sector_job(self, sector_id: int) -> None:
        """스케줄된 섹터 작업 실행"""
        logger.info(f"Scheduled job triggered for sector {sector_id}")
        self.process_sector(sector_id)

    def _send_weekly_summary(self) -> None:
        """주간 완료 요약 알림"""
        progress = self.state_manager.get_progress()
        state = self.state_manager.load_state()

        summary = f"""📊 <b>주간 섹터 투자정보 완료</b>

완료: {progress['completed']}/{progress['total']} ({progress['percent']}%)
실패: {progress['failed']}

"""
        # 블로그 URL 추가
        blog_urls = state.get('blog_urls', {})
        if blog_urls:
            summary += "<b>업로드된 포스트:</b>\n"
            for sid, url in sorted(blog_urls.items()):
                sector = SectorConfig.get_sector_by_id(int(sid))
                summary += f"• {sector.name}: {url}\n"

        if self.telegram:
            self.telegram.send_message(summary, parse_mode="HTML")

    def _send_completion_notification(self, sector, result: dict) -> None:
        """섹터 완료 알림"""
        if not self.telegram:
            return

        if result['success']:
            message = f"""✅ <b>{sector.name}</b> 섹터 완료

{f"<a href='{result['blog_url']}'>블로그 보기</a>" if result['blog_url'] else "테스트 모드"}
"""
        else:
            message = f"""❌ <b>{sector.name}</b> 섹터 실패

에러: {result.get('error', 'Unknown')}
"""

        try:
            self.telegram.send_message(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")

    def _send_summary_notification(self, results: List[dict]) -> None:
        """전체 완료 요약 알림"""
        if not self.telegram:
            return

        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)

        message = f"""📊 <b>주간 섹터 투자정보 완료</b>

완료: {success_count}/{total_count}

"""
        for r in results:
            status = "✅" if r['success'] else "❌"
            message += f"{status} {r['sector_name']}"
            if r['blog_url']:
                message += f" (<a href='{r['blog_url']}'>링크</a>)"
            message += "\n"

        try:
            self.telegram.send_message(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description='Weekly Sector Investment Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python weekly_sector_bot.py --once      # 즉시 전체 실행
  python weekly_sector_bot.py --resume    # 중단 후 재개
  python weekly_sector_bot.py --sector 1  # 특정 섹터만 실행
  python weekly_sector_bot.py --test      # 테스트 (업로드 스킵)
  python weekly_sector_bot.py             # 스케줄 모드 (일요일 자동)
        """
    )

    parser.add_argument(
        '--once',
        action='store_true',
        help='Run all sectors once immediately'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from last incomplete sector'
    )
    parser.add_argument(
        '--sector',
        type=int,
        choices=range(1, 10),
        help='Run specific sector only (1-9)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode (skip blog upload)'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Show current state and exit'
    )
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Reset state and exit'
    )

    args = parser.parse_args()

    # 상태 확인/초기화
    state_manager = StateManager()

    if args.status:
        print(state_manager.get_summary())
        return

    if args.reset:
        state_manager.reset_state()
        print("State reset completed.")
        return

    # 봇 초기화
    bot = WeeklySectorBot(test_mode=args.test)

    # 실행 모드 결정
    if args.sector:
        # 특정 섹터만 실행
        logger.info(f"Running single sector: {args.sector}")
        result = bot.process_sector(args.sector)
        print(f"\nResult: {'Success' if result['success'] else 'Failed'}")
        if result['blog_url']:
            print(f"URL: {result['blog_url']}")
        if result['error']:
            print(f"Error: {result['error']}")

    elif args.resume:
        # 재개 모드
        resume_id = state_manager.get_resume_sector_id()
        if resume_id:
            logger.info(f"Resuming from sector {resume_id}")
            results = bot.run_all_sectors(start_from_id=resume_id)
        else:
            logger.info("Nothing to resume, all sectors completed or new week")
            print("Nothing to resume. Use --once to run all sectors.")

    elif args.once:
        # 즉시 전체 실행
        logger.info("Running all sectors once")
        results = bot.run_all_sectors()
        print(f"\nCompleted: {sum(1 for r in results if r['success'])}/{len(results)}")

    else:
        # 스케줄 모드
        logger.info("Starting scheduled mode")
        try:
            bot.run_scheduled()
        except KeyboardInterrupt:
            logger.info("Stopped by user")


if __name__ == '__main__':
    main()
