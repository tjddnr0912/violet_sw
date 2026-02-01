"""
Sector Bot Configuration
------------------------
9개 섹터 정의 및 스케줄 설정
"""

import os
from dataclasses import dataclass
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass
class Sector:
    """섹터 정의"""
    id: int
    name: str
    name_en: str
    scheduled_time: str  # HH:MM format
    search_keywords: List[str]
    analysis_focus: List[str]


# 9개 섹터 정의
SECTORS: List[Sector] = [
    Sector(
        id=1,
        name="AI/양자컴퓨터",
        name_en="ai_quantum",
        scheduled_time="13:00",
        search_keywords=[
            "AI artificial intelligence investment 2026",
            "quantum computing stocks market 2026",
            "AI benchmark breakthrough this week",
            "MCP protocol AI agents",
            "quantum computing company news",
            "large language model investment",
            "AI semiconductor chips investment",
        ],
        analysis_focus=[
            "AI 기술 발표 및 벤치마크 성과",
            "MCP/Skills 등 AI 에이전트 생태계",
            "양자컴퓨팅 업체 동향 (IBM, Google, IonQ 등)",
            "AI 반도체 및 인프라 투자",
        ]
    ),
    Sector(
        id=2,
        name="금융",
        name_en="finance",
        scheduled_time="13:30",
        search_keywords=[
            "Federal Reserve interest rate decision 2026",
            "central bank monetary policy this week",
            "Wall Street outlook investment",
            "inflation CPI data 2026",
            "employment jobs report",
            "gold silver precious metals price",
            "treasury bond yield",
        ],
        analysis_focus=[
            "기준금리 및 통화정책 결정",
            "월가 전망 및 투자 의견",
            "인플레이션/CPI 지표",
            "고용지수 및 경제지표",
            "귀금속 시장 동향",
        ]
    ),
    Sector(
        id=3,
        name="조선/항공/우주",
        name_en="shipbuilding_aerospace",
        scheduled_time="14:00",
        search_keywords=[
            "shipbuilding industry investment 2026",
            "Korean shipyard orders news",
            "aerospace defense stocks",
            "space industry SpaceX news",
            "satellite launch investment",
            "aircraft manufacturer Boeing Airbus",
            "defense contractor stocks",
        ],
        analysis_focus=[
            "조선 수주 및 업황",
            "항공기 제조사 동향",
            "우주산업 및 위성 발사",
            "방산 관련 투자",
        ]
    ),
    Sector(
        id=4,
        name="에너지",
        name_en="energy",
        scheduled_time="14:30",
        search_keywords=[
            "renewable energy investment 2026",
            "oil price crude WTI Brent",
            "natural gas price market",
            "nuclear energy investment",
            "solar wind energy stocks",
            "energy storage battery",
            "hydrogen fuel cell investment",
        ],
        analysis_focus=[
            "신재생에너지 기술 및 투자",
            "원유/천연가스 가격 동향",
            "원자력 발전 관련 동향",
            "에너지 저장장치 시장",
        ]
    ),
    Sector(
        id=5,
        name="바이오",
        name_en="bio",
        scheduled_time="15:00",
        search_keywords=[
            "biotech pharmaceutical investment 2026",
            "FDA drug approval this week",
            "clinical trial results news",
            "gene therapy CRISPR stocks",
            "vaccine development news",
            "cancer treatment breakthrough",
            "biotech IPO acquisition",
        ],
        analysis_focus=[
            "신약 개발 및 FDA 승인",
            "임상시험 결과 발표",
            "유전자 치료 기술 동향",
            "바이오텍 M&A 및 IPO",
        ]
    ),
    Sector(
        id=6,
        name="IT/통신/Cloud/DC",
        name_en="it_cloud",
        scheduled_time="15:30",
        search_keywords=[
            "cloud computing AWS Azure Google 2026",
            "data center investment news",
            "5G telecommunications stocks",
            "cybersecurity investment",
            "software as a service SaaS",
            "enterprise software stocks",
            "hyperscaler capex data center",
        ],
        analysis_focus=[
            "클라우드 시장 동향 (AWS, Azure, GCP)",
            "데이터센터 투자 및 확장",
            "통신/5G 관련 동향",
            "사이버보안 시장",
        ]
    ),
    Sector(
        id=7,
        name="주식시장",
        name_en="stock_market",
        scheduled_time="16:00",
        search_keywords=[
            "US stock market outlook this week",
            "S&P 500 Nasdaq prediction",
            "geopolitical risk investment impact",
            "trade war tariff stocks",
            "global market volatility",
            "emerging markets investment",
            "stock market technical analysis",
        ],
        analysis_focus=[
            "미국 시장 전망 (S&P 500, Nasdaq)",
            "정치/경제 이벤트 영향",
            "지정학적 리스크 (무역, 군사)",
            "글로벌 시장 동향",
        ]
    ),
    Sector(
        id=8,
        name="반도체",
        name_en="semiconductor",
        scheduled_time="16:30",
        search_keywords=[
            "semiconductor chip stocks 2026",
            "TSMC Samsung foundry news",
            "Nvidia AMD Intel investment",
            "memory chips DRAM NAND price",
            "semiconductor equipment ASML",
            "AI chip GPU investment",
            "fabless chip design stocks",
        ],
        analysis_focus=[
            "파운드리/Fab 공정 동향",
            "소부장 (장비, 소재) 시장",
            "Fabless SoC 설계 동향",
            "메모리 (DRAM, NAND) 가격 및 수요",
        ]
    ),
    Sector(
        id=9,
        name="자동차/배터리/로봇",
        name_en="auto_battery_robot",
        scheduled_time="17:00",
        search_keywords=[
            "electric vehicle EV stocks 2026",
            "Tesla BYD EV sales",
            "EV battery lithium cobalt",
            "autonomous driving investment",
            "robotics automation stocks",
            "humanoid robot investment",
            "solid state battery news",
        ],
        analysis_focus=[
            "전기차 판매 및 시장 점유율",
            "배터리 기술 및 원자재 가격",
            "자율주행 기술 동향",
            "로봇/자동화 산업",
        ]
    ),
]


