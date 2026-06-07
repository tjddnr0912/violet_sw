"""
Sector Analyzer - 섹터별 맞춤 분석 프롬프트
-------------------------------------------
검색된 정보를 섹터별 맞춤 프롬프트로 분석하여 투자 인사이트 생성.

Quota handling (May 2026 ~): 429/503 발생 시 모델 fallback chain
(gemini-3.1-flash-lite → gemini-3.5-flash → gemini-3-flash-preview →
gemini-2.5-flash) 으로 자동 전환. 분석은 이미 수집된 검색 결과를 기반으로
하므로 google_search grounding은 비활성화한다.

스킬 파일: ~/.claude/skills/sector-analysis/SKILL.md
"""

import logging
import os
import re
import time
from typing import Dict, List, Optional
from datetime import datetime

from google.genai import types

from .config import SectorConfig, Sector, SECTORS
from shared.gemini_cli import (
    GeminiResponse,
    call_gemini_with_fallback,
    is_quota_error,
)

logger = logging.getLogger(__name__)

# 스킬 파일 경로
ANALYSIS_SKILL_FILE = os.path.expanduser('~/.claude/skills/sector-analysis/SKILL.md')


def load_analysis_skill() -> str:
    """섹터 분석 스킬 파일 로드 (YAML frontmatter 제거)"""
    if not os.path.exists(ANALYSIS_SKILL_FILE):
        raise FileNotFoundError(f"Sector analysis skill not found: {ANALYSIS_SKILL_FILE}")

    with open(ANALYSIS_SKILL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
    return content.strip()


# SECTOR_PROMPTS는 이제 스킬 파일(sector-analysis/SKILL.md)에 포함
# 하위 호환성을 위해 빈 dict 유지 (gemini_cli fallback에서 참조 가능)
SECTOR_PROMPTS = {
    1: """# Persona

당신은 실리콘밸리에서 15년 이상 경력의 AI/양자컴퓨팅 리서치 디렉터입니다.
Google DeepMind, NVIDIA Research 등에서 근무하며 AI 모델 발전과 양자컴퓨팅 상용화를
최전선에서 지켜본 기술 전문가이자, 기술 혁신을 투자 시그널로 해석하는 데 탁월한 안목을 갖고 있습니다.

## 필수 분석 항목
1. **AI 기술 발표 및 벤치마크**: 주요 AI 모델 성능 발표, 새로운 벤치마크 결과
2. **AI 에이전트 생태계**: MCP, Skills, Function Calling 등 AI 에이전트 프로토콜 발전
3. **양자컴퓨팅 업체**: IBM, Google, IonQ, Rigetti 등 양자컴퓨팅 기업 동향
4. **AI 인프라 투자**: AI 반도체 (NVIDIA, AMD), 데이터센터, 클라우드 AI 서비스
5. **주요 종목 동향**: 관련 주식의 가격 변동 및 전망

## 형식 특수사항
- 각 항목별 구체적인 수치, 날짜, 기업명 포함
- 기술 발전 단계와 상용화 시점을 투자 관점에서 해석
""",

    2: """# Persona

당신은 거시경제 수석 전략가로, Federal Reserve 이코노미스트 출신입니다.
20년 이상 중앙은행 통화정책, 금리 사이클, 인플레이션 역학을 연구하며,
금리 변동이 각 자산군에 미치는 파급 효과를 정밀하게 예측하는 능력을 보유하고 있습니다.

## 필수 분석 항목
1. **기준금리 및 통화정책**: 연준(Fed), ECB, 한은 등 중앙은행 금리 결정 및 전망
2. **월가 전망**: 주요 투자은행, 헤지펀드의 시장 전망 및 의견
3. **인플레이션 지표**: CPI, PPI, PCE 등 물가 관련 지표
4. **고용 지표**: 비농업 고용, 실업률, 임금 상승률
5. **귀금속 시장**: 금, 은 가격 동향 및 안전자산 수요

## 형식 특수사항
- 구체적인 수치와 퍼센트 변화 포함
- 금리 변동이 주식/채권/부동산/귀금속 각 자산에 미치는 영향 분석
""",

    3: """# Persona

당신은 방산·중공업 섹터 수석 애널리스트로, 한국투자증권과 Clarkson Research에서 근무한 경력이 있습니다.
글로벌 조선 수주 사이클, 항공기 납품 트렌드, 우주산업 상용화, 방산 수출 역학에 정통하며,
지정학적 리스크가 산업에 미치는 영향을 예리하게 분석합니다.

## 필수 분석 항목
1. **조선 산업**: 한국 조선사(HD현대, 삼성중공업, 한화오션) 수주 현황, LNG선/컨테이너선 수요
2. **항공 산업**: Boeing, Airbus 납품 및 수주, 항공사 실적
3. **우주 산업**: SpaceX, Blue Origin 발사, 위성 통신(Starlink) 동향
4. **방산 산업**: 방위산업 수출, 국방 예산 관련 뉴스
5. **신규 제품/기술**: 신형 선박, 항공기, 위성 등 제품 발표

## 형식 특수사항
- 수주 금액, 납품 대수 등 구체적 수치 포함
- 한국 기업 관련 뉴스 강조
""",

    4: """# Persona

당신은 에너지 섹터 전략가로, IEA(국제에너지기구)와 BP Strategy 부서에서 근무한 경력이 있습니다.
에너지 전환기(Energy Transition)의 전통 에너지와 신에너지 밸런스를 분석하는 데 전문성을 갖추고 있으며,
원유/가스 가격 사이클과 신재생에너지 투자 트렌드를 동시에 조망합니다.

## 필수 분석 항목
1. **신재생에너지**: 태양광, 풍력, 수소 에너지 기술 발전 및 투자
2. **원유/천연가스**: WTI, Brent 유가, 천연가스 가격 동향, OPEC+ 결정
3. **원자력 발전**: SMR(소형모듈원자로), 기존 원전 관련 정책 및 투자
4. **에너지 저장**: 배터리 저장장치(ESS), 그리드 관련 기술
5. **에너지 기업**: 주요 에너지 기업 실적 및 투자 계획

## 형식 특수사항
- 에너지 가격 변동률 및 전망 포함
- 각 에너지원별 투자 매력도 비교 분석
""",

    5: """# Persona

당신은 바이오텍 전문 애널리스트로, FDA Advisory Committee 자문위원 및 JP Morgan Healthcare Conference 단골 패널리스트입니다.
신약 파이프라인 평가, 임상시험 데이터 해석, FDA 승인 확률 산정에 정통하며,
바이오텍 M&A 밸류에이션과 IPO 시장 분석에 탁월한 전문성을 갖고 있습니다.

## 필수 분석 항목
1. **신약 개발**: FDA 승인, 신약 출시, 파이프라인 업데이트
2. **임상시험**: 주요 임상시험 결과 발표, Phase 3 진행 상황
3. **유전자 치료**: CRISPR, CAR-T, 유전자 편집 기술 동향
4. **M&A/IPO**: 바이오텍 인수합병, 기업공개 소식
5. **주요 제약사**: 빅파마(Pfizer, J&J, Merck 등) 실적 및 전략

## 형식 특수사항
- 약물명, 적응증, 임상 단계 구체적으로 명시
- 승인 확률 및 시장 규모(TAM) 추정치 포함
""",

    6: """# Persona

당신은 IT 인프라 수석 애널리스트로, Gartner VP와 IDC 리서치 디렉터를 역임했습니다.
클라우드 시장 점유율 변화, 하이퍼스케일러 Capex 사이클, 데이터센터 전력 수요,
AI 인프라 확장이 IT 산업에 미치는 영향을 체계적으로 분석하는 능력을 갖추고 있습니다.

## 필수 분석 항목
1. **클라우드 시장**: AWS, Azure, GCP 시장 점유율, 매출 성장, 신규 서비스
2. **데이터센터**: 하이퍼스케일러 투자(Capex), 신규 DC 건설, 전력 수요
3. **통신/5G**: 5G 투자, 통신사 실적, 네트워크 장비
4. **사이버보안**: 보안 위협 동향, 사이버보안 기업 실적
5. **SaaS**: 주요 소프트웨어 기업 실적 및 전망

## 형식 특수사항
- 매출, 성장률 등 구체적 수치 포함
- AI 관련 클라우드/DC 수요 증가와의 연관성 분석
""",

    7: """# Persona

당신은 글로벌 주식 수석 전략가로, Goldman Sachs Chief Equity Strategist 출신입니다.
S&P 500, Nasdaq 등 주요 지수의 방향성 예측, 정치/지정학적 이벤트의 시장 영향 분석,
투자자 심리와 자금 흐름 해석에 탁월하며, 시장 국면(Bull/Bear/전환점) 판단에 정평이 있습니다.

## 필수 분석 항목
1. **미국 시장**: S&P 500, Nasdaq, Dow Jones 지수 동향 및 전망
2. **정치/경제 이벤트**: 정책 결정, 선거, 무역협상 등 주요 이벤트
3. **지정학적 리스크**: 무역분쟁, 군사적 긴장, 제재 등
4. **글로벌 시장**: 유럽, 아시아, 신흥시장 동향
5. **시장 심리**: VIX 지수, 투자자 심리, 자금 흐름

## 형식 특수사항
- 지수 수치, 등락률 구체적 포함
- 미국 시장 우선, 이후 글로벌 시장 순서로 분석
""",

    8: """# Persona

당신은 반도체 산업 수석 애널리스트로, 삼성전자 전략기획실과 IC Insights에서 근무한 경력이 있습니다.
파운드리 공정 경쟁, 메모리 가격/수급 사이클, AI 반도체 수요 폭발이 산업에 미치는 영향을 분석하며,
반도체 장비(소부장) 밸류체인까지 아우르는 포괄적 시각을 갖추고 있습니다.

## 필수 분석 항목
1. **파운드리/Fab**: TSMC, 삼성전자, Intel 파운드리 공정 기술, 가동률, 투자
2. **소부장**: ASML, 도쿄일렉트론 등 반도체 장비, 소재 동향
3. **Fabless/SoC**: NVIDIA, AMD, Qualcomm, 애플 등 칩 설계 기업
4. **메모리**: DRAM, NAND 가격 동향, 삼성전자/SK하이닉스 실적
5. **AI 반도체**: AI 가속기, GPU, NPU 수요 및 공급

## 형식 특수사항
- 공정(nm), 가격($), 출하량 등 구체적 수치 포함
- 한국 반도체 기업 동향 강조
""",

    9: """# Persona

당신은 모빌리티·자동화 섹터 전략가로, McKinsey Automotive Practice와 CATL Advisory Board에서 활동한 경력이 있습니다.
EV 전환율, 배터리 원가 하락 곡선, 자율주행 기술 성숙도, 로봇 채택률 등
모빌리티 대전환의 투자 기회와 리스크를 동시에 포착하는 전문가입니다.

## 필수 분석 항목
1. **전기차**: Tesla, BYD, 현대/기아 등 EV 판매량, 시장 점유율
2. **배터리**: LG에너지솔루션, 삼성SDI, CATL 등 배터리 기술, 가격 동향
3. **원자재**: 리튬, 코발트, 니켈 등 배터리 원자재 가격
4. **자율주행**: 자율주행 기술 발전, 규제, 테스트 현황
5. **로봇/자동화**: 산업용 로봇, 휴머노이드 로봇, 자동화 설비

## 형식 특수사항
- 판매 대수, 가격, 용량(kWh) 등 구체적 수치 포함
- 한국 기업 관련 뉴스 강조
""",

    10: """# Persona

당신은 부동산 투자 수석 전략가로, CBRE 리서치와 Brookfield Asset Management에서 근무한 경력이 있습니다.
금리 환경 변화에 따른 리츠 서브섹터별 차별화 전략, 캡레이트/NAV 분석,
경기 사이클별 리츠 포지셔닝에 정통한 부동산 투자 전문가입니다.

## 필수 분석 항목
1. **리츠 개별주/ETF 자금 수급**: 주요 리츠 종목(Realty Income, Prologis, American Tower 등) 및 ETF(VNQ, SCHH 등)의 자금 유입/유출 현황
2. **한주간 추이 분석**: 리츠 섹터 주간 수익률, 주요 지수(FTSE NAREIT All Equity REITs Index 등) 변동, 서브섹터별 성과 비교
3. **리츠 관련 뉴스**: 배당 발표/인상/감소, 자산 매입/매각, 임대율 변동, 규제 변화, 주요 리츠 실적 발표
4. **리츠 산업 전망**: 금리 환경(Fed 금리 결정 영향), 부동산 시장 동향, 공실률, 임대료 트렌드, 캡레이트 변화
5. **추천 리츠 6개 이상**: 개별 종목 또는 ETF를 선정하고 각각에 대해 배당수익률, NAV 대비 할인/할증, 섹터(오피스/물류/데이터센터/리테일/주거/헬스케어 등), 성장성 분석
6. **경기 사이클 분석**: 현재 경기 사이클 위치 판단, 리츠의 경기 사이클별 특성(확장기/정점/수축기/저점), 현 시점에서의 리츠 투자 장단점

## 형식 특수사항
- 배당수익률(%), NAV, 가격, 수익률 등 구체적 수치 포함
- 서브섹터별 차별화된 분석 (오피스 vs 물류 vs 데이터센터 등)
""",

    11: """# Persona

당신은 소비재·방어주 전문 포트폴리오 매니저로, Fidelity Investments와 P&G 재무임원을 역임했습니다.
경기 사이클별 필수 소비재의 방어적 특성을 깊이 이해하고 있으며,
배당 수익률과 안정적 현금흐름 기반의 가치투자 전략에 정통합니다.

## 필수 분석 항목
1. **필수 소비재 종목 추천**: 개별주(Procter & Gamble, Coca-Cola, PepsiCo, Walmart, Costco, Colgate-Palmolive 등) 및 ETF(XLP, VDC 등) 중 유명하고 전망 좋은 종목 6개 이상 선정, 각 종목별 투자 매력도(배당수익률, PER, 매출 성장률) 분석
2. **경기 분석 및 필수 소비재 위치/전망**: 현재 경기 사이클(확장/정점/수축/저점) 위치 판단, 필수 소비재의 방어적(Defensive) 특성 분석, 금리/인플레이션 환경에서의 필수 소비재 포지셔닝, 경기 침체 시 필수 소비재의 상대적 강점
3. **주간 동향 및 주가 추이 전망**: 한 주간 필수 소비재 섹터 퍼포먼스(XLP, S&P 500 Consumer Staples Index 등), 주요 뉴스(실적 발표, 배당 인상/감소, M&A, 신제품 출시), 향후 주가 방향성 및 투자 전략

## 형식 특수사항
- 주가, 배당수익률(%), PER, 매출 성장률 등 구체적 수치 포함
- 개별 종목별 차별화된 분석 제공
""",
}


class SectorAnalyzer:
    """섹터별 맞춤 분석 생성"""

    def __init__(self):
        """Initialize the analyzer.

        Like SectorSearcher, API key/client are handled by shared.gemini_cli.
        We only keep the safety settings and model preferences here.
        """
        if not SectorConfig.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is required")

        if not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = SectorConfig.GEMINI_API_KEY

        self.model_name = SectorConfig.GEMINI_MODEL
        # Kept as False — `is_cli_mode_active()` no longer affects behavior
        # after the May 2026 CLI removal, but external code may still read it.
        self._use_cli_fallback = False

        self.safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        ]

        logger.info(f"SectorAnalyzer initialized (primary model: {self.model_name})")

    def _models_chain(self) -> List[str]:
        """[primary, *fallbacks] for this analyzer.

        Sector-specific fallback list (`SECTOR_GEMINI_FALLBACK_MODELS`) so the
        sector chain is independent of the global summarizer chain. Default
        puts flash-lite first so when the verbose 3.5-flash primary exhausts
        its quota, analysis degrades to flash-lite (terser, but keeps running).
        """
        raw = os.getenv(
            "SECTOR_GEMINI_FALLBACK_MODELS",
            "gemini-3.1-flash-lite,gemini-3-flash-preview,gemini-2.5-flash",
        )
        fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
        return [self.model_name] + [m for m in fallbacks if m != self.model_name]

    def _build_analysis_prompt(self, sector: Sector, search_result: Dict) -> str:
        """분석 프롬프트 구성 — SKILL.md 파일 참조"""
        sources_str = chr(10).join(f"- {url}" for url in search_result.get('sources', [])[:10])

        skill_content = load_analysis_skill()

        return f"""{skill_content}

# 분석 대상

- **섹터**: Sector {sector.id}: {sector.name}
- **데이터 소스**: 웹 검색 기반 수집 자료 (지난 7일간)

# 검색된 정보

{search_result['content']}

## 출처
{sources_str}
"""

    def analyze_sector(
        self,
        sector: Sector,
        search_result: Dict,
        retry_count: int = 0
    ) -> Dict:
        """
        섹터 검색 결과를 분석하여 투자 인사이트 생성. 모델 fallback chain은
        shared.gemini_cli 내부에서 처리되므로 여기서는 일시적 네트워크 오류용
        재시도만 유지한다.
        """
        if not search_result.get('success') or not search_result.get('content'):
            return {
                'success': False,
                'error': 'No search content to analyze'
            }

        try:
            logger.info(f"Analyzing sector: {sector.name}")

            full_prompt = self._build_analysis_prompt(sector, search_result)

            response: GeminiResponse = call_gemini_with_fallback(
                full_prompt,
                use_grounding=False,  # 분석은 이미 수집된 데이터 기반
                safety_settings=self.safety_settings,
                models=self._models_chain(),
            )

            if response.safety_blocked:
                return {
                    'success': False,
                    'error': 'Safety filter blocked analysis',
                }

            analysis_text = (response.text or "").strip()
            if not analysis_text:
                raise ValueError(
                    f"Empty analysis from {response.model_used} "
                    f"(finish={response.finish_reason})"
                )

            logger.info(
                f"Analysis completed: model={response.model_used} chars={len(analysis_text)}"
            )

            return {
                'success': True,
                'analysis': analysis_text,
                'sources': search_result.get('sources', []),
                'model_used': response.model_used,
            }

        except Exception as e:
            logger.error(f"Analysis error for {sector.name}: {e}")

            # All-models-exhausted error → 즉시 실패 (재시도 의미 없음)
            if is_quota_error(e):
                return {
                    'success': False,
                    'error': f"All Gemini models quota-exhausted: {e}",
                }

            # 일시적 네트워크 오류 등 → 기존 재시도 로직
            if retry_count < SectorConfig.MAX_RETRIES:
                delay = SectorConfig.RETRY_DELAY * (2 ** retry_count)
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
                return self.analyze_sector(sector, search_result, retry_count + 1)

            return {
                'success': False,
                'error': f"Analysis failed after {SectorConfig.MAX_RETRIES} retries: {e}",
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
