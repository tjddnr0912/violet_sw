"""
한국투자증권 API 클라이언트
- REST API 호출 기본 클래스
- 국내주식 시세/주문/잔고 조회
"""

import time
import logging
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass
from requests.exceptions import Timeout, ConnectionError, RequestException

from .kis_auth import KISAuth, get_auth

logger = logging.getLogger(__name__)


# ========== 커스텀 예외 ==========

class KISAPIError(Exception):
    """KIS API 에러 기본 클래스"""
    def __init__(self, message: str, code: str = "", response: dict = None):
        self.message = message
        self.code = code
        self.response = response or {}
        super().__init__(f"[{code}] {message}" if code else message)


class KISTimeoutError(KISAPIError):
    """API 호출 타임아웃"""
    pass


class KISConnectionError(KISAPIError):
    """네트워크 연결 오류"""
    pass


class KISHTTPError(KISAPIError):
    """HTTP 오류 (4xx, 5xx)"""
    def __init__(self, message: str, status_code: int, response: dict = None):
        self.status_code = status_code
        super().__init__(message, str(status_code), response)


class KISRateLimitError(KISAPIError):
    """API 요청 제한 초과"""
    pass


class KISBusinessError(KISAPIError):
    """KIS 비즈니스 로직 오류 (rt_cd != 0)"""
    pass


@dataclass
class StockPrice:
    """주식 현재가 정보"""
    code: str           # 종목코드
    name: str           # 종목명
    price: int          # 현재가
    change: int         # 전일대비
    change_rate: float  # 등락률
    volume: int         # 거래량
    high: int           # 고가
    low: int            # 저가
    open: int           # 시가


@dataclass
class FinancialRatio:
    """재무비율 정보"""
    code: str           # 종목코드
    name: str           # 종목명
    per: float          # PER (주가수익비율)
    pbr: float          # PBR (주가순자산비율)
    eps: float          # EPS (주당순이익)
    bps: float          # BPS (주당순자산)
    roe: float          # ROE (자기자본이익률)
    dividend_yield: float  # 배당수익률


@dataclass
class MinuteCandle:
    """분봉 데이터"""
    time: str           # 시간 (HHMMSS)
    open: int           # 시가
    high: int           # 고가
    low: int            # 저가
    close: int          # 종가
    volume: int         # 거래량


@dataclass
class OrderResult:
    """주문 결과"""
    success: bool       # 성공 여부
    order_no: str       # 주문번호
    message: str        # 메시지


@dataclass
class StockBalance:
    """보유 주식 정보"""
    code: str           # 종목코드
    name: str           # 종목명
    qty: int            # 보유수량
    avg_price: int      # 평균단가
    current_price: int  # 현재가
    profit: int         # 평가손익
    profit_rate: float  # 수익률


