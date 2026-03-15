"""
Gemini CLI Fallback - API 할당량 초과 시 gemini -p 사용
------------------------------------------------------
Gemini API가 429 RESOURCE_EXHAUSTED를 반환할 때
Gemini CLI (gemini -p)를 통해 우회 실행
"""

import logging
import os
import re
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Gemini CLI timeout (5분)
GEMINI_CLI_TIMEOUT = 300


def is_quota_error(error: Exception) -> bool:
    """429 RESOURCE_EXHAUSTED 에러인지 확인"""
    error_str = str(error)
    return "429" in error_str or "RESOURCE_EXHAUSTED" in error_str


def call_gemini_cli(prompt: str, timeout: int = GEMINI_CLI_TIMEOUT) -> str:
    """
    Gemini CLI (gemini -p)를 사용하여 프롬프트 실행

    Args:
        prompt: 프롬프트 텍스트
        timeout: 타임아웃 (초)

    Returns:
        Gemini CLI 응답 텍스트

    Raises:
        RuntimeError: CLI 실행 실패 시
    """
    gemini_path = shutil.which("gemini")
    if not gemini_path:
        raise RuntimeError("Gemini CLI not found. Install: npm install -g @anthropic-ai/gemini-cli")

    logger.info(f"Calling Gemini CLI (prompt: {len(prompt)} chars)")

    env = {**os.environ, "NO_COLOR": "1"}

    try:
        result = subprocess.run(
            [gemini_path, "--prompt", prompt, "--sandbox"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        output = result.stdout.strip()
        if not output and result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"Gemini CLI error (exit {result.returncode}): {stderr[:500]}")

        if not output:
            raise RuntimeError("Empty response from Gemini CLI")

        logger.info(f"Gemini CLI response: {len(output)} chars")
        return output

    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Gemini CLI timed out after {timeout}s")


def extract_urls(text: str) -> list[str]:
    """텍스트에서 URL 추출"""
    url_pattern = r'https?://[^\s<>\"\'\)\]，。）」』]+'
    urls = re.findall(url_pattern, text)
    # 중복 제거 (순서 유지)
    return list(dict.fromkeys(urls))
