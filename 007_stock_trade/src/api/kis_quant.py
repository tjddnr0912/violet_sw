"""
한국투자증권 퀀트 전략용 API 클라이언트
- 재무비율, 순위 조회, 모멘텀 계산 등
"""

import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .kis_client import KISClient


@dataclass
class FinancialStatement:
    """재무제표 데이터"""
    code: str
    name: str
    # 손익계산서
    revenue: int = 0                 # 매출액
    operating_profit: int = 0        # 영업이익
    net_income: int = 0              # 당기순이익
    # 재무상태표
    total_assets: int = 0            # 총자산
    total_liabilities: int = 0       # 총부채
    total_equity: int = 0            # 자기자본
    # 비율
    operating_margin: float = 0.0    # 영업이익률
    net_margin: float = 0.0          # 순이익률
    debt_ratio: float = 0.0          # 부채비율
    roe: float = 0.0                 # ROE
    roa: float = 0.0                 # ROA


@dataclass
class FinancialRatioExt:
    """재무비율 확장 데이터 (퀀트용)"""
    code: str
    name: str
    per: float = 0.0                 # PER
    pbr: float = 0.0                 # PBR
    psr: float = 0.0                 # PSR
    pcr: float = 0.0                 # PCR
    eps: float = 0.0                 # EPS
    bps: float = 0.0                 # BPS
    roe: float = 0.0                 # ROE
    roa: float = 0.0                 # ROA
    dividend_yield: float = 0.0      # 배당수익률
    operating_margin: float = 0.0    # 영업이익률
    debt_ratio: float = 0.0          # 부채비율


@dataclass
class RankingItem:
    """순위 데이터"""
    rank: int
    code: str
    name: str
    price: int = 0
    change: int = 0
    change_pct: float = 0.0
    volume: int = 0
    trade_amount: int = 0            # 거래대금 (백만원)
    market_cap: int = 0              # 시가총액 (억원)


@dataclass
class HighLowItem:
    """52주 신고저가 데이터"""
    code: str
    name: str
    price: int = 0
    high_52w: int = 0                # 52주 최고가
    low_52w: int = 0                 # 52주 최저가
    high_52w_date: str = ""          # 52주 최고가 일자
    low_52w_date: str = ""           # 52주 최저가 일자
    distance_from_high: float = 0.0  # 고점 대비 (%)
    distance_from_low: float = 0.0   # 저점 대비 (%)


@dataclass
class MomentumData:
    """모멘텀 데이터"""
    code: str
    name: str = ""
    current_price: int = 0
    return_1m: float = 0.0           # 1개월 수익률
    return_3m: float = 0.0           # 3개월 수익률
    return_6m: float = 0.0           # 6개월 수익률
    return_12m: float = 0.0          # 12개월 수익률
    return_12_1: float = 0.0         # 12-1 모멘텀 (최근 1개월 제외)
    high_52w: int = 0
    low_52w: int = 0
    distance_from_high: float = 0.0
    volatility_20d: float = 0.0      # 20일 변동성
    avg_volume_20d: int = 0          # 20일 평균 거래량


@dataclass
class DailyPrice:
    """일별 시세 데이터"""
    date: str
    open: int
    high: int
    low: int
    close: int
    volume: int
    change: int = 0
    change_pct: float = 0.0


