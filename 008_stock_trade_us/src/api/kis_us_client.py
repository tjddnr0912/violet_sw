"""
한국투자증권 API 클라이언트 - 미국 주식
- REST API 호출 기본 클래스
- 미국주식 시세/주문/잔고 조회
"""

import time
import logging
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from requests.exceptions import Timeout, ConnectionError, RequestException

from .kis_auth import KISAuth, get_auth
from .kis_client import (
    KISAPIError, KISTimeoutError, KISConnectionError,
    KISHTTPError, KISRateLimitError, KISBusinessError,
    OrderResult
)

logger = logging.getLogger(__name__)


# ========== 미국 주식 데이터 클래스 ==========

@dataclass
class USStockPrice:
    """미국 주식 현재가 정보"""
    symbol: str           # 종목코드 (예: AAPL)
    name: str             # 종목명
    price: float          # 현재가 (USD)
    change: float         # 전일대비
    change_rate: float    # 등락률 (%)
    volume: int           # 거래량
    high: float           # 고가
    low: float            # 저가
    open: float           # 시가
    prev_close: float     # 전일종가
    exchange: str         # 거래소 (NYSE, NASD, AMEX)


@dataclass
class USStockBalance:
    """미국 주식 보유 정보"""
    symbol: str           # 종목코드
    name: str             # 종목명
    qty: int              # 보유수량
    avg_price: float      # 평균단가 (USD)
    current_price: float  # 현재가 (USD)
    profit: float         # 평가손익 (USD)
    profit_rate: float    # 수익률 (%)
    exchange: str         # 거래소


@dataclass
class USDailyCandle:
    """미국 주식 일봉 데이터"""
    date: str             # 날짜 (YYYYMMDD)
    open: float           # 시가
    high: float           # 고가
    low: float            # 저가
    close: float          # 종가
    volume: int           # 거래량


# ========== 거래소 코드 ==========

class USExchange:
    """미국 거래소 코드"""
    NYSE = "NYS"   # 뉴욕증권거래소
    NASDAQ = "NAS"  # 나스닥
    AMEX = "AMS"   # 아멕스


# ========== 시세 지연 안내 ==========
#
# ⚠️ 미국 주식 시세는 기본적으로 15분 지연됩니다!
#
# 실시간 시세 조건:
# 1. 당월 또는 전월 해외주식 거래 실적 1회 이상
# 2. KIS 앱/HTS에서 실시간 시세 서비스 신청
# 3. 모의투자 계좌는 실시간 시세 미지원 가능성 높음
#
# 퀀트 전략 영향:
# - 스크리닝/리밸런싱: 영향 없음 (일봉 기준)
# - 손절/익절: 15분 지연 감안 필요
#

    # KIS API에서 사용하는 거래소 코드
    EXCHANGE_MAP = {
        "NYS": "NYSE",
        "NAS": "NASDAQ",
        "AMS": "AMEX",
        "NYSE": "NYS",
        "NASDAQ": "NAS",
        "NASD": "NAS",
        "AMEX": "AMS"
    }

    @classmethod
    def normalize(cls, exchange: str) -> str:
        """거래소 코드 정규화"""
        return cls.EXCHANGE_MAP.get(exchange.upper(), exchange.upper())


