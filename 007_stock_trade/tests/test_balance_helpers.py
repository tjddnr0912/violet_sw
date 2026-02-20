"""parse_balance 헬퍼 테스트"""

import pytest
from src.utils.balance_helpers import parse_balance, BalanceSummary


class TestParseBalance:
    """parse_balance() 테스트"""

    def test_nass_positive(self):
        """nass > 0 일 때 nass 기반 계산"""
        balance = {
            'nass': 10_000_000,
            'scts_evlu': 6_000_000,
            'cash': 8_000_000,  # T+2 미반영 예수금 (무시되어야 함)
            'buy_amount': 5_500_000,
        }
        bs = parse_balance(balance)
        assert bs.total_assets == 10_000_000
        assert bs.cash == 4_000_000  # 10M - 6M
        assert bs.scts_evlu == 6_000_000
        assert bs.buy_amount == 5_500_000

    def test_nass_zero_fallback(self):
        """nass == 0 일 때 cash + scts_evlu 폴백"""
        balance = {
            'nass': 0,
            'scts_evlu': 6_000_000,
            'cash': 4_000_000,
            'buy_amount': 5_500_000,
        }
        bs = parse_balance(balance)
        assert bs.total_assets == 10_000_000
        assert bs.cash == 4_000_000
        assert bs.scts_evlu == 6_000_000

    def test_missing_keys(self):
        """키가 누락된 경우 기본값 0"""
        bs = parse_balance({})
        assert bs.total_assets == 0
        assert bs.cash == 0
        assert bs.scts_evlu == 0
        assert bs.buy_amount == 0

    def test_nass_missing_key(self):
        """nass 키 자체가 없을 때"""
        balance = {
            'scts_evlu': 3_000_000,
            'cash': 2_000_000,
        }
        bs = parse_balance(balance)
        assert bs.total_assets == 5_000_000
        assert bs.cash == 2_000_000

    def test_returns_namedtuple(self):
        """BalanceSummary NamedTuple 타입 반환"""
        bs = parse_balance({'nass': 100})
        assert isinstance(bs, BalanceSummary)
        assert isinstance(bs, tuple)