class KISClient:
    """한국투자증권 API 클라이언트"""

    # API 설정
    DEFAULT_TIMEOUT = 10  # 초
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

        Args:
            method: HTTP 메서드 (GET/POST)
            endpoint: API 엔드포인트
            tr_id: 거래ID
            params: 쿼리 파라미터
            body: 요청 바디
            timeout: 타임아웃 (초)
            retries: 재시도 횟수

        Returns:
            응답 JSON

        Raises:
            KISTimeoutError: 타임아웃 발생
            KISConnectionError: 네트워크 오류
            KISHTTPError: HTTP 4xx/5xx 오류
            KISRateLimitError: 요청 제한 초과 (429)
            KISBusinessError: KIS 비즈니스 오류 (rt_cd != 0)
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
                    # 상태코드별 사용자 친화적 메시지
                    user_messages = {
                        400: "잘못된 요청입니다. 파라미터를 확인하세요.",
                        401: "API 인증 실패. 앱키와 시크릿을 확인하세요.",
                        403: "접근 권한이 없습니다. API 권한 설정을 확인하세요.",
                        404: "요청한 리소스를 찾을 수 없습니다.",
                        429: "API 요청 제한입니다. 잠시 후 다시 시도하세요.",
                        500: "증권사 서버 내부 오류입니다. 잠시 후 다시 시도하세요.",
                        502: "증권사 서버 연결 오류입니다. 잠시 후 다시 시도하세요.",
                        503: "증권사 서버 점검 중입니다. 잠시 후 다시 시도하세요.",
                        504: "증권사 서버 응답 시간 초과입니다."
                    }
                    user_msg = user_messages.get(
                        response.status_code,
                        f"서버 오류가 발생했습니다 (코드: {response.status_code})"
                    )
                    # 로그에는 상세 정보 기록
                    logger.error(
                        f"HTTP 에러 [{response.status_code}] {endpoint}: {response.text[:200]}",
                        extra={"status_code": response.status_code, "endpoint": endpoint}
                    )
                    raise KISHTTPError(user_msg, response.status_code)

                # JSON 파싱
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
                raise  # HTTP 에러는 재시도 안함

            except KISBusinessError:
                raise  # 비즈니스 에러는 재시도 안함

            except RequestException as e:
                last_error = KISAPIError(f"요청 오류: {e}")
                logger.warning(f"요청 오류 (시도 {attempt + 1}/{retries}): {e}")

            # 재시도 대기 (exponential backoff)
            if attempt < retries - 1:
                wait_time = self.RETRY_DELAY * (2 ** attempt)
                time.sleep(wait_time)

        # 모든 재시도 실패
        if last_error:
            logger.error(f"API 호출 최종 실패: {endpoint} - {last_error}")
            raise last_error

        raise KISAPIError(f"API 호출 실패: {endpoint}")

    # ========== 시세 조회 ==========

    def get_stock_price(self, stock_code: str) -> StockPrice:
        """
        국내주식 현재가 조회

        Args:
            stock_code: 종목코드 (예: "005930")

        Returns:
            StockPrice 객체
        """
        # 모의투자/실전투자 거래ID
        tr_id = "FHKST01010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 시장구분 (J: 주식)
            "FID_INPUT_ISCD": stock_code
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id=tr_id,
            params=params
        )

        output = data.get("output", {})

        return StockPrice(
            code=stock_code,
            name=output.get("hts_kor_isnm", ""),
            price=int(output.get("stck_prpr", 0)),
            change=int(output.get("prdy_vrss", 0)),
            change_rate=float(output.get("prdy_ctrt", 0)),
            volume=int(output.get("acml_vol", 0)),
            high=int(output.get("stck_hgpr", 0)),
            low=int(output.get("stck_lwpr", 0)),
            open=int(output.get("stck_oprc", 0))
        )

    def get_financial_ratio(self, stock_code: str) -> FinancialRatio:
        """
        국내주식 재무비율 조회 (PER, PBR, EPS, BPS, ROE, 배당수익률)

        Args:
            stock_code: 종목코드 (예: "005930")

        Returns:
            FinancialRatio 객체
        """
        # 현재가 상세 조회 API 사용 (재무비율 포함)
        tr_id = "FHKST01010100"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id=tr_id,
            params=params
        )

        output = data.get("output", {})

        return FinancialRatio(
            code=stock_code,
            name=output.get("hts_kor_isnm", ""),
            per=float(output.get("per", 0) or 0),
            pbr=float(output.get("pbr", 0) or 0),
            eps=float(output.get("eps", 0) or 0),
            bps=float(output.get("bps", 0) or 0),
            roe=float(output.get("roe", 0) or 0),
            dividend_yield=float(output.get("hts_avls_dl_rt", 0) or 0)
        )

    def get_minute_chart(
        self,
        stock_code: str,
        time: str = "",
        count: int = 30
    ) -> list:
        """
        국내주식 당일 분봉 조회

        Args:
            stock_code: 종목코드 (예: "005930")
            time: 조회 기준 시간 (HHMMSS, 빈값이면 현재시간)
            count: 조회 개수 (최대 30개)

        Returns:
            MinuteCandle 리스트 (최신 데이터가 앞)
        """
        tr_id = "FHKST03010200"

        # 시간이 지정되지 않으면 현재 시간 사용
        if not time:
            from datetime import datetime
            time = datetime.now().strftime("%H%M%S")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": time,
            "FID_PW_DATA_INCU_YN": "N",  # 당일 데이터만
            "FID_ETC_CLS_CODE": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output2", [])[:count]:
            result.append(MinuteCandle(
                time=item.get("stck_cntg_hour", ""),
                open=int(item.get("stck_oprc", 0)),
                high=int(item.get("stck_hgpr", 0)),
                low=int(item.get("stck_lwpr", 0)),
                close=int(item.get("stck_prpr", 0)),
                volume=int(item.get("cntg_vol", 0))
            ))

        return result

    def get_stock_history(
        self,
        stock_code: str,
        period: str = "D",
        count: int = 30
    ) -> list:
        """
        국내주식 기간별 시세 조회 (일/주/월봉)

        Args:
            stock_code: 종목코드
            period: 기간 (D:일, W:주, M:월)
            count: 조회 개수

        Returns:
            OHLCV 리스트
        """
        tr_id = "FHKST01010400"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0",  # 수정주가 원주가 (0: 수정주가)
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output", [])[:count]:
            result.append({
                "date": item.get("stck_bsop_date", ""),
                "open": int(item.get("stck_oprc", 0)),
                "high": int(item.get("stck_hgpr", 0)),
                "low": int(item.get("stck_lwpr", 0)),
                "close": int(item.get("stck_clpr", 0)),
                "volume": int(item.get("acml_vol", 0))
            })

        return result

    # ========== 주문 ==========

    def _validate_order_params(
        self,
        stock_code: str,
        qty: int,
        price: int,
        order_type: str
    ) -> tuple[bool, str]:
        """
        주문 파라미터 검증

        Returns:
            (유효여부, 에러메시지)
        """
        import re

        # 종목코드 검증 (6자리 숫자)
        if not stock_code or not re.match(r'^\d{6}$', stock_code):
            return False, f"올바른 종목코드를 입력하세요 (6자리 숫자): {stock_code}"

        # 수량 검증
        if not isinstance(qty, int) or qty < 1:
            return False, f"주문수량은 1 이상의 정수여야 합니다: {qty}"
        if qty > 999999:
            return False, f"주문수량이 너무 큽니다 (최대 999,999주): {qty}"

        # 가격 검증
        if not isinstance(price, int) or price < 0:
            return False, f"주문가격은 0 이상의 정수여야 합니다: {price}"

        # 주문유형 검증
        valid_order_types = ["00", "01"]  # 00: 지정가, 01: 시장가
        if order_type not in valid_order_types:
            return False, f"주문유형은 00(지정가) 또는 01(시장가)이어야 합니다: {order_type}"

        # 시장가 주문 시 가격은 0이어야 함
        if order_type == "01" and price != 0:
            return False, f"시장가 주문 시 가격은 0이어야 합니다: {price}"

        # 지정가 주문 시 가격은 0보다 커야 함
        if order_type == "00" and price <= 0:
            return False, f"지정가 주문 시 가격을 지정해야 합니다: {price}"

        return True, ""

    def buy_stock(
        self,
        stock_code: str,
        qty: int,
        price: int = 0,
        order_type: str = "00"
    ) -> OrderResult:
        """
        국내주식 매수 주문

        Args:
            stock_code: 종목코드
            qty: 주문수량
            price: 주문가격 (시장가일 때 0)
            order_type: 주문유형 (00: 지정가, 01: 시장가)

        Returns:
            OrderResult 객체
        """
        # 파라미터 검증
        is_valid, error_msg = self._validate_order_params(stock_code, qty, price, order_type)
        if not is_valid:
            return OrderResult(success=False, order_no="", message=error_msg)

        # 모의투자/실전투자 거래ID
        tr_id = "VTTC0802U" if self.is_virtual else "TTTC0802U"

        acct_no, acct_suffix = self.auth.get_account_info()

        body = {
            "CANO": acct_no,                    # 계좌번호 (8자리)
            "ACNT_PRDT_CD": acct_suffix,        # 계좌상품코드 (2자리)
            "PDNO": stock_code,                 # 종목코드
            "ORD_DVSN": order_type,             # 주문구분
            "ORD_QTY": str(qty),                # 주문수량
            "ORD_UNPR": str(price),             # 주문단가
        }

        try:
            data = self._request(
                method="POST",
                endpoint="/uapi/domestic-stock/v1/trading/order-cash",
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
        stock_code: str,
        qty: int,
        price: int = 0,
        order_type: str = "00"
    ) -> OrderResult:
        """
        국내주식 매도 주문

        Args:
            stock_code: 종목코드
            qty: 주문수량
            price: 주문가격 (시장가일 때 0)
            order_type: 주문유형 (00: 지정가, 01: 시장가)

        Returns:
            OrderResult 객체
        """
        # 파라미터 검증
        is_valid, error_msg = self._validate_order_params(stock_code, qty, price, order_type)
        if not is_valid:
            return OrderResult(success=False, order_no="", message=error_msg)

        # 모의투자/실전투자 거래ID
        tr_id = "VTTC0801U" if self.is_virtual else "TTTC0801U"

        acct_no, acct_suffix = self.auth.get_account_info()

        body = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "PDNO": stock_code,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }

        try:
            data = self._request(
                method="POST",
                endpoint="/uapi/domestic-stock/v1/trading/order-cash",
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
        계좌 잔고 조회

        Returns:
            잔고 정보 딕셔너리
        """
        # 모의투자/실전투자 거래ID
        tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"

        acct_no, acct_suffix = self.auth.get_account_info()

        params = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id=tr_id,
            params=params
        )

        # 보유종목 리스트
        stocks = []
        for item in data.get("output1", []):
            if int(item.get("hldg_qty", 0)) > 0:
                stocks.append(StockBalance(
                    code=item.get("pdno", ""),
                    name=item.get("prdt_name", ""),
                    qty=int(item.get("hldg_qty", 0)),
                    avg_price=int(float(item.get("pchs_avg_pric", 0))),
                    current_price=int(item.get("prpr", 0)),
                    profit=int(item.get("evlu_pfls_amt", 0)),
                    profit_rate=float(item.get("evlu_pfls_rt", 0))
                ))

        # 계좌 요약
        summary = data.get("output2", [{}])[0] if data.get("output2") else {}

        return {
            "stocks": stocks,
            "total_eval": int(summary.get("tot_evlu_amt", 0)),       # 총평가금액
            "total_profit": int(summary.get("evlu_pfls_smtl_amt", 0)),  # 총평가손익
            "cash": int(summary.get("dnca_tot_amt", 0)),             # 예수금총액
            "buy_amount": int(summary.get("pchs_amt_smtl_amt", 0))   # 매입금액합계
        }

    def get_order_history(self) -> list:
        """
        당일 주문내역 조회

        Returns:
            주문내역 리스트
        """
        tr_id = "VTTC8001R" if self.is_virtual else "TTTC8001R"

        acct_no, acct_suffix = self.auth.get_account_info()

        params = {
            "CANO": acct_no,
            "ACNT_PRDT_CD": acct_suffix,
            "INQR_STRT_DT": "",
            "INQR_END_DT": "",
            "SLL_BUY_DVSN_CD": "00",  # 전체
            "INQR_DVSN": "00",
            "PDNO": "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output1", []):
            result.append({
                "order_no": item.get("odno", ""),
                "code": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "side": "매수" if item.get("sll_buy_dvsn_cd") == "02" else "매도",
                "qty": int(item.get("ord_qty", 0)),
                "price": int(item.get("ord_unpr", 0)),
                "filled_qty": int(item.get("tot_ccld_qty", 0)),
                "status": item.get("ord_dvsn_name", "")
            })

        return result

    # ========== 휴장일 조회 ==========

    def get_holiday_schedule(self, base_date: str = None) -> list:
        """
        국내휴장일조회

        Args:
            base_date: 기준일자 (YYYYMMDD), None이면 오늘

        Returns:
            휴장일 리스트 ["YYYYMMDD", ...]
        """
        from datetime import datetime

        # TR-ID: CTCA0903R (실전/모의 공통)
        tr_id = "CTCA0903R"

        if not base_date:
            base_date = datetime.now().strftime("%Y%m%d")

        params = {
            "BASS_DT": base_date,
            "CTX_AREA_NK": "",
            "CTX_AREA_FK": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/chk-holiday",
            tr_id=tr_id,
            params=params
        )

        holidays = []
        for item in data.get("output", []):
            # opnd_yn: 개장 여부 (Y=개장, N=휴장)
            if item.get("opnd_yn") == "N":
                holidays.append(item.get("bass_dt", ""))

        return holidays
