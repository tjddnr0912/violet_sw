"""Item #43: 섹터 집중도 제한 - 단일 섹터 N개 초과 매수 차단"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.quant_modules.order_executor import OrderExecutor, DEFAULT_MAX_PER_SECTOR
from src.strategy.quant.sector import STOCK_SECTOR_MAP, Sector


def _mk():
    return OrderExecutor(
        client=MagicMock(),
        portfolio=MagicMock(),
        notifier=MagicMock(),
        config=MagicMock(),
        is_virtual=True,
    )


def main():
    oe = _mk()

    # 금융 섹터 종목 코드 찾기 (한국전력은 유틸리티이지만 KB금융/신한지주/하나금융지주는 금융)
    financial_codes = [
        c for c, s in STOCK_SECTOR_MAP.items() if s == Sector.FINANCE
    ][: DEFAULT_MAX_PER_SECTOR + 2]
    if len(financial_codes) < DEFAULT_MAX_PER_SECTOR + 1:
        print(f"SKIP: 금융 섹터 종목 부족 ({len(financial_codes)}개), 검증 의미 없음")
        return

    # 케이스 1: 빈 보유 → 처음 N개는 매수 가능, N+1번째는 차단
    counts = oe._count_sectors_in_positions(set())
    bought = []
    blocked = []
    for code in financial_codes:
        if oe._is_blocked_by_sector_limit(code, counts):
            blocked.append(code)
        else:
            bought.append(code)
            oe._increment_sector(code, counts)
    assert len(bought) == DEFAULT_MAX_PER_SECTOR, f"매수 {len(bought)} != {DEFAULT_MAX_PER_SECTOR}"
    assert len(blocked) >= 1, "한도 초과 매수가 차단되지 않음"

    # 케이스 2: 이미 보유 N개 → 추가 매수 차단
    oe2 = _mk()
    counts2 = oe2._count_sectors_in_positions(set(financial_codes[:DEFAULT_MAX_PER_SECTOR]))
    new_code = financial_codes[DEFAULT_MAX_PER_SECTOR]  # 같은 섹터 신규
    assert oe2._is_blocked_by_sector_limit(new_code, counts2) is True

    # 케이스 3: 다른 섹터는 통과
    other_code = next(
        (c for c, s in STOCK_SECTOR_MAP.items() if s != Sector.FINANCE),
        None,
    )
    assert other_code, "다른 섹터 종목 없음"
    assert oe2._is_blocked_by_sector_limit(other_code, counts2) is False

    print(f"PASS: 섹터 한도 max_per_sector={DEFAULT_MAX_PER_SECTOR}, 금융 {DEFAULT_MAX_PER_SECTOR}개 후 차단")


if __name__ == "__main__":
    main()
