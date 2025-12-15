"""
한국투자증권 API 클라이언트
- REST API 호출 기본 클래스
- 국내주식 시세/주문/잔고 조회
"""

import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .kis_auth import KISAuth, get_auth


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
        body: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        API 요청 공통 메서드

        Args:
            method: HTTP 메서드 (GET/POST)
            endpoint: API 엔드포인트
            tr_id: 거래ID
            params: 쿼리 파라미터
            body: 요청 바디

        Returns:
            응답 JSON
        """
        url = f"{self.auth.base_url}{endpoint}"
        headers = self.auth.get_headers(tr_id)

        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        else:
            response = requests.post(url, headers=headers, json=body)

        response.raise_for_status()
        return response.json()

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