class SectorConfig:
    """Sector Bot Configuration"""

    # Gemini API
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('SECTOR_GEMINI_MODEL', 'gemini-3-flash-preview')

    # Blogger
    BLOGGER_BLOG_ID = os.getenv('SECTOR_BLOGGER_BLOG_ID', '9115231004981625966')  # OgusInvest
    BLOGGER_CREDENTIALS_PATH = os.getenv(
        'BLOGGER_CREDENTIALS_PATH',
        './credentials/blogger_credentials.json'
    )
    BLOGGER_TOKEN_PATH = os.getenv(
        'BLOGGER_TOKEN_PATH',
        './credentials/blogger_token.pkl'
    )

    # Telegram
    TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # Output
    OUTPUT_DIR = '../004_Sector_Weekly'

    # State file for resume functionality
    STATE_FILE = './sector_bot/state.json'

    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY = 60  # seconds

    # Claude CLI timeout (15 minutes for long HTML generation)
    CLAUDE_TIMEOUT = 900  # seconds

    # Schedule (Sunday)
    SCHEDULE_DAY = 6  # 0=Monday, 6=Sunday

    @classmethod
    def get_sector_by_id(cls, sector_id: int) -> Sector:
        """ID로 섹터 조회"""
        for sector in SECTORS:
            if sector.id == sector_id:
                return sector
        raise ValueError(f"Sector ID {sector_id} not found")

    @classmethod
    def get_sector_labels(cls, sector: Sector) -> List[str]:
        """섹터별 블로그 라벨 반환"""
        return [sector.name, '주간', '투자정보']

    @classmethod
    def validate(cls):
        """설정 검증"""
        errors = []

        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is not set")

        if not cls.BLOGGER_BLOG_ID:
            errors.append("SECTOR_BLOGGER_BLOG_ID is not set")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

        return True
