"""
텔레그램 봇 모듈
- 거래 알림 전송
- 명령어 처리 (잔고, 시세 조회 등)
"""

import os
import asyncio
import logging
import time
import threading
from typing import Optional
from pathlib import Path

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from dotenv import load_dotenv

# 분리된 모듈에서 import
from .notifier import TelegramNotifier, NotificationType, get_notifier
from .validators import InputValidator
from .commands import (
    QueryCommandsMixin,
    ControlCommandsMixin,
    ActionCommandsMixin,
    SettingCommandsMixin,
    AnalysisCommandsMixin,
)

# 프로젝트 루트의 .env 파일 명시적 로드
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path, override=True)

# 로깅 설정
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramBot(
    QueryCommandsMixin,
    ControlCommandsMixin,
    ActionCommandsMixin,
    SettingCommandsMixin,
    AnalysisCommandsMixin,
):
    """텔레그램 봇 클래스 (양방향 명령어 처리용)"""

    def __init__(self, kis_client=None):
        """
        Args:
            kis_client: KISClient 인스턴스 (명령어에서 API 호출용)
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.kis_client = kis_client
        self.application: Optional[Application] = None
        self.notifier = TelegramNotifier()
        self._rebalance_lock = threading.Lock()

    def validate_config(self) -> bool:
        """설정 유효성 검증"""
        return self.notifier.validate_config()

    # ==================== 기본 명령어 ====================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """시작 명령어"""
        message = (
            "🤖 <b>퀀트 자동매매 봇</b>\n\n"
            "📋 /help - 전체 명령어 보기\n\n"
            "<b>주요 명령어:</b>\n"
            "/status - 시스템 상태\n"
            "/start_trading - 자동매매 시작\n"
            "/stop_trading - 자동매매 중지\n"
            "/positions - 보유 포지션\n"
            "/emergency_stop - 긴급 정지"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말 명령어"""
        message = (
            "📚 <b>명령어 도움말</b>\n\n"
            "<b>🔧 시스템 제어:</b>\n"
            "/start_trading - 자동매매 시작\n"
            "/stop_trading - 자동매매 중지\n"
            "/pause - 일시 정지\n"
            "/resume - 재개\n"
            "/emergency_stop - 긴급 정지\n"
            "/clear_emergency - 긴급 정지 해제\n\n"
            "<b>🔄 수동 실행:</b>\n"
            "/run_screening - 스크리닝 실행\n"
            "/run_rebalance - 리밸런싱 실행\n"
            "/rebalance - 긴급 리밸런싱 (보유 부족 시)\n"
            "/reconcile - 장부 점검 (KIS 실잔고 대조)\n"
            "/sync_positions - KIS 포지션 동기화\n"
            "/run_optimize - 최적화 실행\n\n"
            "<b>⚙️ 설정 변경:</b>\n"
            "/set_dryrun on|off - Dry-run 모드\n"
            "/set_target [N] - 목표 종목 수\n"
            "/set_stoploss [N] - 손절 비율(%)\n\n"
            "<b>📊 조회:</b>\n"
            "/status - 시스템 상태\n"
            "/positions - 보유 포지션\n"
            "/balance - 계좌 잔고\n"
            "/history [N] - 자산 변동 (N일)\n"
            "/trades [N] - 거래 내역 (N일)\n"
            "/capital - 투자 원금 대비 현황\n"
            "/orders [N] - 체결 내역 (N일)\n"
            "/logs - 최근 로그\n"
            "/report - 일일 리포트\n"
            "/monthly_report - 월간 리포트\n\n"
            "<b>📈 분석:</b>\n"
            "/screening - 스크리닝 결과\n"
            "/signal [코드] - 기술적 분석\n"
            "/price [코드] - 현재가 조회"
        )
        await update.message.reply_text(message, parse_mode='HTML')

    # ==================== Application 관련 ====================

    async def _post_init(self, application: Application) -> None:
        """Application 초기화 후 명령어 등록"""
        try:
            commands = [
                BotCommand("start", "Start bot"),
                BotCommand("help", "Show help"),
                BotCommand("status", "System status"),
                BotCommand("balance", "Account balance"),
                BotCommand("positions", "Position list"),
                BotCommand("start_trading", "Start trading"),
                BotCommand("stop_trading", "Stop trading"),
                BotCommand("pause", "Pause trading"),
                BotCommand("resume", "Resume trading"),
            ]
            await application.bot.set_my_commands(commands)
            logger.info("텔레그램 명령어 목록 등록 완료")
        except Exception as e:
            logger.warning(f"명령어 목록 등록 실패 (무시됨): {e}")

    def build_application(self) -> Application:
        """Application 빌드"""
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")

        self.application = Application.builder().token(self.bot_token).post_init(self._post_init).build()

        # 기본 명령어
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        # 시스템 제어 명령어
        self.application.add_handler(CommandHandler("start_trading", self.cmd_start_trading))
        self.application.add_handler(CommandHandler("stop_trading", self.cmd_stop_trading))
        self.application.add_handler(CommandHandler("pause", self.cmd_pause))
        self.application.add_handler(CommandHandler("resume", self.cmd_resume))
        self.application.add_handler(CommandHandler("emergency_stop", self.cmd_emergency_stop))
        self.application.add_handler(CommandHandler("clear_emergency", self.cmd_clear_emergency))

        # 수동 실행 명령어
        self.application.add_handler(CommandHandler("run_screening", self.cmd_run_screening))
        self.application.add_handler(CommandHandler("run_rebalance", self.cmd_run_rebalance))
        self.application.add_handler(CommandHandler("rebalance", self.cmd_rebalance))
        self.application.add_handler(CommandHandler("reconcile", self.cmd_reconcile))
        self.application.add_handler(CommandHandler("run_optimize", self.cmd_run_optimize))

        # 설정 변경 명령어
        self.application.add_handler(CommandHandler("set_dryrun", self.cmd_set_dryrun))
        self.application.add_handler(CommandHandler("set_target", self.cmd_set_target))
        self.application.add_handler(CommandHandler("set_stoploss", self.cmd_set_stoploss))

        # 조회 명령어
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("positions", self.cmd_positions))
        self.application.add_handler(CommandHandler("balance", self.cmd_balance))
        self.application.add_handler(CommandHandler("history", self.cmd_history))
        self.application.add_handler(CommandHandler("trades", self.cmd_trades))
        self.application.add_handler(CommandHandler("capital", self.cmd_capital))
        self.application.add_handler(CommandHandler("orders", self.cmd_orders))
        self.application.add_handler(CommandHandler("logs", self.cmd_logs))
        self.application.add_handler(CommandHandler("report", self.cmd_report))
        self.application.add_handler(CommandHandler("monthly_report", self.cmd_monthly_report))

        # 포지션 관리 명령어
        self.application.add_handler(CommandHandler("close", self.cmd_close))
        self.application.add_handler(CommandHandler("close_all", self.cmd_close_all))
        self.application.add_handler(CommandHandler("sync_positions", self.cmd_sync_positions))

        # 분석 명령어
        self.application.add_handler(CommandHandler("screening", self.cmd_screening))
        self.application.add_handler(CommandHandler("signal", self.cmd_signal))
        self.application.add_handler(CommandHandler("price", self.cmd_price))

        return self.application

    def run(self):
        """봇 실행 (블로킹)"""
        app = self.build_application()
        logger.info("텔레그램 봇 시작...")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


