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
