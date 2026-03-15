"""
멀티팩터 계산 엔진
- Cross-Sectional Percentile Ranking 기반 팩터 점수 계산
- 가치, 모멘텀, 퀄리티 팩터
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import statistics
import logging

logger = logging.getLogger(__name__)


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
    volatility: float = 0.0  # 연환산 변동성 (%, ATR 손절용)

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


# ============================================================
# Cross-Sectional Percentile Ranking 유틸리티
# ============================================================

def _percentile_rank(values: List[float], ascending: bool = True) -> List[float]:
    """
    Cross-sectional percentile ranking (0~100)

    Args:
        values: 원시 팩터값 리스트
        ascending: True면 값이 클수록 높은 점수 (ROE, 모멘텀)
                   False면 값이 작을수록 높은 점수 (PER, PBR, 부채비율)

    Returns:
        0~100 사이의 percentile 점수 리스트
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [50.0]

    # (인덱스, 값) 튜플 생성 후 정렬
    indexed = list(enumerate(values))
    indexed.sort(key=lambda x: x[1])

    # 동점 처리: 평균 순위(average rank) 부여
    ranks = [0.0] * n
    i = 0
    while i < n:
        # 동점 그룹 찾기
        j = i
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        # 평균 순위 (0-based)
        avg_rank = (i + j - 1) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j

    # percentile 변환 (0~100)
    result = [0.0] * n
    for idx in range(n):
        pct = ranks[idx] / (n - 1) * 100.0 if n > 1 else 50.0
        if not ascending:
            pct = 100.0 - pct  # 역순위: 값이 작을수록 높은 점수
        result[idx] = pct

    return result


def _winsorize(values: List[float], lower_pct: float = 2.5, upper_pct: float = 97.5) -> List[float]:
    """
    Winsorization: 극단값을 상하위 percentile로 clip

    Args:
        values: 원시값 리스트
        lower_pct: 하위 clip percentile (기본 2.5%)
        upper_pct: 상위 clip percentile (기본 97.5%)

    Returns:
        winsorize 된 값 리스트
    """
    if len(values) < 5:
        return values[:]

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    lower_idx = max(0, int(n * lower_pct / 100))
    upper_idx = min(n - 1, int(n * upper_pct / 100))

    lower_val = sorted_vals[lower_idx]
    upper_val = sorted_vals[upper_idx]

    return [max(lower_val, min(upper_val, v)) for v in values]


# ============================================================
# Batch 팩터 계산기 (Cross-Sectional Percentile)
# ============================================================

