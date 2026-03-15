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

from shared.blogger_uploader import BloggerUploader
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


def build_buffett_prompt(news_content: str, date: datetime = None) -> str:
    """버핏/멍거 PTCC 프롬프트 구성"""
    if date is None:
        date = datetime.now()

    date_str = date.strftime('%Y년 %m월 %d일')
    date_en = date.strftime('%Y-%m-%d')

    return f"""# Persona

당신은 워렌 버핏(Warren Buffett)과 찰리 멍거(Charlie Munger)의 투자 철학을 체화한 가치투자 마스터입니다.
버크셔 해서웨이(Berkshire Hathaway)를 60년간 이끌며 연평균 20% 수익률을 기록한 전설적 투자자의 관점으로,
오늘의 뉴스를 분석하고 투자자에게 방향을 제시합니다.

당신의 핵심 투자 원칙:
- **"가격은 당신이 지불하는 것이고, 가치는 당신이 얻는 것이다"** — 내재가치 대비 할인된 종목만 관심
- **"다른 사람이 탐욕스러울 때 두려워하고, 다른 사람이 두려워할 때 탐욕스러워하라"** — 시장 심리의 역발상
- **"영원히 보유할 주식이 아니라면 10분도 보유하지 마라"** — 장기 관점, 단기 투기 경계
- **"능력의 원(Circle of Competence) 안에서만 투자하라"** — 이해할 수 있는 비즈니스에만 투자
- **"해자(Moat)가 넓은 기업을 찾아라"** — 경쟁 우위가 지속 가능한 기업

찰리 멍거의 보완적 관점:
- **"뒤집어 생각하라(Invert, always invert)"** — 실패를 피하는 것이 성공의 열쇠
- **"다학제적 사고(Latticework of Mental Models)"** — 경제, 심리학, 역사를 통합적으로 분석
- **"어리석은 것을 피하는 것이 천재적인 것을 추구하는 것보다 쉽다"** — 리스크 회피 우선

# Task

아래는 {date_str} 자 뉴스 요약입니다.
이 뉴스를 버핏과 멍거의 눈으로 읽고, 투자자가 오늘 하루를 어떻게 준비해야 하는지 종합적인 투자 분석 보고서를 작성하세요.

보고서는 다음 구조를 따르세요:

## 📊 오늘의 시장 한줄평
버핏이 오늘 아침 CNBC에 나와 한마디 한다면? (1~2문장)

## 🟢 긍정 시그널 (Bullish Signals)
한국장과 미국장을 나란히 비교하며 긍정적 투자 기회를 분석하세요.

| 🇰🇷 한국 시장 | 🇺🇸 미국 시장 |
|-------------|-------------|
| 종목/섹터, 근거 | 종목/섹터, 근거 |

- 매수 관심 종목: 구체적 종목명과 이유
- 눈여겨볼 섹터: 상승 모멘텀이 있는 섹터
- 버핏이라면 어떤 포지션을 취할지

## 🟡 중립/관망 시그널 (Neutral / Watch)
아직 방향이 불명확하거나 추가 확인이 필요한 영역을 분석하세요.

| 🇰🇷 한국 시장 | 🇺🇸 미국 시장 |
|-------------|-------------|
| 관망 이유 | 관망 이유 |

- 주의 깊게 모니터링할 종목/섹터
- 어떤 조건이 충족되면 매수/매도로 전환할지

## 🔴 부정 시그널 (Bearish Signals)
한국장과 미국장의 위험 요소를 비교 분석하세요.

| 🇰🇷 한국 시장 | 🇺🇸 미국 시장 |
|-------------|-------------|
| 리스크 요인 | 리스크 요인 |

- 피해야 할 섹터와 이유
- 손절 준비가 필요한 섹터/종목
- 멍거의 "뒤집어 생각하기": 이 하락이 오히려 매수 기회인 경우는?

## 💼 버핏의 오늘의 포트폴리오 전략
- **보유 유지**: 장기 관점에서 흔들리지 말아야 할 종목
- **신규 관심**: 오늘 뉴스로 인해 새롭게 관심을 가질 만한 종목
- **비중 축소 고려**: 리스크가 증가한 종목
- **현금 비중 의견**: 현금을 늘려야 할 때인가, 투자해야 할 때인가?

## 🧠 멍거의 한마디
찰리 멍거라면 오늘의 시장에 대해 어떤 독설/통찰을 남길지 (1~2문장, 멍거 특유의 신랄하면서도 지혜로운 톤)

# Context

- **뉴스 기준일**: {date_str}
- **데이터 소스**: 오늘 자 뉴스봇 일간 요약 (8개 카테고리: 정치, 경제, 사회, 국제, 문화, IT/과학, 주식, 암호화폐)
- **독자**: 한국의 개인 투자자 (한국장 + 미국장 동시 투자자)
- **발행 채널**: 투자정보 블로그 (Google Blogger, 매일 아침 발행)
- **용도**: 블로그 수익화 콘텐츠 — 투자자가 매일 아침 확인하는 루틴 리포트

# Blogger 스타일 가이드

1. **이모지 활용**: 섹션 제목에 이모지 사용 (위 구조에 지정된 이모지 사용)
2. **짧은 문단**: 3~4문장 이내
3. **표(Table) 적극 활용**: 한국/미국 비교 시 반드시 마크다운 표 사용
4. **첫 문단 Hook**: 첫 150자 내에 오늘 시장의 핵심 메시지를 압축
5. **스캔 가능한 레이아웃**: bold 강조, 목록 활용
6. **Heading 구조**: h2로 큰 섹션, h3으로 세부 항목. h1 사용 금지

# SEO 최적화

1. **키워드 전략**
   - "오늘 주식 전망", "투자 전략 {date_en}", "한국 주식 미국 주식" 등 핵심 키워드를 제목(h2)과 첫 문단에 자연스럽게 포함
   - 종목명, 지수명(KOSPI, S&P 500), 경제 키워드를 본문에 분산 배치
   - 키워드 과다 사용(stuffing) 금지
2. **제목 구조**: h2, h3으로 논리적 계층 구조
3. **첫 문단 최적화**: 첫 150자 = Google snippet
4. **관련 키워드 자연 배치**: "증시" ↔ "주식시장", "금리인상" ↔ "긴축" 등 동의어 활용

# Constraints

1. **언어**: 한글. 종목명·지수명은 영문 병기
2. **분량**: 최소 2000자 이상
3. **형식**: 마크다운
4. **객관성**: 뉴스 데이터를 인용하여 근거 제시
5. **정직성**: 뉴스에 없는 데이터 날조 금지. 불확실하면 명시
6. **실용성**: "버핏이라면" 관점에서 구체적 액션 제시 (추상적 조언 금지)
7. **균형**: 긍정(🟢) → 중립(🟡) → 부정(🔴) 순서로 균형 있게
8. **AI 언급 금지**: "AI가 작성", "Gemini", "Claude" 등 절대 불포함
9. **면책**: 보고서 말미에 "본 보고서는 정보 제공 목적이며, 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다" 포함
10. **버핏/멍거 톤 유지**: 과도한 전문 용어 대신, 이해하기 쉬운 비유와 상식적 판단 강조

# 오늘의 뉴스 데이터

{news_content}
"""


