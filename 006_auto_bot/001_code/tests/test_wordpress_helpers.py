"""WordPress 업로더 SEO 헬퍼(slugify / auto_excerpt / demote_body_h1) 단위 테스트."""

from shared.wordpress_uploader import slugify, auto_excerpt, demote_body_h1


def test_slugify_korean_to_ascii():
    s = slugify("2026년 06월 13일 뉴스 요약")
    assert s and s.isascii()
    assert " " not in s and s == s.lower()
    assert all(c.isalnum() or c == "-" for c in s)


def test_slugify_keeps_ascii_words():
    assert slugify("Buffett Daily 2026-06-13") == "buffett-daily-2026-06-13"


def test_slugify_empty_returns_empty():
    assert slugify("") == ""
    assert slugify("!!! ???") == ""  # 로마자화 불가 문자만 → 빈 슬러그


def test_slugify_word_and_length_cap():
    long_title = "가 나 다 라 마 바 사 아 자 차"  # 10 단어
    s = slugify(long_title, max_words=6)
    assert s.count("-") <= 5  # 최대 6단어 → 하이픈 5개 이하
    assert len(s) <= 60


def test_demote_body_h1():
    html = '<h1 style="font-size:26px">헤드라인</h1><p>본문</p><h2>소제목</h2>'
    out = demote_body_h1(html)
    assert "<h1" not in out and "</h1>" not in out
    assert '<h2 style="font-size:26px">헤드라인</h2>' in out
    assert "<h2>소제목</h2>" in out  # 기존 h2는 유지


def test_demote_body_h1_idempotent_and_safe():
    assert demote_body_h1("") == ""
    assert demote_body_h1("<p>no heading</p>") == "<p>no heading</p>"


def test_auto_excerpt_skips_heading_and_strips_tags():
    body = (
        '<h1 style="x">스페이스X 상장</h1>'
        "<p>오늘 증시는 상장 기대에 상승 마감했다. 외국인 순매수가 두드러졌다.</p>"
    )
    ex = auto_excerpt(body)
    assert "<" not in ex
    assert ex.startswith("오늘 증시는")  # 헤딩 건너뛰고 첫 문단부터


def test_auto_excerpt_truncates_with_ellipsis():
    long_p = "<p>" + ("가나다라마바사 " * 40) + "</p>"
    ex = auto_excerpt(long_p, max_len=100)
    assert len(ex) <= 101
    assert ex.endswith("…")


def test_auto_excerpt_empty():
    assert auto_excerpt("") == ""
    assert auto_excerpt("<h1>제목뿐</h1>") == ""  # 헤딩만 있으면 빈 발췌