class KISQuantClient(KISClient):
    """퀀트 전략용 확장 API 클라이언트"""

    def __init__(self, is_virtual: bool = True):
        super().__init__(is_virtual)
        # API 호출 제한 관리 (모의: 5건/초, 실전: 20건/초)
        self._last_call_time: float = 0
        self._min_interval: float = 0.5 if is_virtual else 0.1  # 여유있게 설정

    def _rate_limit(self):
        """API 호출 속도 제한"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    # ========== 재무 데이터 API ==========

    def get_financial_ratio_ext(self, stock_code: str) -> FinancialRatioExt:
        """
        재무비율 확장 조회 (퀀트 가치 팩터용)

        TR ID: FHKST66430300
        참고: 현재가 API에서 일부 재무비율 조회 가능
        """
        self._rate_limit()

        # 현재가 API에서 기본 재무비율 조회
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

        # 안전한 float 변환
        def safe_float(val, default=0.0):
            try:
                if val is None or val == "":
                    return default
                return float(val)
            except (ValueError, TypeError):
                return default

        return FinancialRatioExt(
            code=stock_code,
            name=output.get("hts_kor_isnm", ""),
            per=safe_float(output.get("per")),
            pbr=safe_float(output.get("pbr")),
            eps=safe_float(output.get("eps")),
            bps=safe_float(output.get("bps")),
            roe=safe_float(output.get("roe")),
            dividend_yield=safe_float(output.get("stck_dryy_hgpr")),  # 연중 배당수익률
            # 추가 필드는 다른 API에서 조회 필요
            psr=0.0,
            pcr=0.0,
            roa=0.0,
            operating_margin=0.0,
            debt_ratio=0.0
        )

    def get_financial_statement(self, stock_code: str) -> FinancialStatement:
        """
        재무제표 조회 (손익계산서 + 재무상태표)

        주의: 한국투자증권 API에서 상세 재무제표는
              별도 TR이 필요하며, 일부 데이터만 조회 가능
        """
        self._rate_limit()

        # 기본 정보에서 가능한 데이터 추출
        ratio = self.get_financial_ratio_ext(stock_code)

        return FinancialStatement(
            code=stock_code,
            name=ratio.name,
            roe=ratio.roe,
            operating_margin=ratio.operating_margin,
            debt_ratio=ratio.debt_ratio
        )

    # ========== 순위 조회 API ==========

    def get_market_cap_ranking(self, count: int = 100) -> List[RankingItem]:
        """
        시가총액 순위 조회 (페이지네이션 지원)

        TR ID: FHPST01740000

        Note: API가 한 번에 최대 30개만 반환하므로,
              count > 30인 경우 여러 번 호출하여 데이터를 누적합니다.
        """
        tr_id = "FHPST01740000"
        result = []
        last_code = "0000"  # 시작값
        max_per_page = 30   # API 제한

        while len(result) < count:
            self._rate_limit()

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_COND_SCR_DIV_CODE": "20174",
                "FID_INPUT_ISCD": last_code,
                "FID_DIV_CLS_CODE": "0",
                "FID_BLNG_CLS_CODE": "0",
                "FID_TRGT_CLS_CODE": "111111111",
                "FID_TRGT_EXLS_CLS_CODE": "000000",
                "FID_INPUT_PRICE_1": "",
                "FID_INPUT_PRICE_2": "",
                "FID_VOL_CNT": "",
                "FID_INPUT_DATE_1": ""
            }

            data = self._request(
                method="GET",
                endpoint="/uapi/domestic-stock/v1/ranking/market-cap",
                tr_id=tr_id,
                params=params
            )

            items = data.get("output", [])
            if not items:
                break  # 더 이상 데이터 없음

            for item in items:
                if len(result) >= count:
                    break
                try:
                    code = item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", "")
                    if not code:
                        continue

                    # 중복 체크
                    if any(r.code == code for r in result):
                        continue

                    result.append(RankingItem(
                        rank=len(result) + 1,
                        code=code,
                        name=item.get("hts_kor_isnm", ""),
                        price=int(item.get("stck_prpr", 0) or 0),
                        change=int(item.get("prdy_vrss", 0) or 0),
                        change_pct=float(item.get("prdy_ctrt", 0) or 0),
                        volume=int(item.get("acml_vol", 0) or 0),
                        trade_amount=int(item.get("acml_tr_pbmn", 0) or 0),
                        market_cap=int(item.get("stck_avls", 0) or 0)
                    ))
                    last_code = code
                except (ValueError, TypeError) as e:
                    continue

            # 받은 데이터가 max_per_page보다 적으면 더 이상 데이터 없음
            if len(items) < max_per_page:
                break

        return result

    def get_volume_ranking(self, count: int = 100) -> List[RankingItem]:
        """
        거래량 순위 조회

        TR ID: FHPST01710000
        """
        self._rate_limit()

        tr_id = "FHPST01710000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/volume-rank",
            tr_id=tr_id,
            params=params
        )

        result = []
        for i, item in enumerate(data.get("output", [])[:count], 1):
            try:
                result.append(RankingItem(
                    rank=i,
                    code=item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                    name=item.get("hts_kor_isnm", ""),
                    price=int(item.get("stck_prpr", 0) or 0),
                    change=int(item.get("prdy_vrss", 0) or 0),
                    change_pct=float(item.get("prdy_ctrt", 0) or 0),
                    volume=int(item.get("acml_vol", 0) or 0),
                    trade_amount=int(item.get("acml_tr_pbmn", 0) or 0),
                    market_cap=0
                ))
            except (ValueError, TypeError):
                continue

        return result

    def get_fluctuation_ranking(
        self,
        count: int = 100,
        is_rise: bool = True
    ) -> List[RankingItem]:
        """
        등락률 순위 조회

        TR ID: FHPST01720000

        Args:
            count: 조회 개수
            is_rise: True=상승률, False=하락률
        """
        self._rate_limit()

        tr_id = "FHPST01720000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20172",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0" if is_rise else "1",  # 0:상승, 1:하락
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/ranking/fluctuation",
            tr_id=tr_id,
            params=params
        )

        result = []
        for i, item in enumerate(data.get("output", [])[:count], 1):
            try:
                result.append(RankingItem(
                    rank=i,
                    code=item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                    name=item.get("hts_kor_isnm", ""),
                    price=int(item.get("stck_prpr", 0) or 0),
                    change=int(item.get("prdy_vrss", 0) or 0),
                    change_pct=float(item.get("prdy_ctrt", 0) or 0),
                    volume=int(item.get("acml_vol", 0) or 0),
                    trade_amount=int(item.get("acml_tr_pbmn", 0) or 0),
                    market_cap=0
                ))
            except (ValueError, TypeError):
                continue

        return result

    # ========== 52주 신고저가 API ==========

    def get_52week_high_stocks(self, count: int = 50) -> List[HighLowItem]:
        """
        52주 신고가 종목 조회

        TR ID: FHPST01730000
        """
        self._rate_limit()

        tr_id = "FHPST01730000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20173",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",  # 0: 신고가
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output", [])[:count]:
            try:
                price = int(item.get("stck_prpr", 0) or 0)
                high_52w = int(item.get("stck_hgpr", 0) or item.get("d250_hgpr", 0) or price)
                low_52w = int(item.get("stck_lwpr", 0) or item.get("d250_lwpr", 0) or price)

                dist_high = ((price - high_52w) / high_52w * 100) if high_52w > 0 else 0
                dist_low = ((price - low_52w) / low_52w * 100) if low_52w > 0 else 0

                result.append(HighLowItem(
                    code=item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                    name=item.get("hts_kor_isnm", ""),
                    price=price,
                    high_52w=high_52w,
                    low_52w=low_52w,
                    high_52w_date=item.get("d250_hgpr_date", ""),
                    low_52w_date=item.get("d250_lwpr_date", ""),
                    distance_from_high=dist_high,
                    distance_from_low=dist_low
                ))
            except (ValueError, TypeError):
                continue

        return result

    def get_52week_low_stocks(self, count: int = 50) -> List[HighLowItem]:
        """
        52주 신저가 종목 조회
        """
        self._rate_limit()

        tr_id = "FHPST01730000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20173",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "1",  # 1: 신저가
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output", [])[:count]:
            try:
                price = int(item.get("stck_prpr", 0) or 0)
                high_52w = int(item.get("stck_hgpr", 0) or item.get("d250_hgpr", 0) or price)
                low_52w = int(item.get("stck_lwpr", 0) or item.get("d250_lwpr", 0) or price)

                dist_high = ((price - high_52w) / high_52w * 100) if high_52w > 0 else 0
                dist_low = ((price - low_52w) / low_52w * 100) if low_52w > 0 else 0

                result.append(HighLowItem(
                    code=item.get("mksc_shrn_iscd", "") or item.get("stck_shrn_iscd", ""),
                    name=item.get("hts_kor_isnm", ""),
                    price=price,
                    high_52w=high_52w,
                    low_52w=low_52w,
                    high_52w_date=item.get("d250_hgpr_date", ""),
                    low_52w_date=item.get("d250_lwpr_date", ""),
                    distance_from_high=dist_high,
                    distance_from_low=dist_low
                ))
            except (ValueError, TypeError):
                continue

        return result

    # ========== 기간별 시세 및 모멘텀 ==========

    def get_daily_prices(
        self,
        stock_code: str,
        period: str = "D",
        count: int = 100
    ) -> List[DailyPrice]:
        """
        기간별 시세 조회 (일/주/월)

        TR ID: FHKST03010100

        Args:
            stock_code: 종목코드
            period: D(일), W(주), M(월)
            count: 조회 개수
        """
        self._rate_limit()

        tr_id = "FHKST03010100"

        # 종료일자 (오늘)
        end_date = datetime.now().strftime("%Y%m%d")
        # 시작일자 (약 2년 전)
        start_date = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": period,
            "FID_ORG_ADJ_PRC": "0"  # 수정주가
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output2", [])[:count]:
            try:
                result.append(DailyPrice(
                    date=item.get("stck_bsop_date", ""),
                    open=int(item.get("stck_oprc", 0) or 0),
                    high=int(item.get("stck_hgpr", 0) or 0),
                    low=int(item.get("stck_lwpr", 0) or 0),
                    close=int(item.get("stck_clpr", 0) or 0),
                    volume=int(item.get("acml_vol", 0) or 0),
                    change=int(item.get("prdy_vrss", 0) or 0),
                    change_pct=float(item.get("prdy_ctrt", 0) or 0)
                ))
            except (ValueError, TypeError):
                continue

        return result

    def calculate_momentum(self, stock_code: str) -> MomentumData:
        """
        모멘텀 데이터 계산

        Args:
            stock_code: 종목코드

        Returns:
            MomentumData: 기간별 수익률 및 모멘텀 지표
        """
        # 일봉 데이터 조회 (최근 260일 = 약 1년)
        prices = self.get_daily_prices(stock_code, period="D", count=260)

        if len(prices) < 30:
            raise ValueError(f"데이터 부족: {len(prices)}일 (최소 30일 필요)")

        # 최신 데이터가 앞에 있음
        current_price = prices[0].close
        name = ""

        # 안전한 인덱스 접근
        def get_price_at(days: int) -> int:
            if days < len(prices):
                return prices[days].close
            return prices[-1].close

        # 기간별 수익률 계산
        price_1m = get_price_at(21)   # 약 1개월 (21거래일)
        price_3m = get_price_at(63)   # 약 3개월
        price_6m = get_price_at(126)  # 약 6개월
        price_12m = get_price_at(252) # 약 12개월

        return_1m = ((current_price - price_1m) / price_1m * 100) if price_1m > 0 else 0
        return_3m = ((current_price - price_3m) / price_3m * 100) if price_3m > 0 else 0
        return_6m = ((current_price - price_6m) / price_6m * 100) if price_6m > 0 else 0
        return_12m = ((current_price - price_12m) / price_12m * 100) if price_12m > 0 else 0

        # 12-1 모멘텀 (최근 1개월 제외)
        return_12_1 = return_12m - return_1m

        # 52주 고저가
        closes = [p.close for p in prices[:252]]
        high_52w = max(closes) if closes else current_price
        low_52w = min(closes) if closes else current_price

        distance_from_high = ((current_price - high_52w) / high_52w * 100) if high_52w > 0 else 0

        # 20일 변동성 (표준편차)
        returns_20d = []
        for i in range(min(20, len(prices) - 1)):
            if prices[i + 1].close > 0:
                daily_ret = (prices[i].close - prices[i + 1].close) / prices[i + 1].close
                returns_20d.append(daily_ret)

        if returns_20d:
            import statistics
            volatility_20d = statistics.stdev(returns_20d) * 100 * (252 ** 0.5)  # 연환산
        else:
            volatility_20d = 0

        # 20일 평균 거래량
        volumes_20d = [p.volume for p in prices[:20]]
        avg_volume_20d = sum(volumes_20d) // len(volumes_20d) if volumes_20d else 0

        return MomentumData(
            code=stock_code,
            name=name,
            current_price=current_price,
            return_1m=round(return_1m, 2),
            return_3m=round(return_3m, 2),
            return_6m=round(return_6m, 2),
            return_12m=round(return_12m, 2),
            return_12_1=round(return_12_1, 2),
            high_52w=high_52w,
            low_52w=low_52w,
            distance_from_high=round(distance_from_high, 2),
            volatility_20d=round(volatility_20d, 2),
            avg_volume_20d=avg_volume_20d
        )

    # ========== 유틸리티 ==========

    def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """
        종목 종합 정보 조회 (시세 + 재무 + 모멘텀)
        """
        info = {}

        # 현재가
        try:
            price = self.get_stock_price(stock_code)
            info['price'] = {
                'code': price.code,
                'name': price.name,
                'price': price.price,
                'change': price.change,
                'change_pct': price.change_rate,
                'volume': price.volume
            }
        except Exception as e:
            info['price'] = {'error': str(e)}

        # 재무비율
        try:
            ratio = self.get_financial_ratio_ext(stock_code)
            info['financial'] = {
                'per': ratio.per,
                'pbr': ratio.pbr,
                'eps': ratio.eps,
                'roe': ratio.roe,
                'dividend_yield': ratio.dividend_yield
            }
        except Exception as e:
            info['financial'] = {'error': str(e)}

        # 모멘텀
        try:
            momentum = self.calculate_momentum(stock_code)
            info['momentum'] = {
                'return_1m': momentum.return_1m,
                'return_3m': momentum.return_3m,
                'return_6m': momentum.return_6m,
                'return_12m': momentum.return_12m,
                'distance_from_high': momentum.distance_from_high,
                'volatility': momentum.volatility_20d
            }
        except Exception as e:
            info['momentum'] = {'error': str(e)}

        return info