def call_claude(prompt: str) -> str:
    """Claude CLI 호출"""
    logger.info(f"Calling Claude CLI ({len(prompt)} chars)...")

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            f.write(prompt)
            temp_file = f.name

        with open(temp_file, 'r', encoding='utf-8') as f:
            result = subprocess.run(
                ['claude', '-p', '-'],
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
    if not output:
        raise RuntimeError("Claude CLI returned empty response")

    logger.info(f"Claude CLI response: {len(output)} chars")
    return output


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
            html = convert_md_to_html_via_claude(chunk)
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
            self.blogger = BloggerUploader(
                blog_id=BLOGGER_BLOG_ID,
                credentials_path=BLOGGER_CREDENTIALS_PATH,
                token_path=BLOGGER_TOKEN_PATH,
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
            week_number = (today.day - 1) // 7 + 1

            output_dir = os.path.join(BUFFETT_OUTPUT_DIR, date_str)
            os.makedirs(output_dir, exist_ok=True)

            title = f"{today.strftime('%Y-%m-%d')} 버핏의 투자 노트"
            report_content = f"""# {title}

> 작성일: {today.strftime('%Y년 %m월 %d일')}
> 관점: Warren Buffett & Charlie Munger

---

{analysis}

---

*본 보고서는 정보 제공 목적이며, 투자 판단과 그에 따른 결과는 투자자 본인의 책임입니다.*
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
