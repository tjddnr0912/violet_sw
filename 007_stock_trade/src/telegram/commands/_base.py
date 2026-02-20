"""
커맨드 공통 유틸리티

경로 구성, 일수 파싱, 에러 핸들링 데코레이터
"""

import logging
import functools
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "quant"


def parse_days_arg(context: ContextTypes.DEFAULT_TYPE, default: int = 7, max_days: int = 90) -> int:
    """컨텍스트에서 일수 인자 파싱. 유효하지 않으면 default 반환."""
    if context.args:
        try:
            return max(1, min(int(context.args[0]), max_days))
        except ValueError:
            pass
    return default


def with_error_handling(context_name: str):
    """
    커맨드 에러 핸들링 데코레이터.

    except 블록의 반복 패턴을 통합:
    - logger.error(raw traceback)
    - format_user_error → 텔레그램 전송
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            try:
                return await func(self, update, context, *args, **kwargs)
            except Exception as e:
                logger.error(f"{context_name} 실패: {e}", exc_info=True)
                from src.utils.error_formatter import format_user_error
                await update.message.reply_text(
                    format_user_error(e, context_name), parse_mode='HTML'
                )
        return wrapper
    return decorator
