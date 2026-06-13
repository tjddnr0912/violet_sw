"""청크 분할 변환 시 저자 박스가 정확히 1개만 들어가는지 회귀 테스트.

버그(2026-06-13): buffett/sector의 긴 글 청크 변환이 청크마다 저자 박스를
붙여, 2청크 이상이면 박스가 글 중간중간 중복되던 문제. 수정 후 박스는 합친
결과 끝에 한 번만 적용된다.
"""

import os
import re

import buffett_bot


def _count_boxes(html: str) -> int:
    # 저자 박스 이름 div의 고유 스타일 시그니처
    return len(re.findall(r"font-weight:700;font-size:15px", html))


def test_buffett_long_md_single_author_box(monkeypatch):
    os.environ["EDITORIAL_ENABLED"] = "true"

    # 청크 변환은 박스 없는 본문만 반환하도록 모킹(apply_editorial_box=False 동작 모사)
    def fake_convert(md_content, apply_editorial_box=True, **kwargs):
        assert apply_editorial_box is False, "청크엔 박스를 붙이면 안 됨"
        return (f"<div class='chunk'><p>{md_content[:15]}</p></div>", "")

    monkeypatch.setattr(buffett_bot, "convert_md_to_html_via_claude", fake_convert)

    # 2청크 이상으로 강제 분할되는 긴 마크다운
    md = "## 섹션 A\n" + ("가" * 3000) + "\n## 섹션 B\n" + ("나" * 3000)
    html = buffett_bot.convert_long_md_to_html(md)

    assert _count_boxes(html) == 1, f"저자 박스가 1개가 아님: {_count_boxes(html)}"
    assert html.count("<!-- editorial-layer -->") == 1


def test_buffett_single_chunk_still_one_box(monkeypatch):
    os.environ["EDITORIAL_ENABLED"] = "true"

    def fake_convert(md_content, apply_editorial_box=True, **kwargs):
        return (f"<div class='chunk'><p>{md_content[:15]}</p></div>", "")

    monkeypatch.setattr(buffett_bot, "convert_md_to_html_via_claude", fake_convert)

    md = "## 한 섹션\n" + ("다" * 500)
    html = buffett_bot.convert_long_md_to_html(md)
    assert _count_boxes(html) == 1
