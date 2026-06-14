"""이미지 마커 strip 시 주석 중첩(=> '-->' 본문 노출) 방지 회귀 테스트.

버그: Claude가 마커를 주석으로 감싸 `<!-- [[IMAGE: ...]] -->`로 출력하면,
strip이 안쪽만 치환해 `<!-- <!-- ... --> -->`로 중첩 → 브라우저가 첫 -->에서
주석을 닫아 남은 ' -->'가 화면에 노출되고 빈 공간이 생겼다.
"""
import re
import shared.claude_html_converter as conv


def _strip(html):
    return conv._maybe_inject_images(html)


def test_wrapped_marker_no_nested_comment(monkeypatch):
    monkeypatch.delenv("BLOGGER_IMAGES_ENABLED", raising=False)  # default false → strip
    html = "<p>intro</p>\n<!-- [[IMAGE: a french AI illustration, flat]] -->\n<p>body</p>"
    out = _strip(html)
    assert "[[IMAGE" not in out
    assert "<!-- <!--" not in out          # 주석 중첩 없음
    assert not re.search(r"-->\s*-->", out)  # 닫는 주석 중복 없음
    assert "intro" in out and "body" in out  # 본문 보존


def test_bare_marker_still_stripped(monkeypatch):
    monkeypatch.delenv("BLOGGER_IMAGES_ENABLED", raising=False)
    out = _strip("<p>x</p>[[IMAGE: foo bar]]<p>y</p>")
    assert "[[IMAGE" not in out
    assert "<!-- <!--" not in out
    assert "x" in out and "y" in out


def test_no_marker_unchanged(monkeypatch):
    monkeypatch.delenv("BLOGGER_IMAGES_ENABLED", raising=False)
    html = "<p>no markers here</p>"
    assert _strip(html) == html
