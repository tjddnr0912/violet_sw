"""Tests for shared.local_archive (Tistory manual-upload draft saver)."""

from datetime import datetime

from shared.local_archive import save_post_draft, _slugify


def test_saves_under_actual_date_folder(tmp_path):
    when = datetime(2026, 6, 8, 14, 30, 15)
    path = save_post_draft(
        "반도체 공급망 재편", ["반도체", "공급망"], "<p>본문</p>",
        base_dir=str(tmp_path), when=when,
    )
    assert "/2026-06-08/" in path
    assert path.endswith(".txt")


def test_file_order_title_tags_content(tmp_path):
    when = datetime(2026, 6, 8, 9, 0, 0)
    path = save_post_draft(
        "제목입니다", ["a", "b", "c"], "<div>HTML 내용</div>",
        base_dir=str(tmp_path), when=when,
    )
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    assert lines[0] == "제목: 제목입니다"
    assert lines[1] == "태그: a, b, c"
    assert lines[2] == ""              # 빈 줄 구분
    assert "<div>HTML 내용</div>" in text
    # 제목이 태그보다, 태그가 내용보다 앞에 있어야 한다
    assert text.index("제목:") < text.index("태그:") < text.index("<div>")


def test_empty_tags_ok(tmp_path):
    when = datetime(2026, 6, 8, 9, 0, 0)
    path = save_post_draft("t", None, "<p>x</p>", base_dir=str(tmp_path), when=when)
    text = open(path, encoding="utf-8").read()
    assert text.splitlines()[1] == "태그: "


def test_env_override_base_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TISTORY_ARCHIVE_DIR", str(tmp_path / "envdir"))
    when = datetime(2026, 6, 8, 9, 0, 0)
    path = save_post_draft("t", [], "<p>x</p>", when=when)
    assert str(tmp_path / "envdir") in path


def test_slugify_keeps_korean_drops_punct():
    assert _slugify("반도체! 공급망/재편?") == "반도체_공급망재편"
    assert _slugify("") == "untitled"
