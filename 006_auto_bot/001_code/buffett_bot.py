#!/usr/bin/env python3
"""
Buffett Bot - 워렌 버핏 & 찰리 멍거 일일 투자 분석
----------------------------------------------------
매일 오전 7:30, 뉴스봇이 생성한 일간 뉴스 요약을 읽고
버핏/멍거 관점의 투자 분석 보고서를 블로그에 업로드

실행 방법:
  python buffett_bot.py              # 스케줄 모드 (월~금 07:30)
  python buffett_bot.py --once       # 즉시 1회 실행
  python buffett_bot.py --test       # 테스트 (업로드 스킵)
"""

import glob
import os
import sys
import re
import time
import logging
import argparse
import subprocess
import tempfile
import schedule
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.wordpress_uploader import WordPressUploader
from shared.telegram_notifier import TelegramNotifier
from shared.claude_html_converter import convert_md_to_html_via_claude

# Load environment variables
load_dotenv(override=True)

# 로그 디렉토리 생성
os.makedirs('./logs', exist_ok=True)
log_filename = f"./logs/buffett_bot_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 설정
NEWS_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '004_News_paper')
BUFFETT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '005_Buffett_Daily')
BLOGGER_BLOG_ID = os.getenv('SECTOR_BLOGGER_BLOG_ID', '9115231004981625966')  # OgusInvest
BLOGGER_CREDENTIALS_PATH = os.getenv('BLOGGER_CREDENTIALS_PATH', './credentials/blogger_credentials.json')
BLOGGER_TOKEN_PATH = os.getenv('BLOGGER_TOKEN_PATH', './credentials/blogger_token.pkl')
TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
CLAUDE_TIMEOUT = 900  # 15분
CLAUDE_MAX_RETRIES = 3
CLAUDE_RETRY_DELAY = 30  # 초
SCHEDULE_TIME = "07:30"


def find_today_news_summary(date: datetime = None) -> Optional[str]:
    """오늘 날짜의 뉴스 요약 MD 파일 찾기"""
    if date is None:
        date = datetime.now()

    date_str = date.strftime('%Y%m%d')
    date_dir = os.path.join(NEWS_OUTPUT_DIR, date_str)

    if not os.path.exists(date_dir):
        logger.warning(f"News directory not found: {date_dir}")
        return None

    # blog_summary_*.md 파일 찾기 (가장 최신 파일)
    pattern = os.path.join(date_dir, f'blog_summary_{date_str}_*.md')
    files = sorted(glob.glob(pattern))

    if not files:
        logger.warning(f"No blog summary found in {date_dir}")
        return None

    latest_file = files[-1]
    logger.info(f"Found news summary: {latest_file}")

    with open(latest_file, 'r', encoding='utf-8') as f:
        return f.read()


def load_buffett_skill() -> str:
    """버핏 스킬 파일 로드 (YAML frontmatter 제거)"""
    skill_path = os.path.expanduser("~/.claude/skills/buffett/SKILL.md")

    if not os.path.exists(skill_path):
        raise FileNotFoundError(f"Buffett skill not found: {skill_path}")

    with open(skill_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # YAML frontmatter 제거 (--- ... --- 블록)
    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)

    return content.strip()


def build_buffett_prompt(news_content: str, date: datetime = None) -> str:
    """버핏/멍거 프롬프트 구성 — SKILL.md 파일 참조"""
    if date is None:
        date = datetime.now()

    date_str = date.strftime('%Y년 %m월 %d일')

    skill_content = load_buffett_skill()

    return f"""{skill_content}

# 오늘의 뉴스 데이터

- **뉴스 기준일**: {date_str}

{news_content}
"""