class BatchFactorCalculator:
    """
    전체 유니버스를 한번에 받아 Cross-Sectional Percentile Ranking으로 점수 계산.

    P9 개선: 서브팩터 간 상관 관계 관리
    - Value: PER 40% + PBR 20% + PSR 20% + 배당 20% (PER↔PBR 중복 완화)
    - Momentum: 12-1M 모멘텀 50% + 단기 반전 20% + 52주 고점 30% (기간 겹침 제거)
    - Quality: ROE 35% + 영업이익률 25% + 부채비율 25% + EPS 성장 15%
    """

    @staticmethod
    def calculate_value_scores(stocks_data: List[Dict]) -> List[float]:
        """
        가치 팩터 점수 (percentile ranking)

        P9 변경: PER↔PBR 상관(~0.7) 완화
        - PER: 40% (이익 기반 밸류에이션 — 대표 지표)
        - PBR: 20% (자산 기반 — PER과 관점 다르지만 상관 높아 축소)
        - PSR: 20% (매출 기반 — PER/PBR과 독립적 관점, 상향)
        - 배당수익률: 20% (현금흐름 기반 — 독립적, 상향)
        """
        n = len(stocks_data)
        if n == 0:
            return []

        per_vals = _winsorize([d.get("per", 0) for d in stocks_data])
        pbr_vals = _winsorize([d.get("pbr", 0) for d in stocks_data])
        psr_vals = _winsorize([d.get("psr", 0) for d in stocks_data])
        div_vals = _winsorize([d.get("dividend_yield", 0) for d in stocks_data])

        per_pct = _percentile_rank(per_vals, ascending=False)
        pbr_pct = _percentile_rank(pbr_vals, ascending=False)
        psr_pct = _percentile_rank(psr_vals, ascending=False)
        div_pct = _percentile_rank(div_vals, ascending=True)

        # P9: PER↔PBR 중복 완화 가중치
        scores = []
        for i in range(n):
            score = (
                per_pct[i] * 0.40 +
                pbr_pct[i] * 0.20 +
                psr_pct[i] * 0.20 +
                div_pct[i] * 0.20
            )
            scores.append(score)

        return scores

    @staticmethod
    def calculate_momentum_scores(stocks_data: List[Dict]) -> List[float]:
        """
        모멘텀 팩터 점수 (percentile ranking)

        P9 변경: 12M/6M/3M 겹침 제거 → 독립 구간 모멘텀
        - 12-1M 모멘텀 (50%): 최근 1개월 제외 12개월 수익률
          (Jegadeesh & Titman 표준, 단기 반전 효과 분리)
        - 1M 반전 (20%): 단기 반전(mean-reversion) 신호
          최근 1개월 수익률의 역순위 → 단기 과열 매수 방지
        - 52주 고점 근접도 (30%): 추세 강도의 독립 지표
        """
        n = len(stocks_data)
        if n == 0:
            return []

        # 12-1M 모멘텀: 12개월 수익률에서 1개월 수익률 차감 (근사)
        r12m_vals = [d.get("return_12m", 0) for d in stocks_data]
        r1m_vals = [d.get("return_1m", 0) for d in stocks_data]
        r12_1m_vals = _winsorize([r12 - r1 for r12, r1 in zip(r12m_vals, r1m_vals)])

        # 1M 반전: 단기 과매수를 피하기 위해 역순위
        r1m_winsorized = _winsorize(r1m_vals)

        # 52주 고점 근접도
        high_vals = _winsorize([d.get("distance_from_high", 0) for d in stocks_data])

        r12_1m_pct = _percentile_rank(r12_1m_vals, ascending=True)
        r1m_reversal_pct = _percentile_rank(r1m_winsorized, ascending=False)  # 역순위
        high_pct = _percentile_rank(high_vals, ascending=True)

        scores = []
        for i in range(n):
            score = (
                r12_1m_pct[i] * 0.50 +
                r1m_reversal_pct[i] * 0.20 +
                high_pct[i] * 0.30
            )
            scores.append(score)

        return scores

    @staticmethod
    def calculate_quality_scores(stocks_data: List[Dict]) -> List[float]:
        """
        퀄리티 팩터 점수 (percentile ranking)

        Sub-factors (변경 없음 — 상관 낮음):
        - ROE (35%): 수익성
        - 영업이익률 (25%): 본업 수익성
        - 부채비율 (25%): 재무 안정성 (역순위)
        - EPS 성장률 (15%): 성장성
        """
        n = len(stocks_data)
        if n == 0:
            return []

        roe_vals = _winsorize([d.get("roe", 0) for d in stocks_data])
        margin_vals = _winsorize([d.get("operating_margin", 0) for d in stocks_data])
        debt_vals = _winsorize([d.get("debt_ratio", 0) for d in stocks_data])
        growth_vals = _winsorize([d.get("eps_growth", 0) for d in stocks_data])

        roe_pct = _percentile_rank(roe_vals, ascending=True)
        margin_pct = _percentile_rank(margin_vals, ascending=True)
        debt_pct = _percentile_rank(debt_vals, ascending=False)
        growth_pct = _percentile_rank(growth_vals, ascending=True)

        w = FactorWeights
        scores = []
        for i in range(n):
            score = (
                roe_pct[i] * w.QUALITY_ROE_WEIGHT +
                margin_pct[i] * w.QUALITY_MARGIN_WEIGHT +
                debt_pct[i] * w.QUALITY_DEBT_WEIGHT +
                growth_pct[i] * w.QUALITY_GROWTH_WEIGHT
            )
            scores.append(score)

        return scores

    @staticmethod
    def calculate_volume_scores(stocks_data: List[Dict]) -> List[float]:
        """
        거래량/유동성 팩터 점수 (percentile ranking)

        P6: 기존 API 데이터로 확보 가능한 알파 팩터.
        거래량이 높은 종목은 유동성이 좋고, 시장 관심도가 높음.
        다만 거래량만으로는 방향성이 없으므로,
        거래량 + 변동성의 역수(= 유동성 품질)를 조합.

        Sub-factors:
        - 평균 거래량 (50%): 높을수록 좋음 (유동성)
        - 저변동성 (50%): 낮을수록 좋음 (안정적 유동성)

        Returns:
            각 종목의 Volume/Liquidity 점수 리스트 (0~100)
        """
        n = len(stocks_data)
        if n == 0:
            return []

        vol_vals = _winsorize([d.get("avg_volume", 0) for d in stocks_data])
        volatility_vals = _winsorize([d.get("volatility", 0) for d in stocks_data])

        vol_pct = _percentile_rank(vol_vals, ascending=True)  # 거래량 높을수록 좋음
        low_vol_pct = _percentile_rank(volatility_vals, ascending=False)  # 변동성 낮을수록 좋음

        scores = []
        for i in range(n):
            score = vol_pct[i] * 0.50 + low_vol_pct[i] * 0.50
            scores.append(score)

        return scores

    @staticmethod
    def compute_factor_correlations(stocks_data: List[Dict]) -> Dict[str, float]:
        """
        서브팩터 간 상관계수 계산 (모니터링용)

        Returns:
            주요 팩터 쌍의 상관계수 딕셔너리
        """
        if len(stocks_data) < 10:
            return {}

        def _corr(a: List[float], b: List[float]) -> float:
            """피어슨 상관계수 (표준 라이브러리만 사용)"""
            n = len(a)
            if n < 3:
                return 0.0
            mean_a = sum(a) / n
            mean_b = sum(b) / n
            cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / n
            std_a = (sum((x - mean_a) ** 2 for x in a) / n) ** 0.5
            std_b = (sum((x - mean_b) ** 2 for x in b) / n) ** 0.5
            if std_a == 0 or std_b == 0:
                return 0.0
            return cov / (std_a * std_b)

        per = [d.get("per", 0) for d in stocks_data]
        pbr = [d.get("pbr", 0) for d in stocks_data]
        psr = [d.get("psr", 0) for d in stocks_data]
        roe = [d.get("roe", 0) for d in stocks_data]
        margin = [d.get("operating_margin", 0) for d in stocks_data]
        r12m = [d.get("return_12m", 0) for d in stocks_data]
        r6m = [d.get("return_6m", 0) for d in stocks_data]
        r3m = [d.get("return_3m", 0) for d in stocks_data]
        debt = [d.get("debt_ratio", 0) for d in stocks_data]

        correlations = {
            "PER↔PBR": round(_corr(per, pbr), 3),
            "PER↔PSR": round(_corr(per, psr), 3),
            "ROE↔영업이익률": round(_corr(roe, margin), 3),
            "12M↔6M 수익률": round(_corr(r12m, r6m), 3),
            "6M↔3M 수익률": round(_corr(r6m, r3m), 3),
            "PER↔ROE": round(_corr(per, roe), 3),
            "부채비율↔ROE": round(_corr(debt, roe), 3),
        }

        # 높은 상관 경고
        for pair, corr in correlations.items():
            if abs(corr) > 0.7:
                logger.warning(f"팩터 상관 경고: {pair} = {corr:.3f} (>0.7)")

        return correlations


