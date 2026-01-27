"""
멀티팩터 종목 스크리너
- 유니버스 구성
- 팩터 점수 계산
- 종목 선정 및 순위
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging

from .factors import (
    CompositeScore,
    CompositeScoreCalculator,
    FactorWeights
)


logger = logging.getLogger(__name__)


@dataclass
class ScreeningConfig:
    """스크리닝 설정"""
    # 유니버스 설정
    universe_size: int = 300          # 시가총액 상위 N개
    min_market_cap: int = 1000        # 최소 시가총액 (억원)
    min_avg_volume: int = 100000      # 최소 평균 거래량

    # 종목 선정 설정
    target_count: int = 20            # 최종 선정 종목 수
    max_per_sector: float = 0.30      # 섹터당 최대 비중 (30%)

    # 팩터 가중치
    value_weight: float = 0.40
    momentum_weight: float = 0.30
    quality_weight: float = 0.30

    # 필터 설정
    filter_per_max: float = 50
    filter_pbr_max: float = 10
    filter_debt_max: float = 300
    filter_return_min: float = -30


@dataclass
class ScreeningResult:
    """스크리닝 결과"""
    timestamp: datetime
    config: ScreeningConfig
    universe_count: int              # 유니버스 종목 수
    filtered_count: int              # 필터 통과 종목 수
    selected_stocks: List[CompositeScore]  # 최종 선정 종목
    all_scores: List[CompositeScore]  # 전체 점수 (분석용)
    errors: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class MultiFactorScreener:
    """멀티팩터 종목 스크리너"""

    def __init__(
        self,
        api_client,
        config: ScreeningConfig = None
    ):
        """
        Args:
            api_client: KISQuantClient 인스턴스
            config: 스크리닝 설정
        """
        self.client = api_client
        self.config = config or ScreeningConfig()

        self.score_calc = CompositeScoreCalculator(
            value_weight=self.config.value_weight,
            momentum_weight=self.config.momentum_weight,
            quality_weight=self.config.quality_weight
        )

    def build_universe(self) -> List[Dict]:
        """
        유니버스 구성 (시가총액 상위 종목)

        KIS API가 30개 제한이 있으므로, pykrx를 사용하여
        더 큰 유니버스 (KOSPI200 등)를 구성합니다.

        Returns:
            종목 기본 정보 리스트
        """
        logger.info(f"유니버스 구성 시작 (상위 {self.config.universe_size}개)")

        # 1. 먼저 KIS API로 시도
        universe = self._build_universe_from_kis()

        # 2. 결과가 부족하면 pykrx 사용
        if len(universe) < self.config.universe_size:
            kis_count = len(universe)
            logger.info(f"KIS API 결과 부족 ({kis_count}개), pykrx로 확장 시도...")
            pykrx_universe = self._build_universe_from_pykrx()

            # pykrx 결과가 유효하면 사용, 아니면 KIS 결과 유지
            if pykrx_universe and len(pykrx_universe) > 0:
                universe = pykrx_universe
            else:
                logger.warning(f"pykrx 실패, KIS API 결과({kis_count}개)로 진행")

        logger.info(f"유니버스 구성 완료: {len(universe)}개 종목")
        return universe

    def _build_universe_from_kis(self) -> List[Dict]:
        """KIS API를 사용하여 유니버스 구성"""
        try:
            rankings = self.client.get_market_cap_ranking(
                count=self.config.universe_size
            )

            universe = []
            for r in rankings:
                # 최소 시가총액 필터
                if r.market_cap < self.config.min_market_cap:
                    continue

                universe.append({
                    "code": r.code,
                    "name": r.name,
                    "price": r.price,
                    "market_cap": r.market_cap,
                    "volume": r.volume,
                    "change_pct": r.change_pct
                })

            return universe

        except Exception as e:
            logger.error(f"KIS API 유니버스 구성 실패: {e}")
            return []

    def _build_universe_from_pykrx(self) -> List[Dict]:
        """
        pykrx를 사용하여 KOSPI200 기반 유니버스 구성

        KOSPI200은 시가총액 상위 대형주로 구성되어
        퀀트 전략에 적합한 유니버스입니다.
        """
        try:
            from pykrx import stock as pykrx_stock
            import warnings
            warnings.filterwarnings('ignore', category=UserWarning)

            logger.info("pykrx로 KOSPI200 구성종목 조회 중...")

            # KOSPI200 구성종목 조회 (약 200개)
            kospi200_codes = list(pykrx_stock.get_index_portfolio_deposit_file('1028'))
            logger.info(f"KOSPI200: {len(kospi200_codes)}개 종목")

            # 시가총액 데이터 한 번에 조회 (최적화)
            # 공휴일/주말인 경우 최근 거래일 데이터 사용
            try:
                from datetime import datetime, timedelta
                cap_df = None

                for days_back in range(7):  # 최대 7일 전까지 탐색
                    target_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
                    try:
                        df = pykrx_stock.get_market_cap_by_ticker(target_date)
                        if len(df) > 0 and df['시가총액'].sum() > 0:
                            cap_df = df
                            logger.info(f"시가총액 데이터 조회 완료 ({target_date}): {len(cap_df)}개")
                            break
                    except:
                        continue

                if cap_df is None:
                    logger.warning("시가총액 데이터 조회 실패 (최근 7일 내 거래일 없음)")
            except Exception as e:
                logger.warning(f"시가총액 데이터 조회 실패: {e}")
                cap_df = None

            universe = []
            for code in kospi200_codes:
                if len(universe) >= self.config.universe_size:
                    break

                try:
                    # pykrx에서 종목명 조회
                    name = pykrx_stock.get_market_ticker_name(code)

                    # 시가총액 조회 (미리 가져온 데이터에서)
                    if cap_df is not None and code in cap_df.index:
                        market_cap = int(cap_df.loc[code, '시가총액'] / 100_000_000)  # 억원 단위
                    else:
                        market_cap = 0

                    # 최소 시가총액 필터
                    if market_cap > 0 and market_cap < self.config.min_market_cap:
                        continue

                    # 기본 정보만 저장 (현재가는 나중에 조회)
                    universe.append({
                        "code": code,
                        "name": name,
                        "price": 0,  # 나중에 개별 조회
                        "market_cap": market_cap,
                        "volume": 0,
                        "change_pct": 0
                    })

                except Exception as e:
                    logger.warning(f"{code}: 데이터 조회 실패 - {e}")
                    continue

            # 시가총액 기준 정렬
            universe.sort(key=lambda x: x.get('market_cap', 0), reverse=True)

            logger.info(f"pykrx 유니버스 구성 완료: {len(universe)}개")
            return universe

        except ImportError:
            logger.error("pykrx 라이브러리가 설치되지 않았습니다. pip install pykrx")
            return []
        except Exception as e:
            logger.error(f"pykrx 유니버스 구성 실패: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_stock_data(self, code: str, stock_name: str = "") -> Dict:
        """
        개별 종목 데이터 수집 (재무 + 모멘텀)

        Args:
            code: 종목코드
            stock_name: 종목명 (유니버스에서 전달)

        Returns:
            종목 데이터 딕셔너리
        """
        data = {"code": code, "name": stock_name, "error": None}

        try:
            # 재무비율 조회
            ratio = self.client.get_financial_ratio_ext(code)
            # API에서 종목명이 반환되면 사용, 아니면 전달받은 종목명 유지
            if ratio.name:
                data["name"] = ratio.name
            data["per"] = ratio.per
            data["pbr"] = ratio.pbr
            data["psr"] = ratio.psr
            data["eps"] = ratio.eps
            data["roe"] = ratio.roe
            data["dividend_yield"] = ratio.dividend_yield
            data["operating_margin"] = ratio.operating_margin
            data["debt_ratio"] = ratio.debt_ratio

        except Exception as e:
            data["error"] = f"재무비율 조회 실패: {e}"
            return data

        try:
            # 모멘텀 계산
            momentum = self.client.calculate_momentum(code)
            data["return_1m"] = momentum.return_1m
            data["return_3m"] = momentum.return_3m
            data["return_6m"] = momentum.return_6m
            data["return_12m"] = momentum.return_12m
            data["distance_from_high"] = momentum.distance_from_high
            data["volatility"] = momentum.volatility_20d
            data["avg_volume"] = momentum.avg_volume_20d

        except Exception as e:
            # 모멘텀 계산 실패 시 기본값 사용
            data["return_1m"] = 0
            data["return_3m"] = 0
            data["return_6m"] = 0
            data["return_12m"] = 0
            data["distance_from_high"] = 0
            data["volatility"] = 0
            data["avg_volume"] = 0
            logger.warning(f"{code}: 모멘텀 계산 실패, 기본값 사용")

        return data

    def calculate_scores(
        self,
        universe: List[Dict],
        progress_callback=None
    ) -> List[CompositeScore]:
        """
        전체 유니버스에 대해 점수 계산

        Args:
            universe: 유니버스 종목 리스트
            progress_callback: 진행 상황 콜백 함수

        Returns:
            CompositeScore 리스트
        """
        scores = []
        total = len(universe)
        errors = []

        for i, stock in enumerate(universe):
            code = stock["code"]

            if progress_callback:
                progress_callback(i + 1, total, code)

            try:
                # 종목 데이터 수집 (유니버스에서 종목명 전달)
                stock_name = stock.get("name", "")
                data = self.get_stock_data(code, stock_name)

                if data.get("error"):
                    errors.append(f"{code}: {data['error']}")
                    continue

                # 복합 점수 계산
                score = self.score_calc.calculate(
                    code=code,
                    name=data.get("name", ""),
                    per=data.get("per", 0),
                    pbr=data.get("pbr", 0),
                    psr=data.get("psr", 0),
                    dividend_yield=data.get("dividend_yield", 0),
                    return_1m=data.get("return_1m", 0),
                    return_3m=data.get("return_3m", 0),
                    return_6m=data.get("return_6m", 0),
                    return_12m=data.get("return_12m", 0),
                    distance_from_high=data.get("distance_from_high", 0),
                    volatility=data.get("volatility", 0),
                    roe=data.get("roe", 0),
                    operating_margin=data.get("operating_margin", 0),
                    debt_ratio=data.get("debt_ratio", 0),
                    market_cap=stock.get("market_cap", 0)
                )

                scores.append(score)

            except Exception as e:
                errors.append(f"{code}: {str(e)}")
                continue

        if errors:
            logger.warning(f"점수 계산 중 {len(errors)}개 오류 발생")

        return scores

    def select_top_stocks(
        self,
        scores: List[CompositeScore],
        count: int = None
    ) -> List[CompositeScore]:
        """
        상위 종목 선정

        Args:
            scores: 전체 점수 리스트
            count: 선정 개수

        Returns:
            선정된 종목 리스트
        """
        count = count or self.config.target_count

        # 필터 통과한 종목만
        passed = [s for s in scores if s.passed_filter]

        # 복합 점수 기준 정렬
        passed.sort(key=lambda x: x.composite_score, reverse=True)

        # 순위 부여
        for i, score in enumerate(passed, 1):
            score.rank = i

        # 상위 N개 선정
        selected = passed[:count]

        logger.info(f"종목 선정 완료: {len(selected)}개 / 전체 {len(passed)}개")

        return selected

    def apply_sector_diversification(
        self,
        stocks: List[CompositeScore],
        sector_map: Dict[str, str] = None
    ) -> List[CompositeScore]:
        """
        섹터 분산 적용 (선택적)

        섹터 정보가 있는 경우 단일 섹터 비중 제한
        """
        if not sector_map:
            return stocks

        max_per_sector = int(len(stocks) * self.config.max_per_sector)
        sector_count = {}
        diversified = []

        for stock in stocks:
            sector = sector_map.get(stock.code, "기타")

            if sector_count.get(sector, 0) < max_per_sector:
                diversified.append(stock)
                sector_count[sector] = sector_count.get(sector, 0) + 1

        return diversified

    def run_screening(
        self,
        progress_callback=None
    ) -> ScreeningResult:
        """
        전체 스크리닝 실행

        Args:
            progress_callback: 진행 상황 콜백 (current, total, stock_code)

        Returns:
            ScreeningResult
        """
        start_time = time.time()
        errors = []

        logger.info("=" * 50)
        logger.info("멀티팩터 스크리닝 시작")
        logger.info("=" * 50)

        # 1. 유니버스 구성
        universe = self.build_universe()
        if not universe:
            return ScreeningResult(
                timestamp=datetime.now(),
                config=self.config,
                universe_count=0,
                filtered_count=0,
                selected_stocks=[],
                all_scores=[],
                errors=["유니버스 구성 실패"],
                elapsed_seconds=time.time() - start_time
            )

        # 2. 점수 계산
        logger.info(f"점수 계산 시작: {len(universe)}개 종목")
        scores = self.calculate_scores(universe, progress_callback)

        # 3. 종목 선정
        selected = self.select_top_stocks(scores)

        elapsed = time.time() - start_time

        logger.info("=" * 50)
        logger.info(f"스크리닝 완료: {elapsed:.1f}초 소요")
        logger.info(f"유니버스: {len(universe)}개")
        logger.info(f"필터 통과: {len([s for s in scores if s.passed_filter])}개")
        logger.info(f"최종 선정: {len(selected)}개")
        logger.info("=" * 50)

        return ScreeningResult(
            timestamp=datetime.now(),
            config=self.config,
            universe_count=len(universe),
            filtered_count=len([s for s in scores if s.passed_filter]),
            selected_stocks=selected,
            all_scores=scores,
            errors=errors,
            elapsed_seconds=elapsed
        )

    def get_stock_ranking_detail(
        self,
        result: ScreeningResult,
        top_n: int = 30
    ) -> str:
        """
        스크리닝 결과 상세 리포트 생성
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"멀티팩터 스크리닝 결과 ({result.timestamp.strftime('%Y-%m-%d %H:%M')})")
        lines.append("=" * 80)
        lines.append(f"유니버스: {result.universe_count}개 → 필터 통과: {result.filtered_count}개 → 선정: {len(result.selected_stocks)}개")
        lines.append(f"소요시간: {result.elapsed_seconds:.1f}초")
        lines.append("")
        lines.append(f"가중치: 가치 {self.config.value_weight*100:.0f}% / 모멘텀 {self.config.momentum_weight*100:.0f}% / 퀄리티 {self.config.quality_weight*100:.0f}%")
        lines.append("")
        lines.append("-" * 80)
        lines.append(f"{'순위':>4} {'종목명':<12} {'코드':>8} {'복합':>6} {'가치':>6} {'모멘텀':>6} {'퀄리티':>6} {'PER':>6} {'PBR':>5} {'12M%':>7}")
        lines.append("-" * 80)

        for stock in result.selected_stocks[:top_n]:
            lines.append(
                f"{stock.rank:>4} {stock.name[:10]:<12} {stock.code:>8} "
                f"{stock.composite_score:>6.1f} {stock.value_score:>6.1f} "
                f"{stock.momentum_score:>6.1f} {stock.quality_score:>6.1f} "
                f"{stock.per:>6.1f} {stock.pbr:>5.2f} {stock.return_12m:>+7.1f}"
            )

        lines.append("-" * 80)

        return "\n".join(lines)

    def export_to_excel(
        self,
        result: ScreeningResult,
        filepath: str = None,
        include_technical: bool = True
    ) -> str:
        """
        스크리닝 결과를 엑셀 파일로 저장

        Args:
            result: 스크리닝 결과
            filepath: 저장 경로 (None이면 자동 생성)
            include_technical: 기술적 분석 포함 여부

        Returns:
            저장된 파일 경로
        """
        import pandas as pd
        from pathlib import Path

        # 파일 경로 생성
        if filepath is None:
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "screening"
            data_dir.mkdir(parents=True, exist_ok=True)
            filename = f"screening_{result.timestamp.strftime('%Y%m%d_%H%M')}.xlsx"
            filepath = str(data_dir / filename)

        # ExcelWriter 생성
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # ========== 1. 요약 시트 ==========
            summary_data = {
                "항목": [
                    "스크리닝 일시",
                    "유니버스 크기",
                    "필터 통과",
                    "최종 선정",
                    "소요 시간",
                    "",
                    "가치 가중치",
                    "모멘텀 가중치",
                    "퀄리티 가중치",
                    "",
                    "PER 상한",
                    "PBR 상한",
                    "부채비율 상한",
                    "12M 수익률 하한"
                ],
                "값": [
                    result.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    f"{result.universe_count}개",
                    f"{result.filtered_count}개",
                    f"{len(result.selected_stocks)}개",
                    f"{result.elapsed_seconds:.1f}초",
                    "",
                    f"{self.config.value_weight*100:.0f}%",
                    f"{self.config.momentum_weight*100:.0f}%",
                    f"{self.config.quality_weight*100:.0f}%",
                    "",
                    f"{self.config.filter_per_max}",
                    f"{self.config.filter_pbr_max}",
                    f"{self.config.filter_debt_max}%",
                    f"{self.config.filter_return_min}%"
                ]
            }
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name='요약', index=False)

            # ========== 2. 전체 종목 시트 ==========
            all_stocks_data = []
            for score in result.all_scores:
                all_stocks_data.append({
                    "순위": score.rank if score.rank else "-",
                    "종목코드": score.code,
                    "종목명": score.name,
                    "복합점수": round(score.composite_score, 1),
                    "가치점수": round(score.value_score, 1),
                    "모멘텀점수": round(score.momentum_score, 1),
                    "퀄리티점수": round(score.quality_score, 1),
                    "PER": round(score.per, 2) if score.per else 0,
                    "PBR": round(score.pbr, 2) if score.pbr else 0,
                    "ROE": round(score.roe, 2) if score.roe else 0,
                    "6M수익률": round(score.return_6m, 2) if score.return_6m else 0,
                    "12M수익률": round(score.return_12m, 2) if score.return_12m else 0,
                    "고점대비": round(score.distance_from_high, 2) if score.distance_from_high else 0,
                    "부채비율": round(score.debt_ratio, 2) if score.debt_ratio else 0,
                    "필터통과": "O" if score.passed_filter else "X",
                    "필터사유": score.filter_reason if not score.passed_filter else ""
                })

            df_all = pd.DataFrame(all_stocks_data)
            # 복합점수 기준 정렬
            df_all = df_all.sort_values('복합점수', ascending=False)
            df_all.to_excel(writer, sheet_name='전체종목', index=False)

            # ========== 3. 선정 종목 시트 ==========
            selected_data = []
            for score in result.selected_stocks:
                selected_data.append({
                    "순위": score.rank,
                    "종목코드": score.code,
                    "종목명": score.name,
                    "복합점수": round(score.composite_score, 1),
                    "가치점수": round(score.value_score, 1),
                    "모멘텀점수": round(score.momentum_score, 1),
                    "퀄리티점수": round(score.quality_score, 1),
                    "PER": round(score.per, 2) if score.per else 0,
                    "PBR": round(score.pbr, 2) if score.pbr else 0,
                    "ROE": round(score.roe, 2) if score.roe else 0,
                    "6M수익률": round(score.return_6m, 2) if score.return_6m else 0,
                    "12M수익률": round(score.return_12m, 2) if score.return_12m else 0,
                    "고점대비": round(score.distance_from_high, 2) if score.distance_from_high else 0,
                    "부채비율": round(score.debt_ratio, 2) if score.debt_ratio else 0
                })

            df_selected = pd.DataFrame(selected_data)
            df_selected.to_excel(writer, sheet_name='선정종목', index=False)

            # ========== 4. 기술적 분석 시트 (선정 종목만) ==========
            if include_technical and result.selected_stocks:
                from .signals import TechnicalAnalyzer

                tech_analyzer = TechnicalAnalyzer()
                tech_data = []

                for score in result.selected_stocks:
                    try:
                        # 일봉 데이터 조회
                        prices_raw = self.client.get_daily_prices(score.code, period="D", count=60)
                        prices = [p.close for p in prices_raw]

                        if len(prices) >= 30:
                            signal = tech_analyzer.analyze(prices)

                            tech_data.append({
                                "순위": score.rank,
                                "종목코드": score.code,
                                "종목명": score.name,
                                "현재가": prices[0] if prices else 0,
                                "신호": signal.signal_type.value,
                                "신호점수": round(signal.score, 1),
                                "RSI": round(signal.rsi, 1),
                                "RSI신호": signal.details.get("rsi_signal", ""),
                                "MACD신호": signal.macd_signal,
                                "MA추세": signal.details.get("ma_trend", ""),
                                "BB위치": signal.bb_signal,
                                "MA20": round(signal.details.get("ma20", 0), 0),
                                "MA60": round(signal.details.get("ma60", 0), 0),
                                "BB상단": round(signal.details.get("bb_upper", 0), 0),
                                "BB하단": round(signal.details.get("bb_lower", 0), 0)
                            })
                        else:
                            tech_data.append({
                                "순위": score.rank,
                                "종목코드": score.code,
                                "종목명": score.name,
                                "현재가": 0,
                                "신호": "데이터부족",
                                "신호점수": 0,
                                "RSI": 0,
                                "RSI신호": "",
                                "MACD신호": "",
                                "MA추세": "",
                                "BB위치": "",
                                "MA20": 0,
                                "MA60": 0,
                                "BB상단": 0,
                                "BB하단": 0
                            })

                    except Exception as e:
                        logger.warning(f"기술적 분석 실패 ({score.code}): {e}")
                        tech_data.append({
                            "순위": score.rank,
                            "종목코드": score.code,
                            "종목명": score.name,
                            "현재가": 0,
                            "신호": "오류",
                            "신호점수": 0,
                            "RSI": 0,
                            "RSI신호": "",
                            "MACD신호": "",
                            "MA추세": "",
                            "BB위치": "",
                            "MA20": 0,
                            "MA60": 0,
                            "BB상단": 0,
                            "BB하단": 0
                        })

                df_tech = pd.DataFrame(tech_data)
                df_tech.to_excel(writer, sheet_name='기술적분석', index=False)

            # ========== 5. 제외 종목 시트 ==========
            excluded_data = []
            for score in result.all_scores:
                if not score.passed_filter:
                    excluded_data.append({
                        "종목코드": score.code,
                        "종목명": score.name,
                        "제외사유": score.filter_reason,
                        "PER": round(score.per, 2) if score.per else 0,
                        "PBR": round(score.pbr, 2) if score.pbr else 0,
                        "ROE": round(score.roe, 2) if score.roe else 0,
                        "부채비율": round(score.debt_ratio, 2) if score.debt_ratio else 0,
                        "12M수익률": round(score.return_12m, 2) if score.return_12m else 0
                    })

            if excluded_data:
                df_excluded = pd.DataFrame(excluded_data)
                df_excluded.to_excel(writer, sheet_name='제외종목', index=False)

        logger.info(f"스크리닝 결과 엑셀 저장: {filepath}")
        return filepath