class TelegramBotHandler:
    """데몬용 텔레그램 봇 핸들러 (스레드 안전)"""

    def __init__(self, kis_client=None):
        self.bot = TelegramBot(kis_client=kis_client)
        self.running = False
        self._loop = None

    def start(self):
        """봇 시작 (블로킹) - 네트워크 에러 시 자동 재시작"""
        self.running = True
        logger.info("텔레그램 봇 핸들러 시작...")

        max_init_retries = 5
        max_runtime_retries = 10
        runtime_retry_count = 0

        while self.running and runtime_retry_count < max_runtime_retries:
            retry_delay = 3

            for attempt in range(max_init_retries):
                if not self.running:
                    break

                app = None
                try:
                    app = self.bot.build_application()
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)

                    logger.info(f"텔레그램 봇 초기화 중... (시도 {attempt + 1}/{max_init_retries})")
                    self._loop.run_until_complete(app.initialize())
                    self._loop.run_until_complete(app.start())
                    self._loop.run_until_complete(app.updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True
                    ))
                    logger.info("텔레그램 봇 초기화 성공")

                    if runtime_retry_count == 0:
                        try:
                            self.bot.notifier.send_message("🤖 텔레그램 봇이 시작되었습니다.\n/help 명령어로 사용법을 확인하세요.")
                        except Exception as e:
                            logger.warning(f"시작 알림 전송 실패 (무시): {e}")
                    else:
                        try:
                            self.bot.notifier.send_message(f"🔄 텔레그램 봇 재연결 성공 (재시도 {runtime_retry_count}회)")
                        except Exception:
                            pass

                    runtime_retry_count = 0

                    while self.running:
                        self._loop.run_until_complete(asyncio.sleep(1))
                    return

                except Exception as e:
                    error_str = str(e)

                    is_conflict_error = "Conflict" in error_str or "terminated by other" in error_str

                    is_network_error = any(x in error_str for x in [
                        "Timed out", "ReadTimeout", "ConnectError",
                        "ConnectTimeout", "NetworkError", "ConnectionError"
                    ])

                    if is_conflict_error:
                        conflict_delay = 10 + (attempt * 5)
                        if attempt < max_init_retries - 1:
                            logger.warning(f"텔레그램 봇 Conflict 에러 (시도 {attempt + 1}/{max_init_retries}), {conflict_delay}초 후 재시도...")
                            time.sleep(conflict_delay)
                            continue
                        else:
                            logger.error(f"텔레그램 봇 Conflict 에러 지속: {e}")
                            break
                    elif is_network_error:
                        if attempt < max_init_retries - 1:
                            logger.warning(f"텔레그램 봇 네트워크 에러 (시도 {attempt + 1}/{max_init_retries}), {retry_delay}초 후 재시도...")
                            time.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 60)
                            continue
                        else:
                            logger.error(f"텔레그램 봇 초기화 실패 (최대 재시도 초과): {e}")
                            break
                    else:
                        logger.error(f"텔레그램 봇 오류: {e}", exc_info=True)
                        break
                finally:
                    if self._loop:
                        try:
                            if app is not None:
                                self._loop.run_until_complete(app.updater.stop())
                                self._loop.run_until_complete(app.stop())
                                self._loop.run_until_complete(app.shutdown())
                        except Exception:
                            pass
                        self.bot.application = None

            if self.running:
                runtime_retry_count += 1
                wait_time = min(30 * runtime_retry_count, 300)
                logger.warning(f"텔레그램 봇 재시작 대기 {wait_time}초... (런타임 재시도 {runtime_retry_count}/{max_runtime_retries})")
                time.sleep(wait_time)

        if runtime_retry_count >= max_runtime_retries:
            logger.error("텔레그램 봇 최대 재시작 횟수 초과 - 봇 스레드 종료")
        logger.info("텔레그램 봇 핸들러 종료됨")

    def stop(self):
        """봇 중지"""
        self.running = False
        if self._loop and self.bot.application:
            try:
                self._loop.run_until_complete(self.bot.application.updater.stop())
                self._loop.run_until_complete(self.bot.application.stop())
                self._loop.run_until_complete(self.bot.application.shutdown())
            except Exception as e:
                logger.debug(f"봇 종료 중 오류 (무시): {e}")
        logger.info("텔레그램 봇 핸들러 중지 요청됨")
