"""WordPress 업로더 SEO 헬퍼(slugify / auto_excerpt / demote_body_h1 / english_slug) 단위 테스트."""

import shared.gemini_cli as gemini_cli
import shared.wordpress_uploader as wp
from shared.wordpress_uploader import (
    slugify,
    auto_excerpt,
    demote_body_h1,
    english_slug,
    auto_draft_enabled,
    WordPressUploader,
    _kebab,
)


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


# --- english_slug ---

def _fake_resp(text):
    return type("R", (), {"text": text})()


def test_kebab_sanitizes():
    assert _kebab("Quantum Computing! PQC, Roadmap.") == "quantum-computing-pqc-roadmap"
    assert _kebab("  Hello   World  ") == "hello-world"


def test_english_slug_ascii_no_gemini(monkeypatch):
    # ASCII 제목은 Gemini를 호출하지 않아야 한다(호출하면 실패하도록 세팅)
    def boom(*a, **k):
        raise AssertionError("ASCII 제목에 Gemini 호출하면 안 됨")
    monkeypatch.setattr(gemini_cli, "call_gemini_with_fallback", boom)
    assert english_slug("Buffett Daily Note 2026-06-13") == "buffett-daily-note-2026-06-13"


def test_english_slug_korean_uses_gemini(monkeypatch):
    monkeypatch.setattr(
        gemini_cli, "call_gemini_with_fallback",
        lambda *a, **k: _fake_resp("Quantum Computing, PQC Migration Roadmap"),
    )
    s = english_slug("양자컴퓨터가 깨뜨릴 암호와 PQC 전환 로드맵")
    assert s == "quantum-computing-pqc-migration-roadmap"
    assert s.isascii()


def test_english_slug_falls_back_to_romanization_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gemini down")
    monkeypatch.setattr(gemini_cli, "call_gemini_with_fallback", boom)
    s = english_slug("뉴스 요약")
    assert s and s.isascii()  # 로마자 폴백(non-empty ascii)


def test_english_slug_falls_back_on_garbage(monkeypatch):
    # Gemini가 빈/너무짧은 결과를 주면 로마자 폴백
    monkeypatch.setattr(
        gemini_cli, "call_gemini_with_fallback", lambda *a, **k: _fake_resp("   ")
    )
    s = english_slug("부동산 주간 디제스트")
    assert s and s.isascii()


# --- force_draft (investment_bot 자동봇 강제 draft) ---

class _FakePostResp:
    status_code = 201
    content = b"{}"

    def json(self):
        return {"id": 1, "link": "https://x/p", "status": "draft"}


def _capture_post(monkeypatch):
    """requests.post를 가로채 /posts payload를 잡는다. (captured dict 반환)"""
    captured = {}

    def fake_post(url, json=None, **kw):
        if url.endswith("/posts"):
            captured["payload"] = json
        return _FakePostResp()

    monkeypatch.setattr(wp.requests, "post", fake_post)
    return captured


def _uploader(**kw):
    return WordPressUploader(
        base_url="https://x", user="u", app_password="p", **kw
    )


def test_force_draft_overrides_explicit_publish(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader(force_draft=True)
    res = up.create_post("Title Only ASCII", "<p>body</p>", status="publish")
    assert res["success"]
    assert captured["payload"]["status"] == "draft"  # publish 요청을 draft로 강제


def test_force_draft_overrides_upload_post_publish(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader(force_draft=True)
    res = up.upload_post("Title Only ASCII", "<p>body</p>", is_draft=False)
    assert res["success"]
    assert captured["payload"]["status"] == "draft"  # is_draft=False여도 강제 draft


def test_no_force_draft_keeps_publish(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader(force_draft=False)
    up.create_post("Title Only ASCII", "<p>body</p>", status="publish")
    assert captured["payload"]["status"] == "publish"  # 기본 동작 보존(텔레그램 봇)


def test_auto_draft_enabled_default_true(monkeypatch):
    monkeypatch.delenv("AUTO_BOT_DRAFT_ONLY", raising=False)
    assert auto_draft_enabled() is True  # .env 없으면 안전하게 draft


def test_auto_draft_enabled_false_toggle(monkeypatch):
    monkeypatch.setenv("AUTO_BOT_DRAFT_ONLY", "false")
    assert auto_draft_enabled() is False
    monkeypatch.setenv("AUTO_BOT_DRAFT_ONLY", "true")
    assert auto_draft_enabled() is True
