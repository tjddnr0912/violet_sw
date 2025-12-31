"""
미국 주식 멀티팩터 스크리너
- 모멘텀 + 저변동성 + 가치 팩터 기반 종목 선정
- 미국 시장 특성에 맞게 조정된 기준값
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .us_universe import USUniverseBuilder, USDataCollector, USStock

logger = logging.getLogger(__name__)


# ========== 데이터 클래스 ==========

@dataclass
class USFactorScore:
    """미국 주식 팩터 점수"""
    symbol: str
    name: str

    # 팩터 점수 (0~100)
    momentum_score: float = 0.0
    short_momentum_score: float = 0.0
    volatility_score: float = 0.0
    volume_score: float = 0.0
    value_score: float = 0.0

    # 복합 점수
    composite_score: float = 0.0
    rank: int = 0

    # 상세 데이터
    return_12m: float = 0.0
    return_6m: float = 0.0
    return_3m: float = 0.0
    return_1m: float = 0.0
    volatility: float = 0.0
    avg_volume: int = 0
    per: float = 0.0
    pbr: float = 0.0
    market_cap: float = 0.0  # 십억 달러

    # 필터
    passed_filter: bool = True
    filter_reason: str = ""

    # 섹터 정보
    sector: str = ""
    exchange: str = ""


@dataclass
class USFactorWeights:
    """팩터 가중치 설정 (미국 시장 최적화)"""
    momentum_weight: float = 0.20      # 12개월 모멘텀
    short_mom_weight: float = 0.10     # 단기 모멘텀 (1-3개월)
    volatility_weight: float = 0.50    # 저변동성 (가장 중요)
    volume_weight: float = 0.00        # 거래량 (비활성화)
    value_weight: float = 0.20         # 가치 (PER, PBR)

    # 필터 기준 (미국 시장)
    per_min: float = 0
    per_max: float = 100               # 미국은 PER이 높은 편
    pbr_max: float = 15                # 미국 PBR 허용 범위 확대
    min_market_cap: float = 1.0        # 최소 시가총액 (십억 달러)
    min_avg_volume: int = 500_000      # 최소 평균 거래량
    max_volatility: float = 80         # 최대 변동성 (%)
    min_return_12m: float = -50        # 최소 12개월 수익률


class USMomentumCalculator:
    """모멘텀 팩터 계산기"""

    @staticmethod
    def calculate_returns(df: pd.DataFrame) -> Dict[str, float]:
        """
        수익률 계산

        Args:
            df: 가격 데이터 (date, close)

        Returns:
            수익률 딕셔너리
        """
        if df.empty or len(df) < 5:
            return {
                "return_1m": 0,
                "return_3m": 0,
                "return_6m": 0,
                "return_12m": 0
            }

        df = df.sort_values('date').reset_index(drop=True)
        current_price = df['close'].iloc[-1]

        returns = {}

        # 1개월 (약 21 거래일)
        if len(df) >= 21:
            price_1m = df['close'].iloc[-21]
            returns["return_1m"] = (current_price / price_1m - 1) * 100
        else:
            returns["return_1m"] = 0

        # 3개월 (약 63 거래일)
        if len(df) >= 63:
            price_3m = df['close'].iloc[-63]
            returns["return_3m"] = (current_price / price_3m - 1) * 100
        else:
            returns["return_3m"] = 0

        # 6개월 (약 126 거래일)
        if len(df) >= 126:
            price_6m = df['close'].iloc[-126]
            returns["return_6m"] = (current_price / price_6m - 1) * 100
        else:
            returns["return_6m"] = returns.get("return_3m", 0) * 2

        # 12개월 (약 252 거래일)
        if len(df) >= 252:
            price_12m = df['close'].iloc[-252]
            returns["return_12m"] = (current_price / price_12m - 1) * 100
        elif len(df) >= 126:
            returns["return_12m"] = returns.get("return_6m", 0) * 2
        else:
            returns["return_12m"] = returns.get("return_3m", 0) * 4

        return returns

    @staticmethod
    def score_momentum(return_12m: float, return_6m: float) -> float:
        """
        12개월 모멘텀 점수 계산 (0~100)
        """
        score = 50.0

        # 12개월 수익률 점수
        if return_12m > 100:
            score += 35
        elif return_12m > 50:
            score += 25
        elif return_12m > 30:
            score += 20
        elif return_12m > 15:
            score += 15
        elif return_12m > 0:
            score += 10
        elif return_12m > -15:
            score += 0
        elif return_12m > -30:
            score -= 15
        else:
            score -= 30

        # 6개월 추세 확인 (보너스/페널티)
        if return_6m > 0 and return_12m > 0:
            score += 5  # 지속적 상승
        elif return_6m < 0 and return_12m > 0:
            score -= 5  # 상승 둔화

        return max(0, min(100, score))

    @staticmethod
    def score_short_momentum(return_1m: float, return_3m: float) -> float:
        """
        단기 모멘텀 점수 계산 (0~100)
        """
        score = 50.0

        # 3개월 수익률
        if return_3m > 30:
            score += 20
        elif return_3m > 15:
            score += 15
        elif return_3m > 5:
            score += 10
        elif return_3m > 0:
            score += 5
        elif return_3m > -10:
            score -= 5
        else:
            score -= 15

        # 1개월 과열 체크
        if return_1m > 30:
            score -= 10  # 단기 과열 페널티
        elif return_1m > 20:
            score -= 5

        return max(0, min(100, score))


class USVolatilityCalculator:
    """저변동성 팩터 계산기"""

    @staticmethod
    def calculate_volatility(df: pd.DataFrame, days: int = 60) -> float:
        """
        변동성 계산 (연간화 표준편차)

        Args:
            df: 가격 데이터 (date, close)
            days: 계산 기간

        Returns:
            연간화 변동성 (%)
        """
        if df.empty or len(df) < 5:
            return 50.0  # 기본값

        df = df.sort_values('date').tail(days)

        if len(df) < 5:
            return 50.0

        # 일간 수익률
        returns = df['close'].pct_change().dropna()

        if len(returns) < 2:
            return 50.0

        # 연간화 변동성 (252 거래일 기준)
        volatility = returns.std() * np.sqrt(252) * 100

        return volatility

    @staticmethod
    def score_volatility(volatility: float) -> float:
        """
        저변동성 점수 계산 (변동성이 낮을수록 높은 점수)

        미국 시장 평균 변동성: 약 20-25%
        """
        if volatility <= 0:
            return 50.0

        # 변동성이 낮을수록 높은 점수
        if volatility < 15:
            return 95
        elif volatility < 20:
            return 85
        elif volatility < 25:
            return 75
        elif volatility < 30:
            return 65
        elif volatility < 35:
            return 55
        elif volatility < 40:
            return 45
        elif volatility < 50:
            return 35
        elif volatility < 60:
            return 25
        else:
            return 10


class USValueCalculator:
    """가치 팩터 계산기 (미국 시장 조정)"""

    @staticmethod
    def score_value(per: float, pbr: float, dividend_yield: float = 0) -> float:
        """
        가치 점수 계산 (0~100)

        미국 시장 특성:
        - S&P 500 평균 PER: 약 20-25
        - 성장주 중심이라 PER이 높은 편
        """
        score = 50.0

        # PER 점수 (미국 시장 조정)
        if 0 < per < 10:
            score += 20
        elif per < 15:
            score += 15
        elif per < 20:
            score += 10
        elif per < 25:
            score += 5
        elif per < 35:
            score += 0
        elif per < 50:
            score -= 5
        elif per < 100:
            score -= 15
        else:
            score -= 25  # 매우 고평가

        # PBR 점수
        if 0 < pbr < 1.5:
            score += 15
        elif pbr < 3:
            score += 10
        elif pbr < 5:
            score += 5
        elif pbr < 8:
            score += 0
        elif pbr < 12:
            score -= 5
        else:
            score -= 15

        # 배당수익률 보너스 (미국은 배당이 낮은 편)
        if dividend_yield > 3:
            score += 10
        elif dividend_yield > 2:
            score += 5
        elif dividend_yield > 1:
            score += 2

        return max(0, min(100, score))


class USMultiFactorScreener:
    """미국 주식 멀티팩터 스크리너"""

    def __init__(
        self,
        weights: USFactorWeights = None,
        kis_client=None
    ):
        """
        Args:
            weights: 팩터 가중치 설정
            kis_client: KIS US 클라이언트
        """
        self.weights = weights or USFactorWeights()
        self.universe_builder = USUniverseBuilder()
        self.data_collector = USDataCollector(kis_client)

    def screen(
        self,
        universe_type: str = "sp500",
        universe_size: int = 100,
        target_count: int = 15
    ) -> List[USFactorScore]:
        """
        멀티팩터 스크리닝 실행

        Args:
            universe_type: 유니버스 유형 ("sp500", "nasdaq100")
            universe_size: 분석할 종목 수
            target_count: 선정할 종목 수

        Returns:
            팩터 점수 리스트 (순위순)
        """
        logger.info(f"미국 주식 스크리닝 시작: {universe_type} ({universe_size}개)")

        # 1. 유니버스 구성
        universe = self.universe_builder.build_universe(
            universe_type=universe_type,
            size=universe_size
        )

        logger.info(f"유니버스 {len(universe)}개 종목 로드")

        # 2. 각 종목 분석
        scores = []
        for stock in universe:
            try:
                score = self._analyze_stock(stock)
                if score:
                    scores.append(score)
            except Exception as e:
                logger.warning(f"종목 분석 실패 ({stock.symbol}): {e}")
                continue

        logger.info(f"분석 완료: {len(scores)}개 종목")

        # 3. 필터링
        filtered = [s for s in scores if s.passed_filter]
        logger.info(f"필터 통과: {len(filtered)}개 종목")

        # 4. 섹터 분산 적용
        diversified = self._apply_sector_diversification(filtered, target_count)

        # 5. 순위 부여
        for i, score in enumerate(diversified, 1):
            score.rank = i

        logger.info(f"최종 선정: {len(diversified)}개 종목")

        return diversified

    def _analyze_stock(self, stock: USStock) -> Optional[USFactorScore]:
        """
        개별 종목 분석

        Args:
            stock: 종목 정보

        Returns:
            팩터 점수
        """
        # 가격 데이터 조회
        df = self.data_collector.get_price_data(stock.symbol, days=260)

        if df.empty or len(df) < 20:
            # Yahoo Finance 폴백
            df = self.data_collector.get_price_data_yahoo(stock.symbol, days=260)

        if df.empty or len(df) < 20:
            return None

        # 펀더멘털 데이터 조회
        fundamental = self.data_collector.get_fundamental_data(stock.symbol)

        if not fundamental:
            fundamental = self.data_collector.get_fundamental_data_yahoo(stock.symbol)

        # 수익률 계산
        returns = USMomentumCalculator.calculate_returns(df)

        # 변동성 계산
        volatility = USVolatilityCalculator.calculate_volatility(df)

        # 거래량
        avg_volume = int(df['volume'].tail(20).mean()) if 'volume' in df.columns else 0

        # 펀더멘털 데이터 추출
        per = fundamental.get("per", 0) or 0
        pbr = fundamental.get("pbr", 0) or 0
        market_cap = fundamental.get("market_cap", 0) or 0
        dividend_yield = fundamental.get("dividend_yield", 0) or 0

        # 필터 체크
        passed, reason = self._check_filters(
            per=per,
            pbr=pbr,
            market_cap=market_cap,
            avg_volume=avg_volume,
            volatility=volatility,
            return_12m=returns["return_12m"]
        )

        # 팩터 점수 계산
        momentum_score = USMomentumCalculator.score_momentum(
            returns["return_12m"], returns["return_6m"]
        )
        short_mom_score = USMomentumCalculator.score_short_momentum(
            returns["return_1m"], returns["return_3m"]
        )
        volatility_score = USVolatilityCalculator.score_volatility(volatility)
        value_score = USValueCalculator.score_value(per, pbr, dividend_yield)

        # 거래량 점수 (현재 비활성화)
        volume_score = 50.0

        # 복합 점수 계산
        composite = (
            momentum_score * self.weights.momentum_weight +
            short_mom_score * self.weights.short_mom_weight +
            volatility_score * self.weights.volatility_weight +
            volume_score * self.weights.volume_weight +
            value_score * self.weights.value_weight
        )

        return USFactorScore(
            symbol=stock.symbol,
            name=stock.name,
            momentum_score=momentum_score,
            short_momentum_score=short_mom_score,
            volatility_score=volatility_score,
            volume_score=volume_score,
            value_score=value_score,
            composite_score=composite,
            return_12m=returns["return_12m"],
            return_6m=returns["return_6m"],
            return_3m=returns["return_3m"],
            return_1m=returns["return_1m"],
            volatility=volatility,
            avg_volume=avg_volume,
            per=per,
            pbr=pbr,
            market_cap=market_cap,
            sector=stock.sector,
            exchange=stock.exchange,
            passed_filter=passed,
            filter_reason=reason
        )

    def _check_filters(
        self,
        per: float,
        pbr: float,
        market_cap: float,
        avg_volume: int,
        volatility: float,
        return_12m: float
    ) -> Tuple[bool, str]:
        """
        필터 체크

        Returns:
            (통과 여부, 실패 사유)
        """
        w = self.weights

        # PER 필터
        if per > 0 and per > w.per_max:
            return False, f"PER({per:.1f}) > {w.per_max}"

        # PBR 필터
        if pbr > w.pbr_max:
            return False, f"PBR({pbr:.1f}) > {w.pbr_max}"

        # 시가총액 필터
        if market_cap > 0 and market_cap < w.min_market_cap:
            return False, f"시가총액(${market_cap:.1f}B) < ${w.min_market_cap}B"

        # 거래량 필터
        if avg_volume > 0 and avg_volume < w.min_avg_volume:
            return False, f"거래량({avg_volume:,}) < {w.min_avg_volume:,}"

        # 변동성 필터
        if volatility > w.max_volatility:
            return False, f"변동성({volatility:.1f}%) > {w.max_volatility}%"

        # 모멘텀 필터
        if return_12m < w.min_return_12m:
            return False, f"12M수익률({return_12m:.1f}%) < {w.min_return_12m}%"

        return True, ""

    def _apply_sector_diversification(
        self,
        scores: List[USFactorScore],
        target_count: int,
        max_per_sector: int = 3
    ) -> List[USFactorScore]:
        """
        섹터 분산 적용

        Args:
            scores: 팩터 점수 리스트
            target_count: 목표 종목 수
            max_per_sector: 섹터별 최대 종목 수

        Returns:
            분산된 종목 리스트
        """
        # 복합 점수 기준 정렬
        sorted_scores = sorted(scores, key=lambda x: x.composite_score, reverse=True)

        selected = []
        sector_count = {}

        for score in sorted_scores:
            if len(selected) >= target_count:
                break

            sector = score.sector or "Unknown"
            current_count = sector_count.get(sector, 0)

            if current_count < max_per_sector:
                selected.append(score)
                sector_count[sector] = current_count + 1

        return selected


# ========== 편의 함수 ==========

def run_screening(
    universe_type: str = "sp500",
    universe_size: int = 100,
    target_count: int = 15,
    weights: USFactorWeights = None
) -> List[USFactorScore]:
    """
    스크리닝 실행

    Args:
        universe_type: 유니버스 유형
        universe_size: 분석 종목 수
        target_count: 선정 종목 수
        weights: 팩터 가중치

    Returns:
        팩터 점수 리스트
    """
    screener = USMultiFactorScreener(weights=weights)
    return screener.screen(
        universe_type=universe_type,
        universe_size=universe_size,
        target_count=target_count
    )
