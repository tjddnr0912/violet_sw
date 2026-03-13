"""Tile definitions, data sources, update intervals, RSS URLs."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5002"))

# --- Update Intervals (seconds) ---
TIER1_INTERVAL = 30    # S&P 500, NASDAQ, Dow, Bitcoin
TIER2_INTERVAL = 60    # VIX, 10Y, DXY, Gold, Oil, FX, EU/Asia
TIER3_INTERVAL = 120   # Sector heatmap, Top movers
TIER4_INTERVAL = 600   # News RSS + AI summary (10min, Gemini free tier 절약)
TIER5_INTERVAL = 600   # Fear & Greed, Market Breadth
OFF_HOURS_INTERVAL = 300  # All tickers during off-hours

# --- yfinance Ticker Groups ---
TIER1_TICKERS = ["^GSPC", "^IXIC", "^DJI", "BTC-USD"]

# Index → Futures mapping (for off-hours display)
INDEX_FUTURES_MAP = {
    "^GSPC": "ES=F",   # S&P 500 E-mini
    "^IXIC": "NQ=F",   # NASDAQ 100 E-mini
    "^DJI": "YM=F",    # Dow Jones E-mini
}

TIER2_TICKERS = [
    "^VIX", "^TNX", "DX-Y.NYB",   # Volatility, Treasury, Dollar
    "GC=F", "CL=F",                # Gold, Oil
    "EURUSD=X", "JPY=X", "KRW=X", # FX
]

EU_TICKERS = ["^FTSE", "^GDAXI", "^FCHI"]
ASIA_TICKERS = ["^N225", "000001.SS", "^KS11", "^HSI"]

SECTOR_ETFS = {
    "XLK": "Tech", "XLF": "Financials", "XLV": "Healthcare",
    "XLY": "Discretionary", "XLP": "Staples", "XLE": "Energy",
    "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
    "XLC": "Comm Svcs", "XLU": "Utilities",
}

# --- New Row 4 Tiles ---
YIELD_TICKERS = ["^IRX", "^FVX", "^TNX", "^TYX"]  # 3M, 5Y, 10Y, 30Y
# --- Watchlist (replaced Crypto tile) ---
WATCHLIST_FIXED_TICKERS = ["O", "SCHD", "QQQ", "GOOGL", "SPY"]
WATCHLIST_DYNAMIC_COUNT = 3          # rotating high-volume slots
WATCHLIST_DYNAMIC_REFRESH = 300      # re-evaluate dynamic picks every 5min
COMMODITY_TICKERS = ["SI=F", "HG=F", "NG=F"]  # Silver, Copper, NatGas

# --- Tile Definitions ---
# grid format: "row_start / col_start / row_end / col_end"
TILES = {
    # Row 1: Major US index charts (2-col span each)
    "sp500":     {"name": "S&P 500",  "ticker": "^GSPC",  "type": "chart", "grid": "1/1/2/3"},
    "nasdaq":    {"name": "NASDAQ",   "ticker": "^IXIC",  "type": "chart", "grid": "1/3/2/5"},
    "dow":       {"name": "Dow Jones","ticker": "^DJI",   "type": "chart", "grid": "1/5/2/7"},

    # Row 2: Key metrics (1x1 each)
    "vix":       {"name": "VIX",       "ticker": "^VIX",      "type": "numeric", "grid": "2/1/3/2"},
    "treasury":  {"name": "10Y Yield", "ticker": "^TNX",      "type": "numeric", "grid": "2/2/3/3"},
    "dxy":       {"name": "DXY",       "ticker": "DX-Y.NYB",  "type": "numeric", "grid": "2/3/3/4"},
    "gold":      {"name": "Gold",      "ticker": "GC=F",      "type": "numeric", "grid": "2/4/3/5"},
    "oil":       {"name": "WTI Oil",   "ticker": "CL=F",      "type": "numeric", "grid": "2/5/3/6"},
    "bitcoin":   {"name": "Bitcoin",   "ticker": "BTC-USD",   "type": "numeric", "grid": "2/6/3/7"},

    # Row 3: Analysis + Global
    "sector":    {"name": "Sectors",       "type": "heatmap",  "grid": "3/1/4/3"},
    "movers":    {"name": "Top Movers",    "type": "movers",   "grid": "3/3/4/4"},
    "feargreed": {"name": "Fear & Greed",  "type": "gauge",    "grid": "3/4/4/5"},
    "europe":    {"name": "Europe",        "type": "region",   "grid": "3/5/4/6"},
    "asia":      {"name": "Asia",          "type": "region",   "grid": "3/6/4/7"},

    # Row 4: FX + Breadth + YieldCurve + Crypto + Commodities + News
    "fx":           {"name": "FX Rates",      "type": "fx",           "grid": "4/1/5/2"},
    "breadth":      {"name": "Mkt Breadth",   "type": "breadth",      "grid": "4/2/5/3"},
    "yieldcurve":   {"name": "Yield Curve",   "type": "yieldcurve",   "grid": "4/3/5/4"},
    "watchlist":     {"name": "Watchlist",      "type": "watchlist",    "grid": "4/4/5/5"},
    "commodities":  {"name": "Commodities",   "type": "commodities",  "grid": "4/5/5/6"},
    "news_compact": {"name": "News Feed",     "type": "news_compact", "grid": "4/6/5/7"},
}

# --- Ticker to Tile ID mapping ---
TICKER_TO_TILE = {}
for tile_id, tile_cfg in TILES.items():
    if "ticker" in tile_cfg:
        TICKER_TO_TILE[tile_cfg["ticker"]] = tile_id

# --- RSS Sources ---
RSS_SOURCES = [
    {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "source": "CNBC", "lang": "EN"},
    {"url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "source": "WSJ", "lang": "EN"},
    {"url": "https://feeds.bloomberg.com/markets/news.rss", "source": "Bloomberg", "lang": "EN"},
    {"url": "https://feeds.marketwatch.com/marketwatch/bulletins", "source": "MarketWatch", "lang": "EN"},
    {"url": "https://seekingalpha.com/market_currents.xml", "source": "SeekingAlpha", "lang": "EN"},
    {"url": "https://www.yna.co.kr/rss/economy.xml", "source": "연합뉴스", "lang": "KR"},
    {"url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSSREADER", "source": "SBS", "lang": "KR"},
    {"url": "https://www.hankyung.com/feed/all-news", "source": "한경", "lang": "KR"},
    {"url": "https://www.mk.co.kr/rss/30000001/", "source": "매경", "lang": "KR"},
    {"url": "https://www.nhk.or.jp/rss/news/cat4.xml", "source": "NHK", "lang": "JP"},
    {"url": "https://news.google.com/rss/search?q=china+economy+OR+china+market&hl=en&gl=US&ceid=US:en", "source": "Google CN", "lang": "EN"},
]

# --- Breaking News Keywords ---
BREAKING_KEYWORDS = [
    "FOMC", "rate cut", "rate hike", "crash", "emergency",
    "recession", "war", "default", "bankruptcy", "circuit breaker",
    "fed", "tariff", "sanctions", "shutdown", "금리", "긴급",
    "폭락", "전쟁", "파산", "서킷브레이커",
]

# --- Gemini Config ---
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_BATCH_SIZE = 5
GEMINI_TIMEOUT = 30  # seconds per batch
GEMINI_RPM_LIMIT = 4  # max calls per minute

# --- Market Hours (timezone, open_hour, open_min, close_hour, close_min) ---
MARKET_HOURS = {
    "US": {"tz": "US/Eastern",       "open": (9, 30),  "close": (16, 0)},
    "EU": {"tz": "Europe/Berlin",    "open": (8, 0),   "close": (16, 30)},
    "JP": {"tz": "Asia/Tokyo",       "open": (9, 0),   "close": (15, 0)},
    "CN": {"tz": "Asia/Shanghai",    "open": (9, 30),  "close": (15, 0)},
    "KR": {"tz": "Asia/Seoul",       "open": (9, 0),   "close": (15, 30)},
}

# --- Top Movers: S&P 500 sample tickers for scanning ---
TOP_MOVERS_TICKERS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "HD", "CVX",
    "MRK", "ABBV", "KO", "PEP", "COST", "AVGO", "LLY", "TMO", "MCD",
    "CSCO", "ACN", "ABT", "DHR", "NEE", "NKE", "ORCL", "CRM", "AMD",
    "INTC", "QCOM", "TXN", "NFLX", "ADBE", "BA", "GS", "CAT", "DIS",
]

# --- Korean KOSPI Large-cap Tickers for Alert Scanning ---
KR_ALERT_TICKERS = [
    "005930.KS", "000660.KS", "373220.KS", "207940.KS", "005380.KS",
    "006400.KS", "035420.KS", "000270.KS", "068270.KS", "035720.KS",
    "105560.KS", "055550.KS", "003670.KS", "012330.KS", "051910.KS",
]

KR_TICKER_NAMES = {
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스", "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오", "005380.KS": "현대차", "006400.KS": "삼성SDI",
    "035420.KS": "NAVER", "000270.KS": "기아", "068270.KS": "셀트리온",
    "035720.KS": "카카오", "105560.KS": "KB금융", "055550.KS": "신한지주",
    "003670.KS": "POSCO", "012330.KS": "현대모비스", "051910.KS": "LG화학",
}

# --- Alert Thresholds ---
ALERT_DAILY_PREFILTER_PCT = 2.0   # Phase 1: daily change filter
ALERT_1H_SURGE_PCT = 3.0          # Phase 2: 1-hour surge/drop threshold
ALERT_COOLDOWN_SECONDS = 900      # 15min cooldown per ticker
ALERT_MAX_ACTIVE = 10             # Max active alerts
ALERT_SCAN_INTERVAL = 120         # Scan interval (seconds)