# ============================================================
# 기존 호환 레이어 (개별 종목 계산 — 레거시)
# ============================================================

class ValueFactorCalculator:
    """가치 팩터 계산기 (레거시 — 단일 종목용)"""

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
        score = 50.0
        details = {}

        if per <= 0 or per > 100:
            return FactorScore(
                factor_type=FactorType.VALUE,
                score=0,
                details={"error": "Invalid PER"}
            )

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
    """모멘텀 팩터 계산기 (레거시 — 단일 종목용)"""

    @staticmethod
    def calculate(
        return_1m: float,
        return_3m: float,
        return_6m: float,
        return_12m: float,
        distance_from_high: float = 0.0,
        volatility: float = 0.0
    ) -> FactorScore:
        score = 50.0
        details = {}

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

        if distance_from_high > -5:
            score += 10
            details["near_high_bonus"] = 10
        elif distance_from_high < -30:
            score -= 10
            details["far_from_high_penalty"] = -10

        if return_1m > 25:
            penalty = -15
            score += penalty
            details["short_term_overheat_penalty"] = penalty
        elif return_1m > 15:
            penalty = -5
            score += penalty
            details["short_term_overheat_penalty"] = penalty

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
    """퀄리티 팩터 계산기 (레거시 — 단일 종목용)"""

    @staticmethod
    def calculate(
        roe: float,
        operating_margin: float = 0.0,
        debt_ratio: float = 0.0,
        eps_growth: float = 0.0
    ) -> FactorScore:
        score = 50.0
        details = {}

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
            roe_score = -15

        details["roe_contribution"] = roe_score
        score += roe_score * FactorWeights.QUALITY_ROE_WEIGHT * 2

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
            margin_score = -10

        details["margin_contribution"] = margin_score
        score += margin_score * FactorWeights.QUALITY_MARGIN_WEIGHT * 2

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


