"""
Sector Analyzer - 섹터별 맞춤 분석 프롬프트
-------------------------------------------
검색된 정보를 섹터별 맞춤 프롬프트로 분석하여 투자 인사이트 생성
"""

import logging
import time
import ssl
from typing import Dict, List, Optional
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from .config import SectorConfig, Sector, SECTORS

logger = logging.getLogger(__name__)

# SSL 인증서 검증 비활성화
ssl._create_default_https_context = ssl._create_unverified_context


# 섹터별 맞춤 분석 프롬프트
SECTOR_PROMPTS = {
    1: """## AI/양자컴퓨터 섹터 분석

다음 정보를 바탕으로 AI 및 양자컴퓨터 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **AI 기술 발표 및 벤치마크**: 주요 AI 모델 성능 발표, 새로운 벤치마크 결과
2. **AI 에이전트 생태계**: MCP, Skills, Function Calling 등 AI 에이전트 프로토콜 발전
3. **양자컴퓨팅 업체**: IBM, Google, IonQ, Rigetti 등 양자컴퓨팅 기업 동향
4. **AI 인프라 투자**: AI 반도체 (NVIDIA, AMD), 데이터센터, 클라우드 AI 서비스
5. **주요 종목 동향**: 관련 주식의 가격 변동 및 전망

### 형식:
- 한글로 작성
- 각 항목별 구체적인 수치, 날짜, 기업명 포함
- 투자 관점에서의 시사점 제공
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    2: """## 금융 섹터 분석

다음 정보를 바탕으로 금융 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **기준금리 및 통화정책**: 연준(Fed), ECB, 한은 등 중앙은행 금리 결정 및 전망
2. **월가 전망**: 주요 투자은행, 헤지펀드의 시장 전망 및 의견
3. **인플레이션 지표**: CPI, PPI, PCE 등 물가 관련 지표
4. **고용 지표**: 비농업 고용, 실업률, 임금 상승률
5. **귀금속 시장**: 금, 은 가격 동향 및 안전자산 수요

### 형식:
- 한글로 작성
- 구체적인 수치와 퍼센트 변화 포함
- 금리 변동이 각 자산에 미치는 영향 분석
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    3: """## 조선/항공/우주 섹터 분석

다음 정보를 바탕으로 조선, 항공, 우주 산업 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **조선 산업**: 한국 조선사(HD현대, 삼성중공업, 한화오션) 수주 현황, LNG선/컨테이너선 수요
2. **항공 산업**: Boeing, Airbus 납품 및 수주, 항공사 실적
3. **우주 산업**: SpaceX, Blue Origin 발사, 위성 통신(Starlink) 동향
4. **방산 산업**: 방위산업 수출, 국방 예산 관련 뉴스
5. **신규 제품/기술**: 신형 선박, 항공기, 위성 등 제품 발표

### 형식:
- 한글로 작성
- 수주 금액, 납품 대수 등 구체적 수치 포함
- 한국 기업 관련 뉴스 강조
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    4: """## 에너지 섹터 분석

다음 정보를 바탕으로 에너지 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **신재생에너지**: 태양광, 풍력, 수소 에너지 기술 발전 및 투자
2. **원유/천연가스**: WTI, Brent 유가, 천연가스 가격 동향, OPEC+ 결정
3. **원자력 발전**: SMR(소형모듈원자로), 기존 원전 관련 정책 및 투자
4. **에너지 저장**: 배터리 저장장치(ESS), 그리드 관련 기술
5. **에너지 기업**: 주요 에너지 기업 실적 및 투자 계획

### 형식:
- 한글로 작성
- 에너지 가격 변동률 및 전망 포함
- 각 에너지원별 투자 매력도 분석
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    5: """## 바이오 섹터 분석

다음 정보를 바탕으로 바이오/제약 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **신약 개발**: FDA 승인, 신약 출시, 파이프라인 업데이트
2. **임상시험**: 주요 임상시험 결과 발표, Phase 3 진행 상황
3. **유전자 치료**: CRISPR, CAR-T, 유전자 편집 기술 동향
4. **M&A/IPO**: 바이오텍 인수합병, 기업공개 소식
5. **주요 제약사**: 빅파마(Pfizer, J&J, Merck 등) 실적 및 전략

### 형식:
- 한글로 작성
- 약물명, 적응증, 임상 단계 구체적으로 명시
- 승인 확률 및 시장 규모 추정치 포함
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    6: """## IT/통신/Cloud/DC 섹터 분석

다음 정보를 바탕으로 IT, 통신, 클라우드, 데이터센터 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **클라우드 시장**: AWS, Azure, GCP 시장 점유율, 매출 성장, 신규 서비스
2. **데이터센터**: 하이퍼스케일러 투자(Capex), 신규 DC 건설, 전력 수요
3. **통신/5G**: 5G 투자, 통신사 실적, 네트워크 장비
4. **사이버보안**: 보안 위협 동향, 사이버보안 기업 실적
5. **SaaS**: 주요 소프트웨어 기업 실적 및 전망

### 형식:
- 한글로 작성
- 매출, 성장률 등 구체적 수치 포함
- AI 관련 클라우드/DC 수요 증가 분석
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    7: """## 주식시장 전망 분석

다음 정보를 바탕으로 주식시장 전망 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **미국 시장**: S&P 500, Nasdaq, Dow Jones 지수 동향 및 전망
2. **정치/경제 이벤트**: 정책 결정, 선거, 무역협상 등 주요 이벤트
3. **지정학적 리스크**: 무역분쟁, 군사적 긴장, 제재 등
4. **글로벌 시장**: 유럽, 아시아, 신흥시장 동향
5. **시장 심리**: VIX 지수, 투자자 심리, 자금 흐름

### 형식:
- 한글로 작성
- 지수 수치, 등락률 구체적 포함
- 미국 시장 우선, 이후 글로벌 시장 순서
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    8: """## 반도체 섹터 분석

다음 정보를 바탕으로 반도체 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **파운드리/Fab**: TSMC, 삼성전자, Intel 파운드리 공정 기술, 가동률, 투자
2. **소부장**: ASML, 도쿄일렉트론 등 반도체 장비, 소재 동향
3. **Fabless/SoC**: NVIDIA, AMD, Qualcomm, 애플 등 칩 설계 기업
4. **메모리**: DRAM, NAND 가격 동향, 삼성전자/SK하이닉스 실적
5. **AI 반도체**: AI 가속기, GPU, NPU 수요 및 공급

### 형식:
- 한글로 작성
- 공정(nm), 가격($), 출하량 등 구체적 수치 포함
- 한국 반도체 기업 동향 강조
- 마지막에 "시장 영향 분석" 섹션 추가
""",

    9: """## 자동차/배터리/로봇 섹터 분석

다음 정보를 바탕으로 자동차, 배터리, 로봇 섹터 투자 분석 보고서를 작성하세요.

### 필수 분석 항목:
1. **전기차**: Tesla, BYD, 현대/기아 등 EV 판매량, 시장 점유율
2. **배터리**: LG에너지솔루션, 삼성SDI, CATL 등 배터리 기술, 가격 동향
3. **원자재**: 리튬, 코발트, 니켈 등 배터리 원자재 가격
4. **자율주행**: 자율주행 기술 발전, 규제, 테스트 현황
5. **로봇/자동화**: 산업용 로봇, 휴머노이드 로봇, 자동화 설비

### 형식:
- 한글로 작성
- 판매 대수, 가격, 용량(kWh) 등 구체적 수치 포함
- 한국 기업 관련 뉴스 강조
- 마지막에 "시장 영향 분석" 섹션 추가
""",
}


class SectorAnalyzer:
    """섹터별 맞춤 분석 생성"""

    def __init__(self):
        """Initialize Gemini client for analysis"""
        if not SectorConfig.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required")

        genai.configure(api_key=SectorConfig.GEMINI_API_KEY)

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        self.model = genai.GenerativeModel(
            model_name=SectorConfig.GEMINI_MODEL,
            safety_settings=self.safety_settings,
        )

        logger.info("SectorAnalyzer initialized")

    def analyze_sector(
        self,
        sector: Sector,
        search_result: Dict,
        retry_count: int = 0
    ) -> Dict:
        """
        섹터 검색 결과를 분석하여 투자 인사이트 생성

        Args:
            sector: 분석할 섹터
            search_result: searcher의 검색 결과
            retry_count: 재시도 횟수

        Returns:
            분석 결과 딕셔너리
        """
        try:
            if not search_result.get('success') or not search_result.get('content'):
                return {
                    'success': False,
                    'error': 'No search content to analyze'
                }

            logger.info(f"Analyzing sector: {sector.name}")

            # 섹터별 맞춤 프롬프트 가져오기
            sector_prompt = SECTOR_PROMPTS.get(sector.id, "")
            if not sector_prompt:
                sector_prompt = f"## {sector.name} 섹터 분석\n\n투자 관점에서 분석해주세요."

            # 전체 프롬프트 구성
            full_prompt = f"""{sector_prompt}

### 검색된 정보:
{search_result['content']}

### 출처:
{chr(10).join(f"- {url}" for url in search_result.get('sources', [])[:10])}

---
위 정보를 바탕으로 투자 분석 보고서를 작성해주세요.
보고서는 한글로 작성하고, 마크다운 형식을 사용하세요.
최소 2000자 이상으로 상세하게 작성해주세요.
"""

            # 분석 생성
            response = self.model.generate_content(full_prompt)

            if not response.candidates:
                raise ValueError("Empty response from Gemini")

            analysis_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'text') and part.text:
                    analysis_text += part.text

            if not analysis_text:
                raise ValueError("No analysis text generated")

            logger.info(f"Analysis completed: {len(analysis_text)} chars")

            return {
                'success': True,
                'analysis': analysis_text,
                'sources': search_result.get('sources', []),
            }

        except Exception as e:
            logger.error(f"Analysis error for {sector.name}: {e}")

            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                return self.analyze_sector(sector, search_result, retry_count + 1)

            return {
                'success': False,
                'error': str(e)
            }

    def generate_title(self, sector: Sector, date: datetime = None) -> str:
        """
        블로그 포스트 제목 생성

        Args:
            sector: 섹터 정보
            date: 날짜 (기본: 오늘)

        Returns:
            포스트 제목
        """
        if date is None:
            date = datetime.now()

        # 주차 계산
        week_number = (date.day - 1) // 7 + 1

        title = f"{date.strftime('%Y-%m-%d')} {week_number}주차 {sector.name} 투자정보"
        return title


# CLI for testing
if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    from .searcher import SectorSearcher

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 테스트
    searcher = SectorSearcher()
    analyzer = SectorAnalyzer()

    sector = SECTORS[0]  # AI/양자컴퓨터

    print(f"\n=== Testing analysis for: {sector.name} ===\n")

    # 검색
    search_result = searcher.search_sector(sector)

    if search_result['success']:
        # 분석
        analysis_result = analyzer.analyze_sector(sector, search_result)

        if analysis_result['success']:
            print(f"Analysis ({len(analysis_result['analysis'])} chars):")
            print(analysis_result['analysis'][:2000])
            print("\n...")
        else:
            print(f"Analysis failed: {analysis_result.get('error')}")
    else:
        print(f"Search failed: {search_result.get('error')}")