class KISUSClient:
    """한국투자증권 미국 주식 API 클라이언트"""

    # API 설정
    DEFAULT_TIMEOUT = 15  # 초 (해외 API는 응답이 느릴 수 있음)
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # 초

    def __init__(self, is_virtual: bool = True):
        """
        Args:
            is_virtual: True=모의투자, False=실전투자
        """
        self.auth = get_auth(is_virtual)
        self.is_virtual = is_virtual

    def _request(
        self,
        method: str,
        endpoint: str,
        tr_id: str,
        params: Optional[Dict] = None,
        body: Optional[Dict] = None,
        timeout: int = None,
        retries: int = None
    ) -> Dict[str, Any]:
        """
        API 요청 공통 메서드 (with retry & error handling)
        """
        url = f"{self.auth.base_url}{endpoint}"
        headers = self.auth.get_headers(tr_id)
        timeout = timeout or self.DEFAULT_TIMEOUT
        retries = retries if retries is not None else self.MAX_RETRIES

        last_error = None

        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = requests.get(
                        url, headers=headers, params=params, timeout=timeout
                    )
                else:
                    response = requests.post(
                        url, headers=headers, json=body, timeout=timeout
                    )

                # HTTP 상태 코드 체크
                if response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"API 요청 제한 초과. {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                    continue

                if response.status_code >= 400:
                    user_messages = {
                        400: "잘못된 요청입니다. 파라미터를 확인하세요.",
                        401: "API 인증 실패. 앱키와 시크릿을 확인하세요.",
                        403: "접근 권한이 없습니다. 해외주식 API 권한을 확인하세요.",
                        404: "요청한 리소스를 찾을 수 없습니다.",
                        429: "API 요청 제한입니다. 잠시 후 다시 시도하세요.",
                        500: "증권사 서버 내부 오류입니다.",
                        502: "증권사 서버 연결 오류입니다.",
                        503: "증권사 서버 점검 중입니다.",
                        504: "증권사 서버 응답 시간 초과입니다."
                    }
                    user_msg = user_messages.get(
                        response.status_code,
                        f"서버 오류가 발생했습니다 (코드: {response.status_code})"
                    )
                    logger.error(
                        f"HTTP 에러 [{response.status_code}] {endpoint}: {response.text[:200]}"
                    )
                    raise KISHTTPError(user_msg, response.status_code)

                data = response.json()

                # KIS API 응답 코드 검증
                rt_cd = data.get("rt_cd", "0")
                if rt_cd != "0":
                    error_msg = data.get("msg1", "Unknown error")
                    logger.warning(f"KIS API 오류 [{rt_cd}]: {error_msg}")
                    raise KISBusinessError(error_msg, rt_cd, data)

                return data

            except Timeout as e:
                last_error = KISTimeoutError(f"API 호출 타임아웃: {endpoint}")
                logger.warning(f"타임아웃 (시도 {attempt + 1}/{retries}): {endpoint}")

            except ConnectionError as e:
                last_error = KISConnectionError(f"네트워크 연결 오류: {e}")
                logger.warning(f"연결 오류 (시도 {attempt + 1}/{retries}): {e}")

            except KISHTTPError:
                raise

            except KISBusinessError:
                raise

            except RequestException as e:
                last_error = KISAPIError(f"요청 오류: {e}")
                logger.warning(f"요청 오류 (시도 {attempt + 1}/{retries}): {e}")

            if attempt < retries - 1:
                wait_time = self.RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)

        if last_error:
            logger.error(f"API 호출 최종 실패: {endpoint} - {last_error}")
            raise last_error

        raise KISAPIError(f"API 호출 실패: {endpoint}")

    # ========== 시세 조회 ==========

    def get_stock_price(
        self,
        symbol: str,
        exchange: str = "NAS"
    ) -> USStockPrice:
        """
        미국주식 현재가 조회

        Args:
            symbol: 종목코드 (예: "AAPL", "TSLA")
            exchange: 거래소 코드 (NAS: 나스닥, NYS: 뉴욕, AMS: 아멕스)

        Returns:
            USStockPrice 객체
        """
        tr_id = "HHDFS00000300"
        exchange = USExchange.normalize(exchange)

        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol.upper()
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/overseas-price/v1/quotations/price",
            tr_id=tr_id,
            params=params
        )

        output = data.get("output", {})

        return USStockPrice(
            symbol=symbol.upper(),
            name=output.get("rsym", ""),
            price=float(output.get("last", 0) or 0),
            change=float(output.get("diff", 0) or 0),
            change_rate=float(output.get("rate", 0) or 0),
            volume=int(output.get("tvol", 0) or 0),
            high=float(output.get("high", 0) or 0),
            low=float(output.get("low", 0) or 0),
            open=float(output.get("open", 0) or 0),
            prev_close=float(output.get("base", 0) or 0),
            exchange=exchange
        )

    def get_stock_price_detail(
        self,
        symbol: str,
        exchange: str = "NAS"
    ) -> Dict[str, Any]:
        """
        미국주식 현재가 상세 조회 (PER, 52주 고저 등)

        Args:
            symbol: 종목코드
            exchange: 거래소 코드

        Returns:
            상세 정보 딕셔너리
        """
        tr_id = "HHDFS76200200"
        exchange = USExchange.normalize(exchange)

        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol.upper()
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/overseas-price/v1/quotations/price-detail",
            tr_id=tr_id,
            params=params
        )

        output = data.get("output", {})

        return {
            "symbol": symbol.upper(),
            "name": output.get("rsym", ""),
            "price": float(output.get("last", 0) or 0),
            "change": float(output.get("diff", 0) or 0),
            "change_rate": float(output.get("rate", 0) or 0),
            "volume": int(output.get("tvol", 0) or 0),
            "per": float(output.get("perx", 0) or 0),
            "eps": float(output.get("epsx", 0) or 0),
            "pbr": float(output.get("pbrx", 0) or 0),
            "high_52w": float(output.get("h52p", 0) or 0),
            "low_52w": float(output.get("l52p", 0) or 0),
            "market_cap": float(output.get("tomv", 0) or 0),  # 시가총액 (억 달러)
            "shares": int(output.get("shar", 0) or 0),
            "exchange": exchange
        }

    def get_daily_price(
        self,
        symbol: str,
        exchange: str = "NAS",
        period: str = "0",
        count: int = 100,
        start_date: str = "",
        end_date: str = ""
    ) -> List[USDailyCandle]:
        """
        미국주식 기간별 시세 조회 (일/주/월봉)

        Args:
            symbol: 종목코드
            exchange: 거래소 코드
            period: 기간 ("0": 일봉, "1": 주봉, "2": 월봉)
            count: 조회 개수 (최대 100)
            start_date: 시작일 (YYYYMMDD, 생략시 현재)
            end_date: 종료일 (YYYYMMDD, 생략시 현재)

        Returns:
            USDailyCandle 리스트
        """
        tr_id = "HHDFS76240000"
        exchange = USExchange.normalize(exchange)

        # 날짜가 없으면 현재 날짜 사용
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            # 100일 전
            from datetime import timedelta
            start_date = (datetime.now() - timedelta(days=count + 50)).strftime("%Y%m%d")

        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": symbol.upper(),
            "GUBN": period,
            "BYMD": end_date,
            "MODP": "1"  # 수정주가 적용
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/overseas-price/v1/quotations/dailyprice",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output2", [])[:count]:
            if not item.get("xymd"):
                continue
            result.append(USDailyCandle(
                date=item.get("xymd", ""),
                open=float(item.get("open", 0) or 0),
                high=float(item.get("high", 0) or 0),
                low=float(item.get("low", 0) or 0),
                close=float(item.get("clos", 0) or 0),
                volume=int(item.get("tvol", 0) or 0)
            ))

        return result

    # ========== 주문 ==========

    def _validate_us_order_params(
        self,
        symbol: str,
        qty: int,
        price: float,
        order_type: str
    ) -> tuple:
        """
        미국주식 주문 파라미터 검증

        Returns:
            (유효여부, 에러메시지)
        """
        import re

        # 종목코드 검증 (1-5자리 영문)
        if not symbol or not re.match(r'^[A-Z]{1,5}$', symbol.upper()):
            return False, f"올바른 종목코드를 입력하세요 (1-5자리 영문): {symbol}"

        # 수량 검증
        if not isinstance(qty, int) or qty < 1:
            return False, f"주문수량은 1 이상의 정수여야 합니다: {qty}"

        # 가격 검증 (시장가일 때도 0 이상)
        if price < 0:
            return False, f"주문가격은 0 이상이어야 합니다: {price}"

        # 주문유형 검증
        valid_order_types = ["00", "32"]  # 00: 지정가, 32: MOC (장마감시 시장가)
        if order_type not in valid_order_types:
            return False, f"주문유형은 00(지정가) 또는 32(MOC)이어야 합니다: {order_type}"

        return True, ""

    def buy_stock(
        self,
        symbol: str,
        qty: int,
        price: float = 0,
        exchange: str = "NAS",
        order_type: str = "00"
    ) -> OrderResult:
        """
        미국주식 매수 주문

        Args:
            symbol: 종목코드 (예: "AAPL")
            qty: 주문수량
            price: 주문가격 (USD)
            exchange: 거래소 코드
            order_type: 주문유형 (00: 지정가, 32: MOC)

        Returns:
            OrderResult 객체
        """
        # 파라미터 검증
        is_valid, error_msg = self._validate_us_order_params(symbol, qty, price, order_type)
        if not is_valid:
            return OrderResult(success=False, order_no="", message=error_msg)

        # 모의투자/실전투자 거래ID
        tr_id = "VTTT1002U" if self.is_virtual else "TTTT1002U"
        exchange = USExchange.normalize(exchange)

        acct_no, acct_suffix = self.auth.get_account_info()

        body = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol.upper(),
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": str(price),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": order_type
        }

        try:
            data = self._request(
                method="POST",
                endpoint="/uapi/overseas-stock/v1/trading/order",
                tr_id=tr_id,
                body=body
            )

            output = data.get("output", {})
            rt_cd = data.get("rt_cd", "1")

            return OrderResult(
                success=(rt_cd == "0"),
                order_no=output.get("ODNO", ""),
                message=data.get("msg1", "")
            )

        except Exception as e:
            return OrderResult(
                success=False,
                order_no="",
                message=str(e)
            )

    def sell_stock(
        self,
        symbol: str,
        qty: int,
        price: float = 0,
        exchange: str = "NAS",
        order_type: str = "00"
    ) -> OrderResult:
        """
        미국주식 매도 주문

        Args:
            symbol: 종목코드
            qty: 주문수량
            price: 주문가격 (USD)
            exchange: 거래소 코드
            order_type: 주문유형

        Returns:
            OrderResult 객체
        """
        # 파라미터 검증
        is_valid, error_msg = self._validate_us_order_params(symbol, qty, price, order_type)
        if not is_valid:
            return OrderResult(success=False, order_no="", message=error_msg)

        # 모의투자/실전투자 거래ID (매도)
        tr_id = "VTTT1006U" if self.is_virtual else "TTTT1006U"
        exchange = USExchange.normalize(exchange)

        acct_no, acct_suffix = self.auth.get_account_info()

        body = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "OVRS_EXCG_CD": exchange,
            "PDNO": symbol.upper(),
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": str(price),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": order_type
        }

        try:
            data = self._request(
                method="POST",
                endpoint="/uapi/overseas-stock/v1/trading/order",
                tr_id=tr_id,
                body=body
            )

            output = data.get("output", {})
            rt_cd = data.get("rt_cd", "1")

            return OrderResult(
                success=(rt_cd == "0"),
                order_no=output.get("ODNO", ""),
                message=data.get("msg1", "")
            )

        except Exception as e:
            return OrderResult(
                success=False,
                order_no="",
                message=str(e)
            )

    # ========== 잔고 조회 ==========

    def get_balance(self) -> Dict[str, Any]:
        """
        미국주식 계좌 잔고 조회

        Returns:
            잔고 정보 딕셔너리
        """
        # 모의투자/실전투자 거래ID
        tr_id = "VTTS3012R" if self.is_virtual else "TTTS3012R"

        acct_no, acct_suffix = self.auth.get_account_info()

        params = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "OVRS_EXCG_CD": "NASD",  # 전체 조회
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/overseas-stock/v1/trading/inquire-balance",
            tr_id=tr_id,
            params=params
        )

        # 보유종목 리스트
        stocks = []
        for item in data.get("output1", []):
            if int(item.get("ovrs_cblc_qty", 0)) > 0:
                stocks.append(USStockBalance(
                    symbol=item.get("ovrs_pdno", ""),
                    name=item.get("ovrs_item_name", ""),
                    qty=int(item.get("ovrs_cblc_qty", 0)),
                    avg_price=float(item.get("pchs_avg_pric", 0) or 0),
                    current_price=float(item.get("now_pric2", 0) or 0),
                    profit=float(item.get("frcr_evlu_pfls_amt", 0) or 0),
                    profit_rate=float(item.get("evlu_pfls_rt", 0) or 0),
                    exchange=item.get("ovrs_excg_cd", "")
                ))

        # 계좌 요약
        summary = data.get("output2", {})

        return {
            "stocks": stocks,
            "total_eval": float(summary.get("tot_evlu_pfls_amt", 0) or 0),
            "total_profit": float(summary.get("ovrs_tot_pfls", 0) or 0),
            "cash_usd": float(summary.get("frcr_pchs_amt1", 0) or 0),
            "cash_krw": float(summary.get("frcr_pchs_amt2", 0) or 0),
            "exchange_rate": float(summary.get("frst_bltn_exrt", 0) or 0)
        }

    def get_order_history(self) -> list:
        """
        미국주식 당일 주문내역 조회

        Returns:
            주문내역 리스트
        """
        tr_id = "VTTS3035R" if self.is_virtual else "TTTS3035R"

        acct_no, acct_suffix = self.auth.get_account_info()

        params = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "PDNO": "%",
            "ORD_STRT_DT": "",
            "ORD_END_DT": "",
            "SLL_BUY_DVSN": "00",  # 전체
            "CCLD_NCCS_DVSN": "00",
            "OVRS_EXCG_CD": "NASD",
            "SORT_SQN": "DS",
            "ORD_DT": "",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/overseas-stock/v1/trading/inquire-ccnl",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output", []):
            result.append({
                "order_no": item.get("odno", ""),
                "symbol": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "side": "매수" if item.get("sll_buy_dvsn_cd") == "02" else "매도",
                "qty": int(item.get("ft_ord_qty", 0) or 0),
                "price": float(item.get("ft_ord_unpr3", 0) or 0),
                "filled_qty": int(item.get("ft_ccld_qty", 0) or 0),
                "status": item.get("ord_dvsn_name", ""),
                "exchange": item.get("ovrs_excg_cd", "")
            })

        return result

    # ========== 유틸리티 ==========

    def get_exchange_rate(self) -> float:
        """
        USD/KRW 환율 조회

        Returns:
            환율 (원/달러)
        """
        # 잔고 조회를 통해 환율 정보 획득
        try:
            balance = self.get_balance()
            return balance.get("exchange_rate", 1300.0)
        except Exception:
            return 1300.0  # 기본값

    def is_market_open(self) -> bool:
        """
        미국 시장 운영 시간 확인 (한국 시간 기준)

        일반거래: 23:30 ~ 06:00 (썸머타임 시 22:30 ~ 05:00)

        Returns:
            장 운영 여부
        """
        from datetime import datetime
        import pytz

        # 미국 동부 시간
        eastern = pytz.timezone('US/Eastern')
        now_eastern = datetime.now(eastern)

        # 주말 체크
        if now_eastern.weekday() >= 5:
            return False

        # 장 운영 시간 (09:30 ~ 16:00 EST)
        hour = now_eastern.hour
        minute = now_eastern.minute

        if hour == 9 and minute >= 30:
            return True
        elif 10 <= hour < 16:
            return True
        else:
            return False


# ========== 편의 함수 ==========

def get_us_client(is_virtual: bool = True) -> KISUSClient:
    """미국 주식 클라이언트 인스턴스 반환"""
    return KISUSClient(is_virtual)