def call_claude(prompt: str) -> str:
    """Claude CLI 호출 (빈 응답 시 자동 재시도)"""
    logger.info(f"Calling Claude CLI ({len(prompt)} chars)...")

    for attempt in range(1, CLAUDE_MAX_RETRIES + 1):
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False, encoding='utf-8'
            ) as f:
                f.write(prompt)
                temp_file = f.name

            with open(temp_file, 'r', encoding='utf-8') as f:
                result = subprocess.run(
                    ['claude', '-p', '--dangerously-skip-permissions', '-'],
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=CLAUDE_TIMEOUT,
                )

            os.unlink(temp_file)

        except subprocess.TimeoutExpired:
            if 'temp_file' in locals():
                os.unlink(temp_file)
            raise RuntimeError(f"Claude CLI timed out after {CLAUDE_TIMEOUT}s")
        except FileNotFoundError:
            if 'temp_file' in locals():
                os.unlink(temp_file)
            raise RuntimeError("Claude CLI not found")

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {(result.stderr or '')[:500]}")

        output = result.stdout.strip()
        if output:
            logger.info(f"Claude CLI response: {len(output)} chars")
            return output

        stderr_hint = f" (stderr: {result.stderr[:200]})" if result.stderr else ""
        if attempt < CLAUDE_MAX_RETRIES:
            logger.warning(
                f"Claude CLI returned empty response (attempt {attempt}/{CLAUDE_MAX_RETRIES}){stderr_hint}, "
                f"retrying in {CLAUDE_RETRY_DELAY}s..."
            )
            time.sleep(CLAUDE_RETRY_DELAY)
        else:
            logger.error(
                f"Claude CLI returned empty response after {CLAUDE_MAX_RETRIES} attempts{stderr_hint}"
            )
            raise RuntimeError(f"Claude CLI returned empty response after {CLAUDE_MAX_RETRIES} retries")


def convert_long_md_to_html(md_content: str) -> str:
    """긴 마크다운을 h2 기준 청크 분할 후 HTML 변환"""
    sections = re.split(r'(?=^## )', md_content, flags=re.MULTILINE)

    chunks = []
    current = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(current) + len(section) < 5000:
            current += "\n\n" + section if current else section
        else:
            if current:
                chunks.append(current)
            current = section
    if current:
        chunks.append(current)

    logger.info(f"Split into {len(chunks)} chunks for HTML conversion")

    html_parts = []
    for i, chunk in enumerate(chunks, 1):
        logger.info(f"Converting chunk {i}/{len(chunks)} ({len(chunk)} chars)...")
        try:
            html, _ = convert_md_to_html_via_claude(
                chunk, editorial={"author": "buffett", "content_type": "buffett"}
            )
            if len(html) < len(chunk) * 0.3:
                logger.warning(f"Chunk {i} HTML too short, using markdown")
                html = None
            else:
                logger.info(f"Chunk {i} HTML: {len(html)} chars")
        except Exception as e:
            logger.warning(f"Chunk {i} HTML conversion failed: {e}")
            html = None
        html_parts.append(html)

    combined = ""
    for html, chunk in zip(html_parts, chunks):
        combined += (html if html else chunk) + "\n\n"

    return combined.strip()


