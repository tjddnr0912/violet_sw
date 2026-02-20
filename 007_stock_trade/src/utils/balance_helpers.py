"""
KIS 잔고 데이터 정규화 헬퍼

nass(순자산) 우선 사용으로 T+2 결제 이중 계산 방지.
"""

from typing import NamedTuple


class BalanceSummary(NamedTuple):
    """정규화된 잔고 요약"""
    total_assets: float   # nass (순자산, 미결제 약정 반영)
    cash: float           # total_assets - scts_evlu (실질 현금)
    scts_evlu: float      # 주식평가금
    buy_amount: float     # 매입금액


def parse_balance(balance: dict) -> BalanceSummary:
    """
    KIS get_balance() 응답을 정규화.

    nass(순자산)를 우선 사용하여 T+2 결제 미반영으로 인한
    예수금(dnca_tot_amt) 이중 계산을 방지.

    Args:
        balance: KIS get_balance() 응답 딕셔너리

    Returns:
        BalanceSummary (total_assets, cash, scts_evlu, buy_amount)
    """
    nass = balance.get('nass', 0)
    scts_evlu = balance.get('scts_evlu', 0)
    buy_amount = balance.get('buy_amount', 0)

    if nass > 0:
        total_assets = nass
    else:
        total_assets = balance.get('cash', 0) + scts_evlu

    cash = total_assets - scts_evlu

    return BalanceSummary(
        total_assets=total_assets,
        cash=cash,
        scts_evlu=scts_evlu,
        buy_amount=buy_amount,
    )
