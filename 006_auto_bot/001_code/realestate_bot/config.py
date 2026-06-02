"""주간 서울 아파트 시장 흐름 다이제스트 봇 설정."""
import os

# 서울 25개 자치구 — 법정동 시군구 5자리 코드 (MOLIT region_code)
# 마포(11440)는 get_region_code로 검증됨. 나머지는 표준 자치구 코드.
SEOUL_GU = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200",
    "광진구": "11215", "동대문구": "11230", "중랑구": "11260", "성북구": "11290",
    "강북구": "11305", "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470", "강서구": "11500",
    "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}

BASELINE_MONTHS = 36          # 신고가 baseline 윈도우 → "최근 3년"
NUM_OF_ROWS = 1000            # 월 거래 누락 방지
NEW_BUILD_MAX_AGE = 5         # build_year 기준 신축 (현재연도 - build_year <= 5)
DIRECT_DEAL_SPIKE_PCT = 30.0  # 직거래 비중 이 이상이면 왜곡 주의 플래그
VOLUME_TREND_MONTHS = 12      # 월별 거래량 시계열 길이

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "realestate", "molit.db")

# 루트 .mcp.json (001_code 기준 ../../../.mcp.json). env로 override 가능.
MCP_CONFIG_PATH = os.getenv(
    "REALESTATE_MCP_CONFIG",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".mcp.json")),
)

# 출력
REALESTATE_BLOGGER_BLOG_ID = os.getenv("REALESTATE_BLOGGER_BLOG_ID", "9115231004981625966")  # OgusInvest
SCHEDULE_DAY = "saturday"
SCHEDULE_TIME = "01:00"
