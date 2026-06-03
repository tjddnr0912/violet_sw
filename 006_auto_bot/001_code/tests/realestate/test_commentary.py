from unittest import mock
from realestate_bot import commentary


def test_returns_text_on_success():
    with mock.patch("realestate_bot.commentary._ask_gemini", return_value="시황 텍스트"):
        out = commentary.make_commentary({"seoul": {"new_total": 10}})
    assert out == "시황 텍스트"


def test_degrades_to_empty_on_failure():
    with mock.patch("realestate_bot.commentary._ask_gemini",
                    side_effect=RuntimeError("429")):
        out = commentary.make_commentary({"seoul": {"new_total": 10}})
    assert out == ""


from realestate_bot import commentary as _c


def test_frame_is_national_multiparagraph():
    # 전국 다문단 지시가 프레임에 들어있다 (서울 전용 문구 아님)
    assert "전국" in _c._FRAME
    assert "광역시" in _c._FRAME


def test_make_commentary_degrades_without_ai(monkeypatch):
    def boom(_prompt):
        raise RuntimeError("no ai")
    monkeypatch.setattr(_c, "_ask_gemini", boom)
    assert _c.make_commentary({"national": {"new_total": 0}, "groups": {}}) == ""
