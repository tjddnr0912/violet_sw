"""
Sector Searcher - Gemini Google Search Grounding
-------------------------------------------------
Gemini API의 Google Search 도구를 사용하여 섹터별 최신 뉴스 검색
"""

import logging
import os
import time
import ssl
from typing import List, Dict, Optional

from google import genai
from google.genai import types

from .config import SectorConfig, Sector

logger = logging.getLogger(__name__)

# SSL 인증서 검증 비활성화 (일부 환경에서 필요)
ssl._create_default_https_context = ssl._create_unverified_context


class SectorSearcher:
    """Gemini Google Search Grounding을 사용한 섹터 정보 검색"""

    def __init__(self):
        """Initialize Gemini client with Google Search tool"""
        if not SectorConfig.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required")

        # 새로운 google-genai SDK 클라이언트
        self.client = genai.Client(api_key=SectorConfig.GEMINI_API_KEY)
        self.model_name = SectorConfig.GEMINI_MODEL

        logger.info(f"SectorSearcher initialized with model: {self.model_name}")

    def search_sector(
        self,
        sector: Sector,
        retry_count: int = 0
    ) -> Dict[str, any]:
        """
        섹터별 최신 투자 정보 검색

        Args:
            sector: 검색할 섹터
            retry_count: 현재 재시도 횟수

        Returns:
            검색 결과 딕셔너리 {
                'content': str,  # 검색된 정보 텍스트
                'sources': List[str],  # 출처 URL 목록
                'success': bool
            }
        """
        try:
            logger.info(f"Searching sector: {sector.name} ({sector.name_en})")

            # 검색 프롬프트 생성
            search_prompt = self._build_search_prompt(sector)

            # Google Search 도구를 사용하여 검색 실행
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_HARASSMENT",
                            threshold="OFF"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_HATE_SPEECH",
                            threshold="OFF"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            threshold="OFF"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="OFF"
                        ),
                    ]
                )
            )

            # 응답 파싱
            content = response.text if response.text else ""
            sources = []

            # grounding_metadata에서 출처 추출
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    gm = candidate.grounding_metadata
                    if hasattr(gm, 'grounding_chunks') and gm.grounding_chunks:
                        for chunk in gm.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                if hasattr(chunk.web, 'uri') and chunk.web.uri:
                                    sources.append(chunk.web.uri)

            if not content:
                raise ValueError("Empty response from Gemini")

            # 중복 출처 제거
            sources = list(dict.fromkeys(sources))

            logger.info(f"Search completed: {len(content)} chars, {len(sources)} sources")

            return {
                'content': content,
                'sources': sources,
                'success': True
            }

        except Exception as e:
            logger.error(f"Search error for {sector.name}: {e}")

            # 재시도 로직
            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)  # 지수 백오프
                logger.info(f"Retrying in {delay} seconds... (attempt {retry_count + 1}/{SectorConfig.MAX_RETRIES})")
                time.sleep(delay)
                return self.search_sector(sector, retry_count + 1)

            return {
                'content': '',
                'sources': [],
                'success': False,
                'error': str(e)
            }

    def _build_search_prompt(self, sector: Sector) -> str:
        """섹터별 검색 프롬프트 생성"""

        keywords_str = ", ".join(sector.search_keywords[:5])  # 상위 5개 키워드
        focus_str = "\n".join(f"- {f}" for f in sector.analysis_focus)

        prompt = f"""You are a financial analyst researching the {sector.name} sector for investment insights.

Search for the latest news and developments from the past week about:
Keywords: {keywords_str}

Focus areas:
{focus_str}

Requirements:
1. Find the most recent and relevant news (within the last 7 days)
2. Include specific company names, stock tickers, and numbers when available
3. Mention any significant price movements, announcements, or market impacts
4. Include both US and global market perspectives
5. Provide factual information with specific dates and figures

Please provide a comprehensive summary of the current state and recent developments in this sector.
Include all relevant URLs/sources in your response.
Write in English but include Korean company names in parentheses if applicable.
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
