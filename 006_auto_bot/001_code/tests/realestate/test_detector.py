from realestate_bot.detector import classify, Verdict


def test_new_high():
    base = {"max": 100000, "max_date": "2025-01-01", "min": 80000,
            "min_date": "2024-01-01", "count": 5}
    v = classify({"price_10k": 110000}, base)
    assert v.kind == "HIGH"
    assert round(v.pct, 1) == 10.0
    assert v.ref_price == 100000 and v.ref_date == "2025-01-01"


def test_new_low():
    base = {"max": 100000, "max_date": "2025-01-01", "min": 80000,
            "min_date": "2024-01-01", "count": 5}
    v = classify({"price_10k": 70000}, base)
    assert v.kind == "LOW"
    assert round(v.pct, 1) == -12.5
    assert v.ref_price == 80000 and v.ref_date == "2024-01-01"


def test_no_history_is_new():
    v = classify({"price_10k": 90000}, None)
    assert v.kind == "NEW" and v.pct is None


def test_within_range_is_normal():
    base = {"max": 100000, "max_date": "x", "min": 80000, "min_date": "y", "count": 5}
    v = classify({"price_10k": 90000}, base)
    assert v.kind == "NORMAL"


def test_tie_with_max_is_normal_not_high():
    # 동일가는 경신이 아님
    base = {"max": 100000, "max_date": "x", "min": 80000, "min_date": "y", "count": 5}
    v = classify({"price_10k": 100000}, base)
    assert v.kind == "NORMAL"
