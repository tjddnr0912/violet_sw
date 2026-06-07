"""Sector analyzer model cascade: 3.5-flash primary -> flash-lite first fallback.

`_models_chain(self)` only reads `self.model_name` + env, so we call the
unbound method with a lightweight fake self (no API key / heavy __init__).
"""

from sector_bot.analyzer import SectorAnalyzer


class _Fake:
    model_name = "gemini-3.5-flash"


def test_sector_chain_3_5_flash_primary_then_flash_lite(monkeypatch):
    monkeypatch.delenv("SECTOR_GEMINI_FALLBACK_MODELS", raising=False)
    chain = SectorAnalyzer._models_chain(_Fake())
    assert chain[0] == "gemini-3.5-flash"            # primary
    assert chain[1] == "gemini-3.1-flash-lite"       # first fallback when 3.5 quota gone
    assert "gemini-3.5-flash" not in chain[1:]       # no duplicate of primary


def test_sector_chain_uses_sector_specific_fallback_env(monkeypatch):
    # sector fallback must be independent of the global GEMINI_FALLBACK_MODELS
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "should-be-ignored")
    monkeypatch.setenv("SECTOR_GEMINI_FALLBACK_MODELS", "gemini-a,gemini-b")
    chain = SectorAnalyzer._models_chain(_Fake())
    assert chain == ["gemini-3.5-flash", "gemini-a", "gemini-b"]


def test_sector_config_default_model_is_3_5_flash(monkeypatch):
    import importlib
    import sector_bot.config as cfg
    monkeypatch.delenv("SECTOR_GEMINI_MODEL", raising=False)
    importlib.reload(cfg)
    try:
        assert cfg.SectorConfig.GEMINI_MODEL == "gemini-3.5-flash"
    finally:
        importlib.reload(cfg)
