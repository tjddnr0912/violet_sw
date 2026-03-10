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
CRYPTO_TICKERS = ["ETH-USD", "SOL-USD", "XRP-USD"]
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
    "crypto":       {"name": "Crypto",        "type": "crypto",       "grid": "4/4/5/5"},
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
    {"url": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0JYcG9MVU5PR2dKRFRpZ0FQAQ?hl=zh-CN&gl=CN&ceid=CN:zh-Hans", "source": "Google CN", "lang": "CN"},
]

# --- Breaking News Keywords ---
BREAKING_KEYWORDS = [
    "FOMC", "rate cut", "rate hike", "crash", "emergency",
    "recession", "war", "default", "bankruptcy", "circuit breaker",
    "fed", "tariff", "sanctions", "shutdown", "금리", "긴급",
    "폭락", "전쟁", "파산", "서킷브레이커",
]

# --- Gemini Config ---
GEMINI_MODEL = "gemini-2.5-flash"
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
