"""
Sector Searcher - Gemini Google Search Grounding
-------------------------------------------------
Gemini API의 Google Search 도구를 사용하여 섹터별 최신 뉴스 검색.

Quota handling (May 2026 ~): 429/503 발생 시 모델 fallback chain
(gemini-3.1-flash-lite → gemini-3.5-flash → gemini-3-flash-preview →
gemini-2.5-flash)으로 자동 전환된다. 기존 `gemini -p` CLI fallback은
2026-06 CLI 종료에 맞춰 제거됨.
"""

import logging
import os
import re
import time
import ssl
from typing import List, Dict, Optional

from google.genai import types

from .config import SectorConfig, Sector
from shared.gemini_cli import (
    GeminiResponse,
    call_gemini_with_fallback,
    is_quota_error,
    extract_urls,
)

logger = logging.getLogger(__name__)

# 스킬 파일 경로
SEARCH_SKILL_FILE = os.path.expanduser('~/.claude/skills/sector-search/SKILL.md')


def load_search_skill() -> str:
    """섹터 검색 스킬 파일 로드 (YAML frontmatter 제거)"""
    if not os.path.exists(SEARCH_SKILL_FILE):
        raise FileNotFoundError(f"Sector search skill not found: {SEARCH_SKILL_FILE}")

    with open(SEARCH_SKILL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
    return content.strip()

# SSL 인증서 검증 비활성화 (일부 환경에서 필요)
ssl._create_default_https_context = ssl._create_unverified_context


class SectorSearcher:
    """Gemini Google Search Grounding을 사용한 섹터 정보 검색"""

    def __init__(self):
        """Initialize the searcher.

        API key/client are managed by shared.gemini_cli; we just hold the
        model preference here. Fallback chain is read from
        GEMINI_FALLBACK_MODELS env (see shared.gemini_cli for defaults).
        """
        if not SectorConfig.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required")

        # 환경변수가 비어있을 경우 SectorConfig 값을 백업으로 export
        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = SectorConfig.GEMINI_API_KEY

        self.model_name = SectorConfig.GEMINI_MODEL
        # `_use_cli_fallback` was removed in May 2026 — kept as False for any
        # external code that still inspects it via is_cli_mode_active().
        self._use_cli_fallback = False

        self.safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        ]

        logger.info(f"SectorSearcher initialized (primary model: {self.model_name})")

    def _models_chain(self) -> List[str]:
        """Build [primary, *fallbacks] for this searcher. Same logic as the
        summarizer — primary comes from SectorConfig.GEMINI_MODEL, fallbacks
        from GEMINI_FALLBACK_MODELS env."""
        raw = os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash",
        )
        fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
        return [self.model_name] + [m for m in fallbacks if m != self.model_name]

    def search_sector(
        self,
        sector: Sector,
        retry_count: int = 0
    ) -> Dict[str, any]:
        """
        섹터별 최신 투자 정보 검색

        Args:
            sector: 검색할 섹터
            retry_count: 현재 재시도 횟수 (네트워크/일시 오류용)

        Returns:
            {'content': str, 'sources': List[str], 'success': bool}
        """
        try:
            logger.info(f"Searching sector: {sector.name} ({sector.name_en})")

            search_prompt = self._build_search_prompt(sector)

            response: GeminiResponse = call_gemini_with_fallback(
                search_prompt,
                use_grounding=True,
                safety_settings=self.safety_settings,
                models=self._models_chain(),
            )

            if response.safety_blocked:
                logger.warning(f"Search safety-blocked for {sector.name}")
                return {
                    'content': '',
                    'sources': [],
                    'success': False,
                    'error': 'Safety filter blocked response',
                }

            content = (response.text or "").strip()
            sources = list(response.sources)

            # Grounding이 출처를 안 돌려준 케이스(예: 3-flash-preview 모델로
            # fallback된 경우)에는 본문에서 URL을 긁어 폴백.
            if not sources and content:
                sources = extract_urls(content)

            if not content:
                raise ValueError(
                    f"Empty response from {response.model_used} "
                    f"(finish={response.finish_reason})"
                )

            logger.info(
                f"Search completed: model={response.model_used} "
                f"chars={len(content)} sources={len(sources)}"
            )

            return {
                'content': content,
                'sources': sources,
                'success': True,
                'model_used': response.model_used,
            }

        except Exception as e:
            logger.error(f"Search error for {sector.name}: {e}")

            # 429/503 등은 wrapper가 이미 모든 모델을 소진한 후에만 여기로 올라옴.
            # 일시적 네트워크/타임아웃 오류는 retry로 회복 가능.
            if is_quota_error(e):
                logger.warning(
                    f"All models in chain exhausted for {sector.name}; "
                    f"no further fallback available"
                )
                return {
                    'content': '',
                    'sources': [],
                    'success': False,
                    'error': f"All Gemini models quota-exhausted: {e}",
                }

            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)
                logger.info(
                    f"Retrying in {delay} seconds... "
                    f"(attempt {retry_count + 1}/{SectorConfig.MAX_RETRIES})"
                )
                time.sleep(delay)
                return self.search_sector(sector, retry_count + 1)

            return {
                'content': '',
                'sources': [],
                'success': False,
                'error': f"Search failed after {SectorConfig.MAX_RETRIES} retries: {e}",
            }

    def _build_search_prompt(self, sector: Sector) -> str:
        """섹터별 검색 프롬프트 생성 — SKILL.md 파일 참조"""

        keywords_str = ", ".join(sector.search_keywords[:5])
        focus_str = "\n".join(f"- {f}" for f in sector.analysis_focus)

        skill_content = load_search_skill()

        prompt = f"""{skill_content}

# Search Target

Sector: {sector.name}
Keywords: {keywords_str}

Focus areas:
{focus_str}
"""
        return prompt

    def search_all_sectors(
        self,
        sectors: Optional[List[Sector]] = None,
        start_from_id: int = 1
    ) -> Dict[int, Dict]:
        """
        여러 섹터 순차 검색

        Args:
            sectors: 검색할 섹터 목록 (None이면 전체)
            start_from_id: 시작할 섹터 ID (재개 기능용)

        Returns:
            섹터 ID를 키로 하는 검색 결과 딕셔너리
        """
        from .config import SECTORS

        if sectors is None:
            sectors = SECTORS

        results = {}
        for sector in sectors:
            if sector.id < start_from_id:
                continue

            result = self.search_sector(sector)
            results[sector.id] = result

            # API 속도 제한 방지
            if sector.id < len(sectors):
                time.sleep(5)

        return results


# CLI for testing
if __name__ == "__main__":
    import json
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    searcher = SectorSearcher()

    # 첫 번째 섹터 테스트
    from .config import SECTORS
    sector = SECTORS[0]  # AI/양자컴퓨터

    print(f"\n=== Testing search for: {sector.name} ===\n")
    result = searcher.search_sector(sector)

    if result['success']:
        print(f"Content ({len(result['content'])} chars):")
        print(result['content'][:1000] + "..." if len(result['content']) > 1000 else result['content'])
        print(f"\nSources ({len(result['sources'])}):")
        for url in result['sources'][:5]:
            print(f"  - {url}")
    else:
        print(f"Search failed: {result.get('error')}")
