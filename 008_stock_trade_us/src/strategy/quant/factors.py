"""
멀티팩터 계산 엔진
- 가치, 모멘텀, 퀄리티 팩터 점수 계산
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import statistics


class FactorType(Enum):
    """팩터 유형"""
    VALUE = "value"
    MOMENTUM = "momentum"
    QUALITY = "quality"


@dataclass
class FactorScore:
    """개별 팩터 점수"""
    factor_type: FactorType
    score: float  # 0~100
    rank: int = 0
    percentile: float = 0.0
    details: Dict[str, float] = field(default_factory=dict)


@dataclass
class CompositeScore:
    """복합 점수"""
    code: str
    name: str
    value_score: float = 0.0
    momentum_score: float = 0.0
    quality_score: float = 0.0
    composite_score: float = 0.0
    rank: int = 0

    # 상세 데이터
    per: float = 0.0
    pbr: float = 0.0
    roe: float = 0.0
    return_12m: float = 0.0
    return_6m: float = 0.0
    distance_from_high: float = 0.0
    debt_ratio: float = 0.0

    # 필터 통과 여부
    passed_filter: bool = True
    filter_reason: str = ""


class FactorWeights:
    """팩터 가중치 설정"""

    # 팩터별 비중
    VALUE_WEIGHT = 0.40
    MOMENTUM_WEIGHT = 0.30
    QUALITY_WEIGHT = 0.30

    # 가치 팩터 내부 가중치
    VALUE_PER_WEIGHT = 0.35
    VALUE_PBR_WEIGHT = 0.35
    VALUE_PSR_WEIGHT = 0.15
    VALUE_DIVIDEND_WEIGHT = 0.15

    # 모멘텀 팩터 내부 가중치
    MOM_12M_WEIGHT = 0.40
    MOM_6M_WEIGHT = 0.30
    MOM_3M_WEIGHT = 0.20
    MOM_1M_WEIGHT = 0.10

    # 퀄리티 팩터 내부 가중치
    QUALITY_ROE_WEIGHT = 0.35
    QUALITY_MARGIN_WEIGHT = 0.25
    QUALITY_DEBT_WEIGHT = 0.25
    QUALITY_GROWTH_WEIGHT = 0.15


class ValueFactorCalculator:
    """가치 팩터 계산기"""

    # 필터 기준
    PER_MIN = 0
    PER_MAX = 50
    PBR_MIN = 0.1
    PBR_MAX = 10

    @staticmethod
    def calculate(
        per: float,
        pbr: float,
        psr: float = 0.0,
        dividend_yield: float = 0.0,
        all_per: List[float] = None,
        all_pbr: List[float] = None
    ) -> FactorScore:
        """
        가치 점수 계산

        낮을수록 저평가 → 높은 점수
        """
        score = 50.0  # 기본 점수
        details = {}

        # 유효성 검증
        if per <= 0 or per > 100:
            return FactorScore(
                factor_type=FactorType.VALUE,
                score=0,
                details={"error": "Invalid PER"}
            )

        # PER 점수 (낮을수록 좋음)
        if per < 8:
            per_score = 25
        elif per < 12:
            per_score = 20
        elif per < 15:
            per_score = 15
        elif per < 20:
            per_score = 10
        elif per < 30:
            per_score = 5
        else:
            per_score = -10

        details["per_contribution"] = per_score
        score += per_score * FactorWeights.VALUE_PER_WEIGHT * 2

        # PBR 점수 (낮을수록 좋음)
        if pbr < 0.5:
            pbr_score = 25
        elif pbr < 0.8:
            pbr_score = 20
        elif pbr < 1.0:
            pbr_score = 15
        elif pbr < 1.5:
            pbr_score = 10
        elif pbr < 2.5:
            pbr_score = 5
        else:
            pbr_score = -10

        details["pbr_contribution"] = pbr_score
        score += pbr_score * FactorWeights.VALUE_PBR_WEIGHT * 2

        # PSR 점수 (있는 경우)
        if psr > 0:
            if psr < 0.5:
                psr_score = 15
            elif psr < 1.0:
                psr_score = 10
            elif psr < 2.0:
                psr_score = 5
            else:
                psr_score = 0

            details["psr_contribution"] = psr_score
            score += psr_score * FactorWeights.VALUE_PSR_WEIGHT

        # 배당수익률 점수
        if dividend_yield > 0:
            if dividend_yield > 5:
                div_score = 15
            elif dividend_yield > 3:
                div_score = 10
            elif dividend_yield > 2:
                div_score = 5
            else:
                div_score = 2

            details["dividend_contribution"] = div_score
            score += div_score * FactorWeights.VALUE_DIVIDEND_WEIGHT

        # 점수 정규화 (0~100)
        final_score = max(0, min(100, score))

        details["per"] = per
        details["pbr"] = pbr
        details["psr"] = psr
        details["dividend_yield"] = dividend_yield

        return FactorScore(
            factor_type=FactorType.VALUE,
            score=final_score,
            details=details
        )


class MomentumFactorCalculator:
    """모멘텀 팩터 계산기"""

    @staticmethod
    def calculate(
        return_1m: float,
        return_3m: float,
        return_6m: float,
        return_12m: float,
        distance_from_high: float = 0.0,
        volatility: float = 0.0
    ) -> FactorScore:
        """
        모멘텀 점수 계산

        상승률이 높을수록 → 높은 점수
        단, 단기 과열 시 페널티
        """
        score = 50.0
        details = {}

        # 12개월 수익률 점수
        if return_12m > 50:
            r12_score = 25
        elif return_12m > 30:
            r12_score = 20
        elif return_12m > 15:
            r12_score = 15
        elif return_12m > 0:
            r12_score = 10
        elif return_12m > -10:
            r12_score = 5
        else:
            r12_score = -15

        details["return_12m_contribution"] = r12_score
        score += r12_score * FactorWeights.MOM_12M_WEIGHT * 2

        # 6개월 수익률 점수
        if return_6m > 30:
            r6_score = 20
        elif return_6m > 15:
            r6_score = 15
        elif return_6m > 5:
            r6_score = 10
        elif return_6m > -5:
            r6_score = 5
        else:
            r6_score = -10

        details["return_6m_contribution"] = r6_score
        score += r6_score * FactorWeights.MOM_6M_WEIGHT * 2

        # 3개월 수익률 점수
        if return_3m > 20:
            r3_score = 15
        elif return_3m > 10:
            r3_score = 10
        elif return_3m > 0:
            r3_score = 5
        else:
            r3_score = -5

        details["return_3m_contribution"] = r3_score
        score += r3_score * FactorWeights.MOM_3M_WEIGHT * 2

        # 52주 고점 근접도 보너스
        if distance_from_high > -5:  # 고점 대비 -5% 이내
            score += 10
            details["near_high_bonus"] = 10
        elif distance_from_high < -30:  # 고점 대비 -30% 이상 하락
            score -= 10
            details["far_from_high_penalty"] = -10

        # 단기 과열 페널티 (1개월 급등)
        if return_1m > 25:
            penalty = -15
            score += penalty
            details["short_term_overheat_penalty"] = penalty
        elif return_1m > 15:
            penalty = -5
            score += penalty
            details["short_term_overheat_penalty"] = penalty

        # 변동성 조정 (높은 변동성은 약간의 페널티)
        if volatility > 50:
            vol_penalty = -5
            score += vol_penalty
            details["high_volatility_penalty"] = vol_penalty

        final_score = max(0, min(100, score))

        details["return_1m"] = return_1m
        details["return_3m"] = return_3m
        details["return_6m"] = return_6m
        details["return_12m"] = return_12m
        details["distance_from_high"] = distance_from_high
        details["volatility"] = volatility

        return FactorScore(
            factor_type=FactorType.MOMENTUM,
            score=final_score,
            details=details
        )


class QualityFactorCalculator:
    """퀄리티 팩터 계산기"""

    @staticmethod
    def calculate(
        roe: float,
        operating_margin: float = 0.0,
        debt_ratio: float = 0.0,
        eps_growth: float = 0.0
    ) -> FactorScore:
        """
        퀄리티 점수 계산

        ROE, 영업이익률 높을수록 → 높은 점수
        부채비율 낮을수록 → 높은 점수
        """
        score = 50.0
        details = {}

        # ROE 점수 (높을수록 좋음)
        if roe > 20:
            roe_score = 25
        elif roe > 15:
            roe_score = 20
        elif roe > 10:
            roe_score = 15
        elif roe > 5:
            roe_score = 10
        elif roe > 0:
            roe_score = 5
        else:
            roe_score = -15  # 적자

        details["roe_contribution"] = roe_score
        score += roe_score * FactorWeights.QUALITY_ROE_WEIGHT * 2

        # 영업이익률 점수
        if operating_margin > 20:
            margin_score = 20
        elif operating_margin > 15:
            margin_score = 15
        elif operating_margin > 10:
            margin_score = 10
        elif operating_margin > 5:
            margin_score = 5
        elif operating_margin > 0:
            margin_score = 0
        else:
            margin_score = -10  # 영업적자

        details["margin_contribution"] = margin_score
        score += margin_score * FactorWeights.QUALITY_MARGIN_WEIGHT * 2

        # 부채비율 점수 (낮을수록 좋음)
        if debt_ratio < 30:
            debt_score = 20
        elif debt_ratio < 50:
            debt_score = 15
        elif debt_ratio < 80:
            debt_score = 10
        elif debt_ratio < 100:
            debt_score = 5
        elif debt_ratio < 150:
            debt_score = 0
        else:
            debt_score = -10

        details["debt_contribution"] = debt_score
        score += debt_score * FactorWeights.QUALITY_DEBT_WEIGHT * 2

        # EPS 성장률 점수
        if eps_growth > 30:
            growth_score = 15
        elif eps_growth > 15:
            growth_score = 10
        elif eps_growth > 5:
            growth_score = 5
        elif eps_growth > 0:
            growth_score = 2
        else:
            growth_score = 0

        details["growth_contribution"] = growth_score
        score += growth_score * FactorWeights.QUALITY_GROWTH_WEIGHT

        final_score = max(0, min(100, score))

        details["roe"] = roe
        details["operating_margin"] = operating_margin
        details["debt_ratio"] = debt_ratio
        details["eps_growth"] = eps_growth

        return FactorScore(
            factor_type=FactorType.QUALITY,
            score=final_score,
            details=details
        )


class CompositeScoreCalculator:
    """복합 점수 계산기"""

    # 기본 필터 기준
    FILTER_CRITERIA = {
        "per_min": 0,
        "per_max": 50,
        "pbr_min": 0.1,
        "pbr_max": 10,
        "roe_min": -10,  # 적자 허용 범위
        "debt_ratio_max": 300,
        "return_12m_min": -30,
        "market_cap_min": 1000,  # 시가총액 1000억 이상
    }

    def __init__(
        self,
        value_weight: float = FactorWeights.VALUE_WEIGHT,
        momentum_weight: float = FactorWeights.MOMENTUM_WEIGHT,
        quality_weight: float = FactorWeights.QUALITY_WEIGHT
    ):
        self.value_weight = value_weight
        self.momentum_weight = momentum_weight
        self.quality_weight = quality_weight

        self.value_calc = ValueFactorCalculator()
        self.momentum_calc = MomentumFactorCalculator()
        self.quality_calc = QualityFactorCalculator()

    def passes_basic_filter(
        self,
        per: float,
        pbr: float,
        roe: float,
        debt_ratio: float,
        return_12m: float,
        market_cap: int = 0
    ) -> Tuple[bool, str]:
        """
        기본 필터 통과 여부 확인

        Returns:
            (통과 여부, 실패 사유)
        """
        criteria = self.FILTER_CRITERIA

        # PER 필터
        if per <= criteria["per_min"]:
            return False, f"PER({per:.1f}) <= 0 (적자)"
        if per > criteria["per_max"]:
            return False, f"PER({per:.1f}) > {criteria['per_max']} (고평가)"

        # PBR 필터
        if pbr < criteria["pbr_min"]:
            return False, f"PBR({pbr:.2f}) < {criteria['pbr_min']} (자본잠식 의심)"
        if pbr > criteria["pbr_max"]:
            return False, f"PBR({pbr:.2f}) > {criteria['pbr_max']} (고평가)"

        # ROE 필터
        if roe < criteria["roe_min"]:
            return False, f"ROE({roe:.1f}%) < {criteria['roe_min']}% (심각한 적자)"

        # 부채비율 필터
        if debt_ratio > criteria["debt_ratio_max"]:
            return False, f"부채비율({debt_ratio:.0f}%) > {criteria['debt_ratio_max']}%"

        # 모멘텀 필터
        if return_12m < criteria["return_12m_min"]:
            return False, f"12개월 수익률({return_12m:.1f}%) < {criteria['return_12m_min']}%"

        # 시가총액 필터
        if market_cap > 0 and market_cap < criteria["market_cap_min"]:
            return False, f"시가총액({market_cap}억) < {criteria['market_cap_min']}억"

        return True, ""

    def calculate(
        self,
        code: str,
        name: str,
        # 가치 데이터
        per: float,
        pbr: float,
        psr: float = 0.0,
        dividend_yield: float = 0.0,
        # 모멘텀 데이터
        return_1m: float = 0.0,
        return_3m: float = 0.0,
        return_6m: float = 0.0,
        return_12m: float = 0.0,
        distance_from_high: float = 0.0,
        volatility: float = 0.0,
        # 퀄리티 데이터
        roe: float = 0.0,
        operating_margin: float = 0.0,
        debt_ratio: float = 0.0,
        eps_growth: float = 0.0,
        # 추가 데이터
        market_cap: int = 0
    ) -> CompositeScore:
        """
        복합 점수 계산
        """
        # 기본 필터 확인
        passed, reason = self.passes_basic_filter(
            per=per,
            pbr=pbr,
            roe=roe,
            debt_ratio=debt_ratio,
            return_12m=return_12m,
            market_cap=market_cap
        )

        if not passed:
            return CompositeScore(
                code=code,
                name=name,
                passed_filter=False,
                filter_reason=reason,
                per=per,
                pbr=pbr,
                roe=roe,
                return_12m=return_12m,
                debt_ratio=debt_ratio
            )

        # 각 팩터 점수 계산
        value_factor = self.value_calc.calculate(
            per=per,
            pbr=pbr,
            psr=psr,
            dividend_yield=dividend_yield
        )

        momentum_factor = self.momentum_calc.calculate(
            return_1m=return_1m,
            return_3m=return_3m,
            return_6m=return_6m,
            return_12m=return_12m,
            distance_from_high=distance_from_high,
            volatility=volatility
        )

        quality_factor = self.quality_calc.calculate(
            roe=roe,
            operating_margin=operating_margin,
            debt_ratio=debt_ratio,
            eps_growth=eps_growth
        )

        # 복합 점수 계산
        composite = (
            value_factor.score * self.value_weight +
            momentum_factor.score * self.momentum_weight +
            quality_factor.score * self.quality_weight
        )

        # 보너스/페널티
        bonus = 0

        # 모든 팩터 상위 50% 이상이면 보너스
        if all(s >= 50 for s in [value_factor.score, momentum_factor.score, quality_factor.score]):
            bonus += 5

        # 어떤 팩터든 하위 20%면 페널티
        if min(value_factor.score, momentum_factor.score, quality_factor.score) < 20:
            bonus -= 10

        final_composite = max(0, min(100, composite + bonus))

        return CompositeScore(
            code=code,
            name=name,
            value_score=value_factor.score,
            momentum_score=momentum_factor.score,
            quality_score=quality_factor.score,
            composite_score=final_composite,
            passed_filter=True,
            per=per,
            pbr=pbr,
            roe=roe,
            return_12m=return_12m,
            return_6m=return_6m,
            distance_from_high=distance_from_high,
            debt_ratio=debt_ratio
        )

    def rank_stocks(self, scores: List[CompositeScore]) -> List[CompositeScore]:
        """
        종목 순위 매기기
        """
        # 필터 통과한 종목만
        passed = [s for s in scores if s.passed_filter]

        # 복합 점수 기준 정렬
        passed.sort(key=lambda x: x.composite_score, reverse=True)

        # 순위 부여
        for i, score in enumerate(passed, 1):
            score.rank = i

        return passed
