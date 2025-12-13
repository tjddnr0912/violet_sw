#!/usr/bin/env python3
"""
Telegram + Gemini CLI + Blogger Integration Bot
------------------------------------------------
1. 텔레그램에서 메시지 수신 (polling)
2. Gemini CLI로 질문 전달
3. 결과를 Google Blogger에 업로드
4. 텔레그램으로 결과 알림

Usage:
    python telegram_gemini_bot.py           # 일반 실행
    python telegram_gemini_bot.py --test    # 테스트 모드 (블로그 업로드 스킵)
"""

import os
import sys
import time
import subprocess
import logging
import argparse
from datetime import datetime
from typing import Optional, Dict, Tuple
from dotenv import load_dotenv

# Load environment variables (override=True to use .env values over system env)
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramGeminiBot:
    """텔레그램 메시지를 받아 Gemini로 처리하고 Google Blogger에 업로드하는 봇"""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        upload_to_blog: bool = True
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.upload_to_blog = upload_to_blog
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.last_update_id = 0

        # Import requests here to handle missing module gracefully
        try:
            import requests
            self.requests = requests
        except ImportError:
            logger.error("requests 모듈이 필요합니다. pip install requests")
            sys.exit(1)

    def get_updates(self, offset: int = None) -> list:
        """텔레그램에서 새 메시지 가져오기"""
        try:
            url = f"{self.api_base}/getUpdates"
            params = {"timeout": 30}  # Long polling
            if offset:
                params["offset"] = offset

            response = self.requests.get(url, params=params, timeout=35)
            result = response.json()

            if result.get("ok"):
                return result.get("result", [])
            return []
        except Exception as e:
            logger.error(f"메시지 가져오기 실패: {e}")
            return []

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """텔레그램으로 메시지 보내기"""
        try:
            url = f"{self.api_base}/sendMessage"

            # 메시지 길이 제한 (4096자)
            if len(text) > 4000:
                text = text[:3900] + "\n\n... (내용이 길어 일부 생략됨)"

            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }

            response = self.requests.post(url, json=payload, timeout=30)
            result = response.json()
            return result.get("ok", False)
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            return False

    def run_gemini(self, question: str) -> Tuple[bool, str, str, list]:
        """
        Gemini CLI 실행

        Returns:
            Tuple[bool, str, str, list]: (성공 여부, 본문 내용, 제목, 라벨 리스트)
        """
        try:
            logger.info(f"Gemini 실행 중: {question[:50]}...")

            # 블로그 스타일 + 제목/라벨 생성을 포함한 프롬프트 구성
            prompt = f"""{question}

---
위 질문에 대해 블로그 게시글 형식으로 답변해줘.

중요: 사고 과정이나 분석 과정 없이 최종 답변만 바로 작성해줘. "Let me think", "I will", "Let's" 같은 중간 과정 설명 없이 독자에게 보여줄 완성된 글만 출력해.

작성 가이드:
- 질문이 한글이면 한글로, 영어면 영어로 답변
- 독자가 이해하기 쉽게 구조화된 형식으로 작성
- 적절한 소제목과 단락 구분 사용
- 핵심 내용은 굵게 또는 리스트로 강조
- 필요시 예시나 코드 포함
- 친근하고 읽기 쉬운 문체 사용

답변이 끝난 후 맨 마지막에 다음 형식으로 작성해줘:
TITLE: [전체 내용을 대표하는 간결한 제목]
LABELS: [핵심 키워드 2~3개를 쉼표로 구분]"""

            # gemini CLI 실행
            result = subprocess.run(
                ["gemini", prompt],
                capture_output=True,
                text=True,
                timeout=120  # 2분 타임아웃
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    logger.info("Gemini 응답 성공")
                    # 제목, 라벨, 본문 분리
                    content, title, labels = self._parse_response(output)
                    return True, content, title, labels
                else:
                    return False, "Gemini 응답이 비어있습니다.", "", []
            else:
                error = result.stderr.strip() or "알 수 없는 오류"
                return False, f"Gemini 오류: {error}", "", []

        except subprocess.TimeoutExpired:
            return False, "Gemini 응답 시간 초과 (2분)", "", []
        except FileNotFoundError:
            return False, "gemini CLI를 찾을 수 없습니다. 설치되어 있는지 확인하세요.", "", []
        except Exception as e:
            return False, f"Gemini 실행 오류: {str(e)}", "", []

    def _parse_response(self, response: str) -> Tuple[str, str, list]:
        """
        Gemini 응답에서 본문, 제목, 라벨 분리

        Returns:
            Tuple[str, str, list]: (본문, 제목, 라벨 리스트)
        """
        import re

        lines = response.strip().split('\n')
        title = ""
        labels = []
        content_end_idx = len(lines)

        # 뒤에서부터 TITLE:과 LABELS: 찾기
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()

            # LABELS: 패턴
            label_match = re.match(r'^LABELS?:\s*(.+)$', line, re.IGNORECASE)
            if label_match:
                label_str = label_match.group(1).strip()
                # 쉼표로 구분된 라벨 파싱
                labels = [l.strip() for l in label_str.split(',') if l.strip()]
                content_end_idx = min(content_end_idx, i)

            # TITLE: 패턴
            title_match = re.match(r'^TITLE:\s*(.+)$', line, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                content_end_idx = min(content_end_idx, i)

        # 본문 추출 (TITLE/LABELS 이전까지)
        content_lines = lines[:content_end_idx]

        # 마지막의 구분선(---) 및 빈 줄 제거
        while content_lines and content_lines[-1].strip() in ['---', '']:
            content_lines.pop()

        # 제목을 찾지 못한 경우 기본값
        if not title:
            title = response[:30].replace('\n', ' ').strip() + "..."

        # 라벨을 찾지 못한 경우 기본값
        if not labels:
            labels = ["AI", "Gemini"]

        content = '\n'.join(content_lines).strip()
        return content, title, labels

    def upload_to_blogger(self, title: str, content: str, labels: list = None) -> Tuple[bool, str]:
        """Google Blogger에 업로드"""
        if not self.upload_to_blog:
            return True, "(테스트 모드 - 업로드 스킵)"

        try:
            from blogger_uploader import BloggerUploader

            blog_id = os.getenv("BLOGGER_BLOG_ID")
            credentials_path = os.getenv("BLOGGER_CREDENTIALS_PATH", "./credentials/blogger_credentials.json")
            token_path = os.getenv("BLOGGER_TOKEN_PATH", "./credentials/blogger_token.pkl")
            is_draft = os.getenv("BLOGGER_IS_DRAFT", "false").lower() == "true"

            # 라벨이 없으면 기본값 사용
            if not labels:
                labels = ["AI", "Gemini"]

            if not blog_id:
                return False, "BLOGGER_BLOG_ID 환경변수가 설정되지 않았습니다."

            logger.info(f"Blogger 업로더 초기화 중... (라벨: {labels})")
            uploader = BloggerUploader(
                blog_id=blog_id,
                credentials_path=credentials_path,
                token_path=token_path
            )

            logger.info("블로그에 포스팅 중...")
            result = uploader.upload_post(
                title=title,
                content=content,
                labels=labels,
                is_draft=is_draft,
                is_markdown=True  # BloggerUploader가 자체적으로 마크다운 변환
            )

            if result.get("success"):
                post_url = result.get("url", "URL 없음")
                return True, post_url
            else:
                return False, result.get("message", "업로드 실패")

        except ImportError:
            return False, "blogger_uploader 모듈을 찾을 수 없습니다."
        except Exception as e:
            return False, f"업로드 오류: {str(e)}"

    def process_message(self, message: dict) -> None:
        """받은 메시지 처리"""
        text = message.get("text", "")
        chat = message.get("chat", {})
        from_user = message.get("from", {})

        # 허용된 chat_id만 처리
        if str(chat.get("id")) != self.chat_id:
            logger.warning(f"허용되지 않은 chat_id: {chat.get('id')}")
            return

        # 명령어 처리
        if text.startswith("/"):
            self._handle_command(text)
            return

        if not text:
            return

        logger.info(f"질문 수신: {text[:50]}...")

        # 처리 시작 알림
        self.send_message(f"질문을 받았습니다. Gemini에게 물어보는 중...")

        # Gemini 실행 (본문, 제목, 라벨 함께 반환)
        success, gemini_content, gemini_title, gemini_labels = self.run_gemini(text)

        if not success:
            self.send_message(f"Gemini 오류: {gemini_content}")
            return

        # 블로그 업로드 (Gemini가 생성한 제목과 라벨 사용)
        upload_success, upload_result = self.upload_to_blogger(gemini_title, gemini_content, gemini_labels)

        # 결과 메시지 작성
        labels_str = ', '.join(gemini_labels) if gemini_labels else '-'
        if upload_success:
            result_msg = f"""<b>Gemini 응답 완료!</b>

<b>제목:</b> {gemini_title}
<b>라벨:</b> {labels_str}

<b>블로그 업로드:</b> {upload_result}

<b>응답 미리보기:</b>
{gemini_content[:500]}{'...' if len(gemini_content) > 500 else ''}"""
        else:
            result_msg = f"""<b>Gemini 응답 완료!</b>

<b>제목:</b> {gemini_title}
<b>라벨:</b> {labels_str}

<b>블로그 업로드 실패:</b> {upload_result}

<b>응답:</b>
{gemini_content[:1000]}"""

        self.send_message(result_msg)
        logger.info(f"처리 완료 - 제목: {gemini_title}, 라벨: {gemini_labels}")

    def _handle_command(self, command: str) -> None:
        """명령어 처리"""
        cmd = command.split()[0].lower()

        if cmd == "/start":
            self.send_message("""<b>Gemini 블로그 봇</b>

질문을 입력하면:
1. Gemini CLI로 답변 생성
2. Google Blogger에 자동 업로드
3. 결과를 텔레그램으로 알림

<b>명령어:</b>
/help - 도움말
/status - 상태 확인""")

        elif cmd == "/help":
            self.send_message("""<b>사용법:</b>
그냥 질문을 입력하세요!

예시:
- Python에서 리스트 컴프리헨션이란?
- 블록체인 기술 설명해줘
- React와 Vue 차이점""")

        elif cmd == "/status":
            upload_status = "활성화" if self.upload_to_blog else "테스트 모드"
            self.send_message(f"""<b>봇 상태</b>
- 블로그 업로드: {upload_status}
- 마지막 업데이트 ID: {self.last_update_id}""")

        else:
            self.send_message(f"알 수 없는 명령어: {cmd}")

    def run(self) -> None:
        """봇 메인 루프"""
        logger.info("=" * 50)
        logger.info("Telegram Gemini Blogger Bot 시작")
        logger.info(f"Blogger 업로드: {'활성화' if self.upload_to_blog else '비활성화'}")
        logger.info("=" * 50)

        self.send_message("Gemini Blogger 봇이 시작되었습니다! 질문을 입력하세요.")

        while True:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1)

                for update in updates:
                    self.last_update_id = update["update_id"]

                    if "message" in update:
                        self.process_message(update["message"])

                time.sleep(1)  # 짧은 대기

            except KeyboardInterrupt:
                logger.info("봇 종료...")
                self.send_message("봇이 종료되었습니다.")
                break
            except Exception as e:
                logger.error(f"오류 발생: {e}")
                time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Telegram Gemini Blogger Bot")
    parser.add_argument("--test", action="store_true", help="테스트 모드 (블로그 업로드 스킵)")
    args = parser.parse_args()

    # 환경 변수 확인
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("오류: .env 파일에 TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID를 설정하세요.")
        sys.exit(1)

    # 봇 실행
    bot = TelegramGeminiBot(
        bot_token=bot_token,
        chat_id=chat_id,
        upload_to_blog=not args.test
    )

    bot.run()


if __name__ == "__main__":
    main()
