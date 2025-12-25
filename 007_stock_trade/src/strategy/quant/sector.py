"""
섹터 분산 모듈
- 업종/섹터 분류
- 섹터 비중 관리
- 섹터 기반 분산 투자
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Sector(Enum):
    """한국 주식 업종 분류"""
    IT = "IT/반도체"
    FINANCE = "금융"
    AUTO = "자동차"
    STEEL = "철강/금속"
    CHEMICAL = "화학"
    PHARMA = "제약/바이오"
    RETAIL = "유통/소비재"
    CONSTRUCTION = "건설"
    ENERGY = "에너지"
    TELECOM = "통신"
    SHIPBUILDING = "조선/기계"
    ENTERTAINMENT = "엔터테인먼트"
    FOOD = "음식료"
    TEXTILE = "섬유/의류"
    TRANSPORT = "운송"
    UTILITY = "유틸리티"
    HOLDING = "지주회사"
    OTHER = "기타"


# 종목코드 → 섹터 매핑 (주요 종목)
STOCK_SECTOR_MAP: Dict[str, Sector] = {
    # IT/반도체
    "005930": Sector.IT,       # 삼성전자
    "000660": Sector.IT,       # SK하이닉스
    "005935": Sector.IT,       # 삼성전자우
    "066570": Sector.IT,       # LG전자
    "035420": Sector.IT,       # NAVER
    "035720": Sector.IT,       # 카카오
    "006400": Sector.IT,       # 삼성SDI
    "051910": Sector.CHEMICAL, # LG화학
    "373220": Sector.IT,       # LG에너지솔루션
    "247540": Sector.IT,       # 에코프로비엠
    "086520": Sector.IT,       # 에코프로
    "402340": Sector.IT,       # SK스퀘어

    # 금융
    "105560": Sector.FINANCE,  # KB금융
    "055550": Sector.FINANCE,  # 신한지주
    "086790": Sector.FINANCE,  # 하나금융지주
    "316140": Sector.FINANCE,  # 우리금융지주
    "138930": Sector.FINANCE,  # BNK금융지주
    "139130": Sector.FINANCE,  # iM금융지주
    "175330": Sector.FINANCE,  # JB금융지주
    "024110": Sector.FINANCE,  # 기업은행
    "000810": Sector.FINANCE,  # 삼성화재
    "001450": Sector.FINANCE,  # 현대해상
    "016360": Sector.FINANCE,  # 삼성증권
    "039490": Sector.FINANCE,  # 키움증권
    "029780": Sector.FINANCE,  # 삼성카드

    # 자동차
    "005380": Sector.AUTO,     # 현대차
    "000270": Sector.AUTO,     # 기아
    "005387": Sector.AUTO,     # 현대차2우B
    "005385": Sector.AUTO,     # 현대차우
    "012330": Sector.AUTO,     # 현대모비스
    "161390": Sector.AUTO,     # 한국타이어앤테크놀로지
    "073240": Sector.AUTO,     # 금호타이어

    # 철강/금속
    "005490": Sector.STEEL,    # POSCO홀딩스
    "010130": Sector.STEEL,    # 고려아연
    "004020": Sector.STEEL,    # 현대제철

    # 화학
    "051910": Sector.CHEMICAL, # LG화학
    "010950": Sector.CHEMICAL, # S-Oil
    "011170": Sector.CHEMICAL, # 롯데케미칼
    "096770": Sector.CHEMICAL, # SK이노베이션

    # 제약/바이오
    "207940": Sector.PHARMA,   # 삼성바이오로직스
    "068270": Sector.PHARMA,   # 셀트리온
    "326030": Sector.PHARMA,   # SK바이오팜
    "196170": Sector.PHARMA,   # 알테오젠

    # 유통/소비재
    "034730": Sector.RETAIL,   # SK
    "030200": Sector.RETAIL,   # KT
    "009150": Sector.RETAIL,   # 삼성전기
    "003550": Sector.RETAIL,   # LG

    # 건설
    "006360": Sector.CONSTRUCTION,  # GS건설
    "000720": Sector.CONSTRUCTION,  # 현대건설
    "047040": Sector.CONSTRUCTION,  # 대우건설

    # 에너지/유틸리티
    "015760": Sector.UTILITY,  # 한국전력
    "034020": Sector.ENERGY,   # 두산에너빌리티

    # 조선/기계
    "329180": Sector.SHIPBUILDING,  # HD현대중공업
    "009540": Sector.SHIPBUILDING,  # HD한국조선해양
    "012450": Sector.SHIPBUILDING,  # 한화에어로스페이스

    # 지주회사
    "000100": Sector.HOLDING,  # 유한양행
    "003490": Sector.HOLDING,  # 대한항공
    "009970": Sector.HOLDING,  # 영원무역홀딩스
}


@dataclass
class SectorAllocation:
    """섹터 배분 정보"""
    sector: Sector
    stock_count: int = 0
    weight: float = 0.0
    target_weight: float = 0.0
    stocks: List[str] = field(default_factory=list)


@dataclass
class SectorConstraints:
    """섹터 제약 조건"""
    max_sector_weight: float = 0.30      # 최대 섹터 비중 (30%)
    min_sector_count: int = 3            # 최소 섹터 수
    max_single_stock: float = 0.10       # 최대 단일 종목 비중 (10%)
    avoid_sectors: Set[Sector] = field(default_factory=set)


class SectorManager:
    """섹터 관리자"""

    def __init__(self, constraints: SectorConstraints = None):
        self.constraints = constraints or SectorConstraints()

    def get_sector(self, stock_code: str) -> Sector:
        """
        종목의 섹터 반환

        Args:
            stock_code: 종목코드

        Returns:
            Sector
        """
        return STOCK_SECTOR_MAP.get(stock_code, Sector.OTHER)

    def classify_stocks(self, stocks: List[Dict]) -> Dict[Sector, List[Dict]]:
        """
        종목 목록을 섹터별로 분류

        Args:
            stocks: 종목 리스트 [{code, name, ...}, ...]

        Returns:
            섹터별 종목 딕셔너리
        """
        sector_stocks = {sector: [] for sector in Sector}

        for stock in stocks:
            code = stock.get('code', '')
            sector = self.get_sector(code)
            stock['sector'] = sector
            sector_stocks[sector].append(stock)

        return sector_stocks

    def get_allocation(
        self,
        positions: List[Dict],
        total_value: float
    ) -> Dict[Sector, SectorAllocation]:
        """
        현재 섹터 배분 현황 계산

        Args:
            positions: 포지션 리스트 [{code, name, value, weight}, ...]
            total_value: 총 포트폴리오 가치

        Returns:
            섹터별 배분 정보
        """
        allocations = {sector: SectorAllocation(sector=sector) for sector in Sector}

        for pos in positions:
            code = pos.get('code', '')
            sector = self.get_sector(code)
            value = pos.get('value', pos.get('market_value', 0))

            allocations[sector].stock_count += 1
            allocations[sector].stocks.append(code)

            if total_value > 0:
                allocations[sector].weight += value / total_value

        return allocations

    def check_constraints(
        self,
        positions: List[Dict],
        total_value: float
    ) -> List[str]:
        """
        섹터 제약 조건 위반 확인

        Args:
            positions: 포지션 리스트
            total_value: 총 포트폴리오 가치

        Returns:
            위반 사항 리스트
        """
        violations = []

        allocations = self.get_allocation(positions, total_value)

        # 최대 섹터 비중 체크
        for sector, alloc in allocations.items():
            if alloc.weight > self.constraints.max_sector_weight:
                violations.append(
                    f"섹터 비중 초과: {sector.value} ({alloc.weight*100:.1f}% > {self.constraints.max_sector_weight*100:.1f}%)"
                )

        # 최소 섹터 수 체크
        active_sectors = sum(1 for a in allocations.values() if a.stock_count > 0)
        if active_sectors < self.constraints.min_sector_count:
            violations.append(
                f"섹터 분산 부족: {active_sectors}개 < {self.constraints.min_sector_count}개"
            )

        # 개별 종목 비중 체크
        for pos in positions:
            weight = pos.get('weight', 0)
            if weight > self.constraints.max_single_stock:
                violations.append(
                    f"종목 비중 초과: {pos.get('name', pos.get('code', ''))} ({weight*100:.1f}%)"
                )

        return violations

    def apply_sector_diversification(
        self,
        candidates: List[Dict],
        target_count: int = 20
    ) -> List[Dict]:
        """
        섹터 분산을 적용하여 종목 선정

        Args:
            candidates: 후보 종목 리스트 (점수 순으로 정렬됨)
            target_count: 목표 종목 수

        Returns:
            분산 적용된 종목 리스트
        """
        if not candidates:
            return []

        selected = []
        sector_counts = {sector: 0 for sector in Sector}

        # 섹터당 최대 종목 수
        max_per_sector = max(2, target_count // 4)

        for stock in candidates:
            if len(selected) >= target_count:
                break

            code = stock.get('code', '')
            sector = self.get_sector(code)

            # 회피 섹터 체크
            if sector in self.constraints.avoid_sectors:
                continue

            # 섹터 한도 체크
            if sector_counts[sector] >= max_per_sector:
                continue

            selected.append(stock)
            sector_counts[sector] += 1

        # 목표 수가 안 찼으면 나머지 채우기
        if len(selected) < target_count:
            remaining = [s for s in candidates if s not in selected]
            for stock in remaining:
                if len(selected) >= target_count:
                    break

                code = stock.get('code', '')
                sector = self.get_sector(code)

                if sector not in self.constraints.avoid_sectors:
                    selected.append(stock)

        return selected

    def calculate_rebalance_for_sector_limit(
        self,
        positions: List[Dict],
        total_value: float
    ) -> List[Dict]:
        """
        섹터 비중 제한을 위한 리밸런싱 계산

        Args:
            positions: 현재 포지션 리스트
            total_value: 총 포트폴리오 가치

        Returns:
            리밸런싱 필요 종목 리스트
        """
        rebalance_actions = []

        allocations = self.get_allocation(positions, total_value)

        # 비중 초과 섹터 처리
        for sector, alloc in allocations.items():
            if alloc.weight > self.constraints.max_sector_weight:
                excess = alloc.weight - self.constraints.max_sector_weight

                # 해당 섹터의 종목 중 가장 낮은 점수의 종목부터 매도
                sector_positions = [p for p in positions if self.get_sector(p['code']) == sector]

                # 점수 기준 정렬 (낮은 것 먼저)
                sector_positions.sort(key=lambda x: x.get('score', 0))

                sold_weight = 0
                for pos in sector_positions:
                    if sold_weight >= excess:
                        break

                    pos_weight = pos.get('weight', 0)
                    sell_weight = min(pos_weight, excess - sold_weight)

                    rebalance_actions.append({
                        'action': 'SELL',
                        'code': pos['code'],
                        'name': pos.get('name', ''),
                        'reason': f'섹터 비중 초과 ({sector.value})',
                        'weight': sell_weight
                    })

                    sold_weight += sell_weight

        return rebalance_actions

    def get_sector_report(
        self,
        positions: List[Dict],
        total_value: float
    ) -> str:
        """
        섹터 배분 리포트 생성

        Args:
            positions: 포지션 리스트
            total_value: 총 포트폴리오 가치

        Returns:
            리포트 문자열
        """
        allocations = self.get_allocation(positions, total_value)

        lines = [
            "=" * 40,
            "       섹터 배분 현황",
            "=" * 40,
            ""
        ]

        # 비중 기준 정렬
        sorted_allocs = sorted(
            allocations.items(),
            key=lambda x: x[1].weight,
            reverse=True
        )

        for sector, alloc in sorted_allocs:
            if alloc.stock_count == 0:
                continue

            bar_len = int(alloc.weight * 100 / 5)  # 5% 단위
            bar = "█" * bar_len

            lines.append(
                f"{sector.value:15} {alloc.weight*100:5.1f}% {bar} ({alloc.stock_count}종목)"
            )

        lines.append("")
        lines.append("-" * 40)

        # 제약 조건 체크
        violations = self.check_constraints(positions, total_value)
        if violations:
            lines.append("⚠️ 제약 조건 위반:")
            for v in violations:
                lines.append(f"  - {v}")
        else:
            lines.append("✅ 모든 제약 조건 충족")

        lines.append("=" * 40)

        return "\n".join(lines)
