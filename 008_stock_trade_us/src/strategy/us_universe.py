"""
미국 주식 유니버스 구성 모듈
- S&P 500, NASDAQ 100 등 인덱스 구성종목 조회
- 종목 정보 및 가격 데이터 수집
"""

import logging
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import pandas as pd
import requests

logger = logging.getLogger(__name__)


@dataclass
class USStock:
    """미국 주식 종목 정보"""
    symbol: str           # 티커 심볼 (예: AAPL)
    name: str             # 회사명
    sector: str           # 섹터
    industry: str         # 산업
    exchange: str         # 거래소 (NYSE, NASDAQ)
    market_cap: float     # 시가총액 (억 달러)


class USUniverseBuilder:
    """미국 주식 유니버스 구성"""

    # S&P 500 구성 종목 (주요 종목 - 실제 운용 시 Wikipedia에서 최신 목록 파싱)
    SP500_TOP_100 = [
        # Technology
        ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics", "NASDAQ"),
        ("MSFT", "Microsoft Corporation", "Technology", "Software", "NASDAQ"),
        ("NVDA", "NVIDIA Corporation", "Technology", "Semiconductors", "NASDAQ"),
        ("GOOGL", "Alphabet Inc. Class A", "Technology", "Internet", "NASDAQ"),
        ("GOOG", "Alphabet Inc. Class C", "Technology", "Internet", "NASDAQ"),
        ("META", "Meta Platforms Inc.", "Technology", "Internet", "NASDAQ"),
        ("AVGO", "Broadcom Inc.", "Technology", "Semiconductors", "NASDAQ"),
        ("ORCL", "Oracle Corporation", "Technology", "Software", "NYSE"),
        ("CSCO", "Cisco Systems Inc.", "Technology", "Networking", "NASDAQ"),
        ("ADBE", "Adobe Inc.", "Technology", "Software", "NASDAQ"),
        ("CRM", "Salesforce Inc.", "Technology", "Software", "NYSE"),
        ("AMD", "Advanced Micro Devices", "Technology", "Semiconductors", "NASDAQ"),
        ("INTC", "Intel Corporation", "Technology", "Semiconductors", "NASDAQ"),
        ("IBM", "International Business Machines", "Technology", "IT Services", "NYSE"),
        ("QCOM", "Qualcomm Inc.", "Technology", "Semiconductors", "NASDAQ"),

        # Financials
        ("BRK.B", "Berkshire Hathaway Inc.", "Financials", "Diversified", "NYSE"),
        ("JPM", "JPMorgan Chase & Co.", "Financials", "Banks", "NYSE"),
        ("V", "Visa Inc.", "Financials", "Payments", "NYSE"),
        ("MA", "Mastercard Inc.", "Financials", "Payments", "NYSE"),
        ("BAC", "Bank of America Corp.", "Financials", "Banks", "NYSE"),
        ("WFC", "Wells Fargo & Co.", "Financials", "Banks", "NYSE"),
        ("GS", "Goldman Sachs Group", "Financials", "Investment Banking", "NYSE"),
        ("MS", "Morgan Stanley", "Financials", "Investment Banking", "NYSE"),
        ("AXP", "American Express Co.", "Financials", "Credit Services", "NYSE"),
        ("C", "Citigroup Inc.", "Financials", "Banks", "NYSE"),

        # Healthcare
        ("LLY", "Eli Lilly and Company", "Healthcare", "Pharmaceuticals", "NYSE"),
        ("UNH", "UnitedHealth Group", "Healthcare", "Insurance", "NYSE"),
        ("JNJ", "Johnson & Johnson", "Healthcare", "Pharmaceuticals", "NYSE"),
        ("MRK", "Merck & Co. Inc.", "Healthcare", "Pharmaceuticals", "NYSE"),
        ("ABBV", "AbbVie Inc.", "Healthcare", "Pharmaceuticals", "NYSE"),
        ("PFE", "Pfizer Inc.", "Healthcare", "Pharmaceuticals", "NYSE"),
        ("TMO", "Thermo Fisher Scientific", "Healthcare", "Diagnostics", "NYSE"),
        ("ABT", "Abbott Laboratories", "Healthcare", "Medical Devices", "NYSE"),
        ("DHR", "Danaher Corporation", "Healthcare", "Diagnostics", "NYSE"),
        ("BMY", "Bristol-Myers Squibb", "Healthcare", "Pharmaceuticals", "NYSE"),

        # Consumer Discretionary
        ("AMZN", "Amazon.com Inc.", "Consumer Discretionary", "E-Commerce", "NASDAQ"),
        ("TSLA", "Tesla Inc.", "Consumer Discretionary", "Automobiles", "NASDAQ"),
        ("HD", "Home Depot Inc.", "Consumer Discretionary", "Retail", "NYSE"),
        ("NKE", "Nike Inc.", "Consumer Discretionary", "Apparel", "NYSE"),
        ("MCD", "McDonald's Corporation", "Consumer Discretionary", "Restaurants", "NYSE"),
        ("SBUX", "Starbucks Corporation", "Consumer Discretionary", "Restaurants", "NASDAQ"),
        ("LOW", "Lowe's Companies Inc.", "Consumer Discretionary", "Retail", "NYSE"),
        ("TJX", "TJX Companies Inc.", "Consumer Discretionary", "Retail", "NYSE"),
        ("BKNG", "Booking Holdings Inc.", "Consumer Discretionary", "Travel", "NASDAQ"),
        ("CMG", "Chipotle Mexican Grill", "Consumer Discretionary", "Restaurants", "NYSE"),

        # Consumer Staples
        ("WMT", "Walmart Inc.", "Consumer Staples", "Retail", "NYSE"),
        ("PG", "Procter & Gamble Co.", "Consumer Staples", "Household Products", "NYSE"),
        ("KO", "Coca-Cola Company", "Consumer Staples", "Beverages", "NYSE"),
        ("PEP", "PepsiCo Inc.", "Consumer Staples", "Beverages", "NASDAQ"),
        ("COST", "Costco Wholesale Corp.", "Consumer Staples", "Retail", "NASDAQ"),
        ("PM", "Philip Morris International", "Consumer Staples", "Tobacco", "NYSE"),
        ("MO", "Altria Group Inc.", "Consumer Staples", "Tobacco", "NYSE"),
        ("CL", "Colgate-Palmolive Co.", "Consumer Staples", "Household Products", "NYSE"),
        ("MDLZ", "Mondelez International", "Consumer Staples", "Food", "NASDAQ"),
        ("KHC", "Kraft Heinz Company", "Consumer Staples", "Food", "NASDAQ"),

        # Communication Services
        ("NFLX", "Netflix Inc.", "Communication Services", "Streaming", "NASDAQ"),
        ("DIS", "Walt Disney Company", "Communication Services", "Entertainment", "NYSE"),
        ("CMCSA", "Comcast Corporation", "Communication Services", "Cable", "NASDAQ"),
        ("T", "AT&T Inc.", "Communication Services", "Telecom", "NYSE"),
        ("VZ", "Verizon Communications", "Communication Services", "Telecom", "NYSE"),
        ("TMUS", "T-Mobile US Inc.", "Communication Services", "Telecom", "NASDAQ"),

        # Industrials
        ("CAT", "Caterpillar Inc.", "Industrials", "Machinery", "NYSE"),
        ("BA", "Boeing Company", "Industrials", "Aerospace", "NYSE"),
        ("HON", "Honeywell International", "Industrials", "Conglomerate", "NASDAQ"),
        ("UNP", "Union Pacific Corp.", "Industrials", "Railroads", "NYSE"),
        ("RTX", "RTX Corporation", "Industrials", "Aerospace", "NYSE"),
        ("GE", "General Electric Co.", "Industrials", "Conglomerate", "NYSE"),
        ("DE", "Deere & Company", "Industrials", "Machinery", "NYSE"),
        ("LMT", "Lockheed Martin Corp.", "Industrials", "Aerospace", "NYSE"),
        ("UPS", "United Parcel Service", "Industrials", "Logistics", "NYSE"),
        ("MMM", "3M Company", "Industrials", "Conglomerate", "NYSE"),

        # Energy
        ("XOM", "Exxon Mobil Corporation", "Energy", "Oil & Gas", "NYSE"),
        ("CVX", "Chevron Corporation", "Energy", "Oil & Gas", "NYSE"),
        ("COP", "ConocoPhillips", "Energy", "Oil & Gas", "NYSE"),
        ("SLB", "Schlumberger Limited", "Energy", "Oil Services", "NYSE"),
        ("EOG", "EOG Resources Inc.", "Energy", "Oil & Gas", "NYSE"),

        # Materials
        ("LIN", "Linde plc", "Materials", "Chemicals", "NYSE"),
        ("APD", "Air Products & Chemicals", "Materials", "Chemicals", "NYSE"),
        ("SHW", "Sherwin-Williams Co.", "Materials", "Chemicals", "NYSE"),
        ("FCX", "Freeport-McMoRan Inc.", "Materials", "Mining", "NYSE"),
        ("NEM", "Newmont Corporation", "Materials", "Gold Mining", "NYSE"),

        # Utilities
        ("NEE", "NextEra Energy Inc.", "Utilities", "Electric", "NYSE"),
        ("DUK", "Duke Energy Corp.", "Utilities", "Electric", "NYSE"),
        ("SO", "Southern Company", "Utilities", "Electric", "NYSE"),
        ("D", "Dominion Energy Inc.", "Utilities", "Electric", "NYSE"),
        ("AEP", "American Electric Power", "Utilities", "Electric", "NYSE"),

        # Real Estate
        ("PLD", "Prologis Inc.", "Real Estate", "Industrial REIT", "NYSE"),
        ("AMT", "American Tower Corp.", "Real Estate", "Tower REIT", "NYSE"),
        ("CCI", "Crown Castle Inc.", "Real Estate", "Tower REIT", "NYSE"),
        ("EQIX", "Equinix Inc.", "Real Estate", "Data Center REIT", "NASDAQ"),
        ("SPG", "Simon Property Group", "Real Estate", "Retail REIT", "NYSE"),
    ]

    # NASDAQ 100 추가 종목 (S&P 500과 중복 제외)
    NASDAQ_100_EXTRA = [
        ("MELI", "MercadoLibre Inc.", "Consumer Discretionary", "E-Commerce", "NASDAQ"),
        ("PANW", "Palo Alto Networks", "Technology", "Cybersecurity", "NASDAQ"),
        ("LRCX", "Lam Research Corp.", "Technology", "Semiconductors", "NASDAQ"),
        ("AMAT", "Applied Materials", "Technology", "Semiconductors", "NASDAQ"),
        ("KLAC", "KLA Corporation", "Technology", "Semiconductors", "NASDAQ"),
        ("SNPS", "Synopsys Inc.", "Technology", "Software", "NASDAQ"),
        ("CDNS", "Cadence Design Systems", "Technology", "Software", "NASDAQ"),
        ("MRVL", "Marvell Technology", "Technology", "Semiconductors", "NASDAQ"),
        ("FTNT", "Fortinet Inc.", "Technology", "Cybersecurity", "NASDAQ"),
        ("WDAY", "Workday Inc.", "Technology", "Software", "NASDAQ"),
        ("TEAM", "Atlassian Corporation", "Technology", "Software", "NASDAQ"),
        ("ZS", "Zscaler Inc.", "Technology", "Cybersecurity", "NASDAQ"),
        ("DDOG", "Datadog Inc.", "Technology", "Software", "NASDAQ"),
        ("CRWD", "CrowdStrike Holdings", "Technology", "Cybersecurity", "NASDAQ"),
        ("ABNB", "Airbnb Inc.", "Consumer Discretionary", "Travel", "NASDAQ"),
    ]

    def __init__(self, cache_dir: str = None):
        """
        Args:
            cache_dir: 캐시 디렉토리 경로
        """
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "universe"
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_sp500_symbols(self) -> List[USStock]:
        """
        S&P 500 구성종목 조회

        Returns:
            USStock 리스트
        """
        stocks = []
        for item in self.SP500_TOP_100:
            symbol, name, sector, industry, exchange = item
            stocks.append(USStock(
                symbol=symbol,
                name=name,
                sector=sector,
                industry=industry,
                exchange=exchange,
                market_cap=0  # 별도 조회 필요
            ))
        return stocks

    def get_nasdaq100_symbols(self) -> List[USStock]:
        """
        NASDAQ 100 구성종목 조회 (S&P 500 포함)

        Returns:
            USStock 리스트
        """
        stocks = self.get_sp500_symbols()
        existing = {s.symbol for s in stocks}

        for item in self.NASDAQ_100_EXTRA:
            symbol, name, sector, industry, exchange = item
            if symbol not in existing:
                stocks.append(USStock(
                    symbol=symbol,
                    name=name,
                    sector=sector,
                    industry=industry,
                    exchange=exchange,
                    market_cap=0
                ))

        return stocks

    def fetch_sp500_from_wikipedia(self) -> List[USStock]:
        """
        Wikipedia에서 최신 S&P 500 구성종목 파싱

        Returns:
            USStock 리스트
        """
        try:
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            tables = pd.read_html(url)
            df = tables[0]

            stocks = []
            for _, row in df.iterrows():
                symbol = str(row['Symbol']).replace('.', '-')  # BRK.B -> BRK-B
                stocks.append(USStock(
                    symbol=symbol,
                    name=row.get('Security', ''),
                    sector=row.get('GICS Sector', ''),
                    industry=row.get('GICS Sub-Industry', ''),
                    exchange='NYSE' if 'NYSE' in str(row.get('CIK', '')) else 'NASDAQ',
                    market_cap=0
                ))

            # 캐시 저장
            self._save_cache('sp500', stocks)
            logger.info(f"S&P 500 종목 {len(stocks)}개 로드 완료 (Wikipedia)")
            return stocks

        except Exception as e:
            logger.warning(f"Wikipedia에서 S&P 500 로드 실패: {e}")
            # 폴백: 내장 목록 사용
            return self.get_sp500_symbols()

    def _save_cache(self, name: str, stocks: List[USStock]):
        """캐시 저장"""
        cache_file = os.path.join(self.cache_dir, f"{name}.json")
        data = {
            "updated_at": datetime.now().isoformat(),
            "stocks": [asdict(s) for s in stocks]
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_cache(self, name: str, max_age_days: int = 7) -> Optional[List[USStock]]:
        """캐시 로드"""
        cache_file = os.path.join(self.cache_dir, f"{name}.json")
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 캐시 만료 체크
            updated_at = datetime.fromisoformat(data["updated_at"])
            if datetime.now() - updated_at > timedelta(days=max_age_days):
                return None

            stocks = [USStock(**s) for s in data["stocks"]]
            return stocks

        except Exception as e:
            logger.warning(f"캐시 로드 실패: {e}")
            return None

    def build_universe(
        self,
        universe_type: str = "sp500",
        size: int = 100
    ) -> List[USStock]:
        """
        투자 유니버스 구성

        Args:
            universe_type: "sp500", "nasdaq100", "sp500_full"
            size: 반환할 종목 수

        Returns:
            USStock 리스트
        """
        # 캐시 확인
        cached = self._load_cache(universe_type)
        if cached:
            logger.info(f"캐시에서 {universe_type} 로드: {len(cached)}개 종목")
            return cached[:size]

        # 유니버스 타입별 처리
        if universe_type == "sp500":
            stocks = self.get_sp500_symbols()
        elif universe_type == "nasdaq100":
            stocks = self.get_nasdaq100_symbols()
        elif universe_type == "sp500_full":
            stocks = self.fetch_sp500_from_wikipedia()
        else:
            stocks = self.get_sp500_symbols()

        # 캐시 저장
        self._save_cache(universe_type, stocks)

        return stocks[:size]

    def get_exchange_code(self, symbol: str) -> str:
        """
        종목의 거래소 코드 반환

        Args:
            symbol: 종목 심볼

        Returns:
            거래소 코드 (NAS, NYS, AMS)
        """
        # 내장 목록에서 확인
        for item in self.SP500_TOP_100 + self.NASDAQ_100_EXTRA:
            if item[0] == symbol:
                exchange = item[4]
                return "NAS" if exchange == "NASDAQ" else "NYS"

        # 기본값: NASDAQ
        return "NAS"


class USDataCollector:
    """미국 주식 데이터 수집기 (KIS API + Yahoo Finance)"""

    def __init__(self, kis_client=None):
        """
        Args:
            kis_client: KISUSClient 인스턴스 (없으면 생성)
        """
        self.kis_client = kis_client
        self.universe_builder = USUniverseBuilder()

    def _get_client(self):
        """클라이언트 lazy 초기화"""
        if self.kis_client is None:
            from src.api.kis_us_client import get_us_client
            self.kis_client = get_us_client(is_virtual=True)
        return self.kis_client

    def get_price_data(
        self,
        symbol: str,
        days: int = 100
    ) -> pd.DataFrame:
        """
        종목의 가격 데이터 조회 (일봉)

        Args:
            symbol: 종목 심볼
            days: 조회 일수

        Returns:
            DataFrame (date, open, high, low, close, volume)
        """
        client = self._get_client()
        exchange = self.universe_builder.get_exchange_code(symbol)

        try:
            candles = client.get_daily_price(
                symbol=symbol,
                exchange=exchange,
                count=days
            )

            if not candles:
                return pd.DataFrame()

            df = pd.DataFrame([{
                'date': c.date,
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume
            } for c in candles])

            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

            return df

        except Exception as e:
            logger.warning(f"가격 데이터 조회 실패 ({symbol}): {e}")
            return pd.DataFrame()

    def get_price_data_yahoo(
        self,
        symbol: str,
        days: int = 100
    ) -> pd.DataFrame:
        """
        Yahoo Finance에서 가격 데이터 조회 (KIS API 백업용)

        Args:
            symbol: 종목 심볼
            days: 조회 일수

        Returns:
            DataFrame
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            df = ticker.history(period=f"{days}d")

            if df.empty:
                return pd.DataFrame()

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={'index': 'date'})

            return df[['date', 'open', 'high', 'low', 'close', 'volume']]

        except ImportError:
            logger.warning("yfinance 라이브러리가 설치되지 않았습니다. pip install yfinance")
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"Yahoo Finance 조회 실패 ({symbol}): {e}")
            return pd.DataFrame()

    def get_fundamental_data(self, symbol: str) -> Dict[str, Any]:
        """
        종목의 펀더멘털 데이터 조회

        Args:
            symbol: 종목 심볼

        Returns:
            펀더멘털 데이터 딕셔너리
        """
        client = self._get_client()
        exchange = self.universe_builder.get_exchange_code(symbol)

        try:
            detail = client.get_stock_price_detail(symbol, exchange)
            return detail
        except Exception as e:
            logger.warning(f"펀더멘털 데이터 조회 실패 ({symbol}): {e}")
            return {}

    def get_fundamental_data_yahoo(self, symbol: str) -> Dict[str, Any]:
        """
        Yahoo Finance에서 펀더멘털 데이터 조회

        Args:
            symbol: 종목 심볼

        Returns:
            펀더멘털 데이터 딕셔너리
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "name": info.get("shortName", ""),
                "price": info.get("currentPrice", 0),
                "per": info.get("trailingPE", 0),
                "pbr": info.get("priceToBook", 0),
                "eps": info.get("trailingEps", 0),
                "roe": info.get("returnOnEquity", 0) * 100 if info.get("returnOnEquity") else 0,
                "market_cap": info.get("marketCap", 0) / 1e9,  # 십억 달러
                "dividend_yield": info.get("dividendYield", 0) * 100 if info.get("dividendYield") else 0,
                "beta": info.get("beta", 1.0),
                "high_52w": info.get("fiftyTwoWeekHigh", 0),
                "low_52w": info.get("fiftyTwoWeekLow", 0),
                "avg_volume": info.get("averageVolume", 0)
            }

        except ImportError:
            logger.warning("yfinance 라이브러리가 설치되지 않았습니다.")
            return {}
        except Exception as e:
            logger.warning(f"Yahoo Finance 펀더멘털 조회 실패 ({symbol}): {e}")
            return {}


# ========== 편의 함수 ==========

def get_universe(
    universe_type: str = "sp500",
    size: int = 100
) -> List[USStock]:
    """유니버스 조회"""
    builder = USUniverseBuilder()
    return builder.build_universe(universe_type, size)


def get_sp500_symbols() -> List[str]:
    """S&P 500 심볼 목록 반환"""
    builder = USUniverseBuilder()
    stocks = builder.get_sp500_symbols()
    return [s.symbol for s in stocks]
