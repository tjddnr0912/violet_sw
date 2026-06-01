"""신고가/신저점 판정 — 순수함수."""
from dataclasses import dataclass


@dataclass
class Verdict:
    kind: str            # 'HIGH' | 'LOW' | 'NEW' | 'NORMAL'
    pct: float | None = None
    ref_price: int | None = None
    ref_date: str | None = None


def classify(record: dict, group_baseline: dict | None) -> Verdict:
    """record를 (단지,평형밴드) 36개월 baseline과 비교.

    group_baseline: {'max','max_date','min','min_date','count'} 또는 None(이력 없음).
    """
    price = int(record["price_10k"])
    if not group_baseline or group_baseline.get("count", 0) == 0:
        return Verdict(kind="NEW")

    mx = group_baseline["max"]
    mn = group_baseline["min"]
    if price > mx:
        return Verdict(kind="HIGH", pct=(price / mx - 1) * 100,
                       ref_price=mx, ref_date=group_baseline["max_date"])
    if price < mn:
        return Verdict(kind="LOW", pct=(price / mn - 1) * 100,
                       ref_price=mn, ref_date=group_baseline["min_date"])
    return Verdict(kind="NORMAL")