class BuffettBot:
    """워렌 버핏 일일 투자 분석 봇"""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode

        if not test_mode:
            # WordPress(grace-moon.com) 발행 — 버핏봇 → '일일시황'(6)
            self.blogger = WordPressUploader(
                default_categories=[6],
                strip_ads_default=True,
            )
        else:
            self.blogger = None

        if TELEGRAM_ENABLED:
            self.telegram = TelegramNotifier(
                bot_token=TELEGRAM_BOT_TOKEN,
                chat_id=TELEGRAM_CHAT_ID,
            )
        else:
            self.telegram = None

        logger.info(f"BuffettBot initialized (test_mode={test_mode})")

    def run(self) -> dict:
        """버핏 분석 보고서 생성 및 업로드"""
        logger.info("=== Buffett Daily Analysis ===")

        result = {'success': False, 'blog_url': None, 'error': None}

        try:
            # 1. 뉴스 요약 읽기
            news_content = find_today_news_summary()
            if not news_content:
                raise Exception("Today's news summary not found. News bot may not have run yet.")

            logger.info(f"News summary loaded: {len(news_content)} chars")

            # 2. 버핏 프롬프트 구성 및 Claude 분석
            prompt = build_buffett_prompt(news_content)
            analysis = call_claude(prompt)

            if len(analysis) < 1000:
                logger.warning(f"Analysis too short: {len(analysis)} chars")

            # 3. 마크다운 저장
            today = datetime.now()
            date_str = today.strftime('%Y%m%d')
            output_dir = os.path.join(BUFFETT_OUTPUT_DIR, date_str)
            os.makedirs(output_dir, exist_ok=True)

            title = f"{today.strftime('%Y-%m-%d')} 버핏의 투자 노트"
            report_content = f"""## {title}

> 작성일: {today.strftime('%Y년 %m월 %d일')}
> 관점: Warren Buffett & Charlie Munger

---

{analysis}
"""

            filepath = os.path.join(output_dir, f'buffett_daily_{date_str}.md')
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"Report saved: {filepath} ({len(report_content)} chars)")

            # 4. HTML 변환 및 블로그 업로드
            if not self.test_mode:
                logger.info("Converting to HTML (chunked)...")
                html_content = convert_long_md_to_html(report_content)

                labels = ['버핏의 투자노트', '일간', '투자정보']

                upload_result = self.blogger.upload_post(
                    title=title,
                    content=html_content,
                    labels=labels,
                    is_draft=False,
                    is_markdown=False,
                )

                if not upload_result['success']:
                    raise Exception(f"Upload failed: {upload_result.get('message')}")

                result['blog_url'] = upload_result.get('url')
                logger.info(f"Uploaded: {result['blog_url']}")
            else:
                logger.info("Test mode - skipping upload")

            result['success'] = True

            # 5. Telegram 알림
            if self.telegram:
                today_str = today.strftime('%Y년 %m월 %d일')
                link_text = f"<a href='{result['blog_url']}'>블로그 보기</a>" if result['blog_url'] else "테스트 모드"
                message = f"🎩 <b>{today_str} 버핏의 투자 노트</b>\n\n{link_text}"
                try:
                    self.telegram.send_message(message, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Telegram notification failed: {e}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Buffett bot error: {error_msg}")
            result['error'] = error_msg

            if self.telegram:
                try:
                    self.telegram.send_message(
                        f"❌ <b>버핏의 투자 노트 생성 실패</b>\n\n에러: {error_msg}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        return result

    def run_scheduled(self):
        """스케줄 모드 (월~금)"""
        logger.info(f"Starting scheduled mode (Mon-Fri {SCHEDULE_TIME})")

        schedule.every().monday.at(SCHEDULE_TIME).do(self._scheduled_job)
        schedule.every().tuesday.at(SCHEDULE_TIME).do(self._scheduled_job)
        schedule.every().wednesday.at(SCHEDULE_TIME).do(self._scheduled_job)
        schedule.every().thursday.at(SCHEDULE_TIME).do(self._scheduled_job)
        schedule.every().friday.at(SCHEDULE_TIME).do(self._scheduled_job)
        logger.info(f"Scheduled: Buffett analysis Mon-Fri at {SCHEDULE_TIME}")

        while True:
            schedule.run_pending()
            time.sleep(60)

    def _scheduled_job(self):
        """스케줄된 작업"""
        logger.info("Scheduled Buffett analysis triggered")
        self.run()


def main():
    parser = argparse.ArgumentParser(
        description='Buffett Bot - Daily Investment Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python buffett_bot.py              # 스케줄 모드 (월~금 07:30)
  python buffett_bot.py --once       # 즉시 1회 실행
  python buffett_bot.py --test       # 테스트 (업로드 스킵)
  python buffett_bot.py --once --test  # 즉시 실행 + 업로드 스킵
        """
    )
    parser.add_argument('--once', action='store_true', help='Run once immediately')
    parser.add_argument('--test', action='store_true', help='Test mode (skip upload)')

    args = parser.parse_args()

    bot = BuffettBot(test_mode=args.test)

    if args.once:
        logger.info("Running Buffett analysis once")
        result = bot.run()
        print(f"\nResult: {'Success' if result['success'] else 'Failed'}")
        if result.get('blog_url'):
            print(f"URL: {result['blog_url']}")
        if result.get('error'):
            print(f"Error: {result['error']}")
    else:
        logger.info("Starting scheduled mode")
        try:
            bot.run_scheduled()
        except KeyboardInterrupt:
            logger.info("Stopped by user")


if __name__ == '__main__':
    main()
