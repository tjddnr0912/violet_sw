"""Tests for the editorial layer (author box + disclaimer + transparency)."""

import pytest

from shared.editorial import (
    apply_editorial,
    author_box_html,
    disclaimer_html,
    transparency_html,
    get_author,
)


def test_author_box_contains_name_and_bio():
    box = author_box_html("sector")
    a = get_author("sector")
    assert a["name"] in box
    assert a["bio"] in box
    # 인라인 스타일만, script/style 금지 (Tistory sanitize 대비)
    assert "<script" not in box
    assert "<style" not in box


def test_unknown_author_falls_back_to_default():
    a = get_author("does-not-exist")
    assert a == get_author("default")


def test_disclaimer_only_for_financial_types():
    assert "투자" in disclaimer_html("buffett")
    assert "거래" in disclaimer_html("realestate")
    # 비금융/일반 타입은 면책 없음
    assert disclaimer_html("news") == ""
    assert disclaimer_html("general") == ""


def test_apply_editorial_appends_block_with_marker():
    html = "<h2>제목</h2><p>본문</p>"
    out = apply_editorial(html, author_key="buffett", content_type="buffett")
    assert html in out                      # 원본 보존
    assert "<!-- editorial-layer -->" in out
    assert get_author("buffett")["name"] in out
    assert "최종 업데이트" in out            # 신뢰/업데이트 라인
    # 기본값은 면책 미포함(스킬이 contextual하게 담당)
    assert "권유가 아닙니다" not in out


def test_apply_editorial_optional_disclaimer():
    html = "<p>본문</p>"
    out = apply_editorial(html, "buffett", "buffett", include_disclaimer=True)
    assert "투자" in out                     # include_disclaimer=True 시 면책 포함


def test_apply_editorial_idempotent():
    html = "<p>x</p>"
    once = apply_editorial(html, "sector", "sector")
    twice = apply_editorial(once, "sector", "sector")
    assert once == twice                    # 마커 있으면 재삽입 안 함


def test_transparency_uses_given_date():
    assert "2026-01-02" in transparency_html("2026-01-02")


def test_empty_html_safe():
    assert apply_editorial("") == ""
    assert apply_editorial(None) is None
