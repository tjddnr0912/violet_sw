"""Tests for ict_meta parameter in trade_from_position."""

from src.data.trade_store import trade_from_position


class _Stub:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _position():
    """Minimal fake closed-position structure."""
    fvg = _Stub(top=101.0, bottom=99.0)
    orb = _Stub(high=100.0, low=99.0, date="2026-05-12")
    signal = _Stub(orb=orb, fvg=fvg)
    return _Stub(
        signal=signal,
        symbol="TQQQ",
        direction="long",
        entry_price=100.5,
        original_stop=99.5,
        take_profit=102.5,
        exit_price=102.5,
        exit_reason="take_profit",
        shares=10,
        risk_per_share=1.0,
        gross_pnl=20.0,
        commission=0.5,
        net_pnl=19.5,
        r_multiple=2.0,
        result="WIN",
        entry_time="10:00",
        exit_time="10:25",
    )


def test_trade_from_position_no_ict_meta_keeps_legacy_shape():
    t = trade_from_position(_position())
    assert "ict" not in t
    # legacy keys remain
    assert t["entry_price"] == 100.5
    assert t["result"] == "WIN"


def test_trade_from_position_attaches_ict_block():
    meta = {
        "killzone": "AM_MACRO",
        "filters_active": ["killzone", "displacement"],
        "signal_direction": "long",
        "rr_ratio": 2.0,
    }
    t = trade_from_position(_position(), ict_meta=meta)
    assert "ict" in t
    assert t["ict"]["killzone"] == "AM_MACRO"
    assert t["ict"]["filters_active"] == ["killzone", "displacement"]


def test_trade_from_position_skips_none_values_in_ict():
    meta = {
        "killzone": None,
        "filters_active": ["killzone"],
        "signal_direction": None,
    }
    t = trade_from_position(_position(), ict_meta=meta)
    assert t["ict"] == {"filters_active": ["killzone"]}


def test_trade_from_position_empty_meta_yields_empty_block():
    t = trade_from_position(_position(), ict_meta={})
    # empty meta is falsy → ict block not added
    assert "ict" not in t
