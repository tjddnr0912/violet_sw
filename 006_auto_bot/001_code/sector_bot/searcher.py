"""
Sector Searcher — Claude CLI + WebSearch
----------------------------------------
섹터별 최신 투자 정보 검색.

Migration timeline:
  - Pre 2026-05-27: `gemini -p` CLI (deprecated by Google, June 2026 shutdown)
  - 2026-05-27 AM: google-genai SDK + `google_search` grounding tool
  - 2026-05-27 PM: Claude CLI + WebSearch
      Gemini 3.x grounding has a separate, tight quota bucket that the AI
      Studio dashboard doesn't expose. Even with model RPD usage at
      10/500, every 3.x grounded call returned 429 — only 2.5-flash
      survived because its per-prompt pricing absorbs grounding charges.
      Rather than scrape by on one surviving model, sector search routes
      through Claude WebSearch where the quota lives in a different
      bucket. Sonnet primary, Opus fallback (섹터별 깊이가 요구되어
      Opus까지 한 단계 더 양보).

The companion `sector_bot/analyzer.py` still uses the Gemini API
(non-grounding, gemini-3.1-flash-lite chain) because analysis doesn't
need fresh web data — searcher already gathered it.
"""

import logging
import os
import re
import time
import ssl
from typing import List, Dict, Optional

from .config import SectorConfig, Sector
from shared.claude_search import (
    ClaudeSearchError,
    ClaudeSearchResponse,
)
from shared.web_search import web_search
from shared.gemini_cli import extract_urls  # URL regex utility, no API call

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
    """Claude CLI + WebSearch 기반 섹터 정보 검색."""

    def __init__(self):
        """Initialize the searcher.

        Claude CLI uses its own auth (ANTHROPIC_API_KEY env or stored
        credentials) — no client object held here. GEMINI_API_KEY is still
        validated for downstream `sector_bot/analyzer` which uses Gemini API
        on non-grounding (analysis-only) calls.
        """
        if not SectorConfig.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required (used by sector_bot.analyzer)")

        # Keep GEMINI_API_KEY exported in case analyzer reads it directly later.
        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = SectorConfig.GEMINI_API_KEY

        # Model preferences for Claude WebSearch (configurable via env).
        self.primary_model = os.getenv("CLAUDE_MODEL_SECTOR_SEARCH", "sonnet")
        self.fallback_model = os.getenv("CLAUDE_MODEL_SECTOR_SEARCH_FALLBACK", "opus")

        # Kept for sector_bot/orchestrator's is_cli_mode_active() check.
        # Always False after May 2026 (CLI fallback path removed entirely).
        self._use_cli_fallback = False

        logger.info(
            f"SectorSearcher initialized (Claude WebSearch, "
            f"primary={self.primary_model}, fallback={self.fallback_model})"
        )

    def search_sector(
        self,
        sector: Sector,
        retry_count: int = 0
    ) -> Dict[str, any]:
        """
        섹터별 최신 투자 정보 검색 via Claude CLI + WebSearch.

        Args:
            sector: 검색할 섹터
            retry_count: 현재 재시도 횟수 (네트워크/일시 오류용)

        Returns:
            {'content': str, 'sources': List[str], 'success': bool, 'model_used': str}
        """
        try:
            logger.info(f"Searching sector: {sector.name} ({sector.name_en})")

            search_prompt = self._build_search_prompt(sector)

            response: ClaudeSearchResponse = web_search(
                search_prompt,
                model=self.primary_model,
                fallback_model=self.fallback_model,
                timeout=900,
            )

            content = (response.text or "").strip()
            sources = list(response.sources)

            # WebSearch가 출처를 footer로 안 돌려준 경우에는 본문 URL을 폴백 추출.
            if not sources and content:
                sources = extract_urls(content)

            if not content:
                raise ValueError(
                    f"Empty response from claude WebSearch "
                    f"(model={response.model_used})"
                )

            logger.info(
                f"Search completed: model={response.model_used} "
                f"chars={len(content)} sources={len(sources)} "
                f"elapsed={response.elapsed_seconds:.1f}s"
            )

            return {
                'content': content,
                'sources': sources,
                'success': True,
                'model_used': response.model_used,
            }

        except ClaudeSearchError as e:
            logger.error(f"Claude WebSearch error for {sector.name}: {e}")
            # Retry on transient subprocess failures (timeout, non-zero exit).
            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)
                logger.info(
                    f"Retrying in {delay}s "
                    f"(attempt {retry_count + 1}/{SectorConfig.MAX_RETRIES})"
                )
                time.sleep(delay)
                return self.search_sector(sector, retry_count + 1)

            return {
                'content': '',
                'sources': [],
                'success': False,
                'error': f"Claude WebSearch failed after {SectorConfig.MAX_RETRIES} retries: {e}",
            }

        except Exception as e:
            logger.error(f"Search error for {sector.name}: {e}")
            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)
                logger.info(
                    f"Retrying in {delay}s "
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