# ============================================================
# 복합 점수 계산기
# ============================================================

class CompositeScoreCalculator:
    """복합 점수 계산기 (Percentile Ranking + 레거시 호환)"""

    FILTER_CRITERIA = {
        "per_min": 0,
        "per_max": 50,
        "pbr_min": 0.1,
        "pbr_max": 10,
        "roe_min": -10,
        "debt_ratio_max": 300,
        "return_12m_min": -30,
        "market_cap_min": 1000,
    }

    def __init__(
        self,
        value_weight: float = FactorWeights.VALUE_WEIGHT,
        momentum_weight: float = FactorWeights.MOMENTUM_WEIGHT,
        quality_weight: float = FactorWeights.QUALITY_WEIGHT,
        volume_weight: float = 0.0
    ):
        # 4팩터 지원: volume_weight > 0이면 V/M/Q에서 비례 차감
        if volume_weight > 0:
            remaining = 1.0 - volume_weight
            total_vmq = value_weight + momentum_weight + quality_weight
            if total_vmq > 0:
                value_weight = value_weight / total_vmq * remaining
                momentum_weight = momentum_weight / total_vmq * remaining
                quality_weight = quality_weight / total_vmq * remaining

        self.value_weight = value_weight
        self.momentum_weight = momentum_weight
        self.quality_weight = quality_weight
        self.volume_weight = volume_weight

        self.batch_calc = BatchFactorCalculator()
        # 레거시 호환
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
        """기본 필터 통과 여부 확인"""
        criteria = self.FILTER_CRITERIA

        if per <= criteria["per_min"]:
            return False, f"PER({per:.1f}) <= 0 (적자)"
        if per > criteria["per_max"]:
            return False, f"PER({per:.1f}) > {criteria['per_max']} (고평가)"
        if pbr < criteria["pbr_min"]:
            return False, f"PBR({pbr:.2f}) < {criteria['pbr_min']} (자본잠식 의심)"
        if pbr > criteria["pbr_max"]:
            return False, f"PBR({pbr:.2f}) > {criteria['pbr_max']} (고평가)"
        if roe < criteria["roe_min"]:
            return False, f"ROE({roe:.1f}%) < {criteria['roe_min']}% (심각한 적자)"
        if debt_ratio > criteria["debt_ratio_max"]:
            return False, f"부채비율({debt_ratio:.0f}%) > {criteria['debt_ratio_max']}%"
        if return_12m < criteria["return_12m_min"]:
            return False, f"12개월 수익률({return_12m:.1f}%) < {criteria['return_12m_min']}%"
        if market_cap > 0 and market_cap < criteria["market_cap_min"]:
            return False, f"시가총액({market_cap}억) < {criteria['market_cap_min']}억"

        return True, ""

    def calculate_batch(
        self,
        stocks_data: List[Dict],
        market_caps: List[int] = None
    ) -> List[CompositeScore]:
        """
        전체 유니버스에 대해 Cross-Sectional Percentile Ranking 기반 점수 계산

        Args:
            stocks_data: 종목 데이터 리스트 (각 dict에 per, pbr, roe, return_12m 등)
            market_caps: 시가총액 리스트 (필터용)

        Returns:
            CompositeScore 리스트 (필터 실패 종목 포함)
        """
        if not stocks_data:
            return []

        n = len(stocks_data)
        if market_caps is None:
            market_caps = [0] * n

        # 1단계: 기본 필터 적용
        filter_results = []
        filtered_indices = []  # 필터 통과한 종목의 인덱스

        for i, data in enumerate(stocks_data):
            passed, reason = self.passes_basic_filter(
                per=data.get("per", 0),
                pbr=data.get("pbr", 0),
                roe=data.get("roe", 0),
                debt_ratio=data.get("debt_ratio", 0),
                return_12m=data.get("return_12m", 0),
                market_cap=market_caps[i],
            )
            filter_results.append((passed, reason))
            if passed:
                filtered_indices.append(i)

        # 2단계: 필터 통과 종목만으로 percentile ranking 계산
        filtered_data = [stocks_data[i] for i in filtered_indices]

        if len(filtered_data) < 2:
            # 통과 종목이 2개 미만이면 기본 점수 50 부여
            logger.warning(f"필터 통과 종목 {len(filtered_data)}개 — percentile ranking 불가")
            value_scores = [50.0] * len(filtered_data)
            momentum_scores = [50.0] * len(filtered_data)
            quality_scores = [50.0] * len(filtered_data)
            volume_scores = [50.0] * len(filtered_data)
        else:
            value_scores = self.batch_calc.calculate_value_scores(filtered_data)
            momentum_scores = self.batch_calc.calculate_momentum_scores(filtered_data)
            quality_scores = self.batch_calc.calculate_quality_scores(filtered_data)
            volume_scores = self.batch_calc.calculate_volume_scores(filtered_data)

        # 3단계: CompositeScore 생성
        results = []
        filtered_idx = 0  # filtered_data 내 인덱스

        for i, data in enumerate(stocks_data):
            code = data.get("code", "")
            name = data.get("name", "")
            passed, reason = filter_results[i]

            if not passed:
                results.append(CompositeScore(
                    code=code,
                    name=name,
                    passed_filter=False,
                    filter_reason=reason,
                    per=data.get("per", 0),
                    pbr=data.get("pbr", 0),
                    roe=data.get("roe", 0),
                    return_12m=data.get("return_12m", 0),
                    debt_ratio=data.get("debt_ratio", 0),
                ))
                continue

            v_score = value_scores[filtered_idx]
            m_score = momentum_scores[filtered_idx]
            q_score = quality_scores[filtered_idx]
            vol_score = volume_scores[filtered_idx]
            filtered_idx += 1

            # 복합 점수 = 가중 합산 (4팩터)
            composite = (
                v_score * self.value_weight +
                m_score * self.momentum_weight +
                q_score * self.quality_weight +
                vol_score * self.volume_weight
            )

            # 보너스/페널티
            bonus = 0
            if all(s >= 50 for s in [v_score, m_score, q_score]):
                bonus += 5
            if min(v_score, m_score, q_score) < 20:
                bonus -= 10

            final_composite = max(0, min(100, composite + bonus))

            results.append(CompositeScore(
                code=code,
                name=name,
                value_score=round(v_score, 1),
                momentum_score=round(m_score, 1),
                quality_score=round(q_score, 1),
                composite_score=round(final_composite, 1),
                passed_filter=True,
                per=data.get("per", 0),
                pbr=data.get("pbr", 0),
                roe=data.get("roe", 0),
                return_12m=data.get("return_12m", 0),
                return_6m=data.get("return_6m", 0),
                distance_from_high=data.get("distance_from_high", 0),
                debt_ratio=data.get("debt_ratio", 0),
                volatility=data.get("volatility", 0),
            ))

        logger.info(
            f"Batch 점수 계산 완료: 전체 {n}개, 필터통과 {len(filtered_indices)}개, "
            f"가중치 V:{self.value_weight:.0%}/M:{self.momentum_weight:.0%}/Q:{self.quality_weight:.0%}"
        )

        # P9: 팩터 상관 모니터링 (필터 통과 종목만)
        if len(filtered_data) >= 10:
            correlations = self.batch_calc.compute_factor_correlations(filtered_data)
            if correlations:
                corr_str = ", ".join(f"{k}={v}" for k, v in correlations.items())
                logger.info(f"팩터 상관: {corr_str}")

        return results

    # ==================== 레거시 호환 메서드 ====================

    def calculate(
        self,
        code: str,
        name: str,
        per: float,
        pbr: float,
        psr: float = 0.0,
        dividend_yield: float = 0.0,
        return_1m: float = 0.0,
        return_3m: float = 0.0,
        return_6m: float = 0.0,
        return_12m: float = 0.0,
        distance_from_high: float = 0.0,
        volatility: float = 0.0,
        roe: float = 0.0,
        operating_margin: float = 0.0,
        debt_ratio: float = 0.0,
        eps_growth: float = 0.0,
        market_cap: int = 0
    ) -> CompositeScore:
        """
        단일 종목 점수 계산 (레거시 호환 — bucket scoring)

        주의: 이 메서드는 개별 종목 분석용.
        스크리닝에는 calculate_batch()를 사용.
        """
        passed, reason = self.passes_basic_filter(
            per=per, pbr=pbr, roe=roe,
            debt_ratio=debt_ratio, return_12m=return_12m, market_cap=market_cap
        )

        if not passed:
            return CompositeScore(
                code=code, name=name,
                passed_filter=False, filter_reason=reason,
                per=per, pbr=pbr, roe=roe,
                return_12m=return_12m, debt_ratio=debt_ratio
            )

        value_factor = self.value_calc.calculate(
            per=per, pbr=pbr, psr=psr, dividend_yield=dividend_yield
        )
        momentum_factor = self.momentum_calc.calculate(
            return_1m=return_1m, return_3m=return_3m,
            return_6m=return_6m, return_12m=return_12m,
            distance_from_high=distance_from_high, volatility=volatility
        )
        quality_factor = self.quality_calc.calculate(
            roe=roe, operating_margin=operating_margin,
            debt_ratio=debt_ratio, eps_growth=eps_growth
        )

        composite = (
            value_factor.score * self.value_weight +
            momentum_factor.score * self.momentum_weight +
            quality_factor.score * self.quality_weight
        )

        bonus = 0
        if all(s >= 50 for s in [value_factor.score, momentum_factor.score, quality_factor.score]):
            bonus += 5
        if min(value_factor.score, momentum_factor.score, quality_factor.score) < 20:
            bonus -= 10

        final_composite = max(0, min(100, composite + bonus))

        return CompositeScore(
            code=code, name=name,
            value_score=value_factor.score,
            momentum_score=momentum_factor.score,
            quality_score=quality_factor.score,
            composite_score=final_composite,
            passed_filter=True,
            per=per, pbr=pbr, roe=roe,
            return_12m=return_12m, return_6m=return_6m,
            distance_from_high=distance_from_high, debt_ratio=debt_ratio
        )

    def rank_stocks(self, scores: List[CompositeScore]) -> List[CompositeScore]:
        """종목 순위 매기기"""
        passed = [s for s in scores if s.passed_filter]
        passed.sort(key=lambda x: x.composite_score, reverse=True)
        for i, score in enumerate(passed, 1):
            score.rank = i
        return passed
