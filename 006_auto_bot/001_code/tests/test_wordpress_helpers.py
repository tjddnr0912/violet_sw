"""WordPress 업로더 SEO 헬퍼(slugify / auto_excerpt / demote_body_h1 / english_slug) 단위 테스트."""

import shared.gemini_cli as gemini_cli
import shared.wordpress_uploader as wp
from shared.wordpress_uploader import (
    slugify,
    auto_excerpt,
    demote_body_h1,
    english_slug,
    auto_draft_enabled,
    render_sources_section,
    render_kroki_png,
    render_mermaid_png,
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


# --- render_sources_section (출처 → '참고 자료' 외부 링크 섹션) ---

def test_render_sources_section_basic():
    out = render_sources_section([
        {"title": "BLS CPI", "url": "https://www.bls.gov/cpi/"},
        {"title": "Fed", "url": "https://www.federalreserve.gov"},
    ])
    assert "참고 자료" in out
    assert 'href="https://www.bls.gov/cpi/"' in out
    assert 'target="_blank"' in out
    assert 'rel="noopener"' in out  # 진짜 출처 → dofollow(nofollow 아님)
    assert "nofollow" not in out
    assert ">BLS CPI</a>" in out and ">Fed</a>" in out
    assert "data-sources-section" in out


def test_render_sources_section_dedup_http_only_and_empty():
    assert render_sources_section([]) == ""
    assert render_sources_section(None) == ""
    # http 아닌 항목은 제외 → 결과 없음
    assert render_sources_section([{"title": "x", "url": "ftp://h"}]) == ""
    # 끝 슬래시만 다른 중복 URL은 1개로
    out = render_sources_section([
        {"title": "A", "url": "https://e.com/x"},
        {"title": "B", "url": "https://e.com/x/"},
    ])
    assert out.count("<li") == 1


def test_render_sources_section_escapes():
    out = render_sources_section([
        {"title": 'a<b>&"', "url": "https://e.com/?a=1&b=2"},
    ])
    assert "<b>" not in out  # 제목 태그 이스케이프됨
    assert "a&lt;b&gt;&amp;&quot;" in out
    assert "a=1&amp;b=2" in out  # URL의 & 이스케이프


def test_render_sources_section_accepts_url_strings():
    out = render_sources_section(["https://e.com/a", "not-a-url"])
    assert out.count("<li") == 1
    assert 'href="https://e.com/a"' in out


def test_create_post_appends_sources_section(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader()
    up.create_post(
        "T", "<p>body</p>", status="publish",
        sources=[{"title": "Ref", "url": "https://e.com/r"}],
    )
    content = captured["payload"]["content"]
    assert "참고 자료" in content
    assert 'href="https://e.com/r"' in content


def test_create_post_no_sources_no_section(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader()
    up.create_post("T", "<p>body</p>", status="publish")
    assert "참고 자료" not in captured["payload"]["content"]


def test_create_post_sources_idempotent(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader()
    # 본문에 이미 섹션 마커가 있으면 다시 붙이지 않는다
    body = '<p>b</p><div data-sources-section><h2>참고 자료</h2></div>'
    up.create_post(
        "T", body, status="publish",
        sources=[{"title": "Ref", "url": "https://e.com/r"}],
    )
    assert captured["payload"]["content"].count("data-sources-section") == 1


def test_upload_post_threads_sources(monkeypatch):
    captured = _capture_post(monkeypatch)
    up = _uploader()
    up.upload_post(
        "T", "<p>b</p>", is_draft=True,
        sources=[{"title": "Ref", "url": "https://e.com/r"}],
    )
    assert 'href="https://e.com/r"' in captured["payload"]["content"]


# --- 타이틀 카드 (대표 이미지 자동 첨부) ---
import shared.title_card as tc  # noqa: E402
from shared.title_card import make_title_card, accent_for  # noqa: E402


def test_make_title_card_returns_png():
    png = make_title_card("엔비디아 실적 서프라이즈, 반도체 섹터 다시 불붙나", "섹터")
    # 시스템 폰트가 있으면 PNG 매직바이트로 시작
    if png is not None:
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png) > 1000


def test_make_title_card_empty_title_none():
    assert make_title_card("", "섹터") is None


def test_accent_for_mapping():
    assert accent_for("섹터") == (39, 174, 96)
    assert accent_for("부동산") == (217, 119, 6)
    assert accent_for("없는카테고리") == (100, 116, 139)  # 기본 슬레이트


def test_create_post_auto_featured_card(monkeypatch):
    captured = _capture_post(monkeypatch)
    monkeypatch.setenv("AUTO_FEATURED_CARD", "true")
    # 폰트 유무와 무관하게 결정적으로: 카드 생성을 스텁
    monkeypatch.setattr(tc, "make_title_card", lambda *a, **k: b"\x89PNG\r\n\x1a\nfake")
    up = _uploader()
    up.create_post("T", "<p>b</p>", categories=[7], status="publish")
    # _FakePostResp.json()의 id=1 이 featured_media로 설정됨
    assert captured["payload"].get("featured_media") == 1


def test_create_post_no_card_when_disabled(monkeypatch):
    captured = _capture_post(monkeypatch)
    monkeypatch.setenv("AUTO_FEATURED_CARD", "false")
    monkeypatch.setattr(tc, "make_title_card", lambda *a, **k: b"\x89PNG\r\n\x1a\nfake")
    up = _uploader()
    up.create_post("T", "<p>b</p>", categories=[7], status="publish")
    assert "featured_media" not in captured["payload"]


def test_create_post_explicit_featured_media_wins(monkeypatch):
    captured = _capture_post(monkeypatch)
    monkeypatch.setenv("AUTO_FEATURED_CARD", "true")
    monkeypatch.setattr(tc, "make_title_card", lambda *a, **k: b"\x89PNG\r\n\x1a\nfake")
    up = _uploader()
    up.create_post("T", "<p>b</p>", categories=[7], status="publish", featured_media=99)
    assert captured["payload"]["featured_media"] == 99  # 명시값이 카드보다 우선


# --- kroki 다중 타입 다이어그램 렌더 (png 네이티브 + svg-only→로컬 래스터화) ---
_PNG = b"\x89PNG\r\n\x1a\nfake"        # kroki png 응답
_SVG = b'<?xml version="1.0"?><svg width="100" height="50"></svg>'  # kroki svg 응답
_RASTER = b"\x89PNG\r\n\x1a\nraster"  # _svg_to_png(Chrome) 래스터화 결과


class _Resp:
    def __init__(self, status, content):
        self.status_code = status
        self.content = content

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")


def _capture_kroki(monkeypatch, png_ok=True):
    """kroki POST URL을 가로채고, /png·/svg 경로별로 응답을 흉내낸다.
    Chrome 래스터화(_svg_to_png)는 _RASTER를 돌려주도록 스텁(실제 Chrome 미실행)."""
    calls = []

    def fake_post(url, data=None, **kw):
        calls.append(url)
        if url.endswith("/png"):
            return _Resp(200, _PNG) if png_ok else _Resp(400, b"Error 400: Unsupported output format: png")
        if url.endswith("/svg"):
            return _Resp(200, _SVG)
        return _Resp(404, b"")

    monkeypatch.setattr(wp.requests, "post", fake_post)
    monkeypatch.setattr(wp, "_svg_to_png", lambda svg, *a, **k: _RASTER)
    return calls


def test_render_kroki_png_png_native_types(monkeypatch):
    calls = _capture_kroki(monkeypatch)
    assert render_mermaid_png("graph TD; a-->b") == _PNG
    assert calls[-1].endswith("/mermaid/png")
    assert render_kroki_png("digraph{a->b}", "dot") == _PNG   # dot → graphviz
    assert calls[-1].endswith("/graphviz/png")


def test_render_kroki_png_svg_only_rasterized(monkeypatch):
    calls = _capture_kroki(monkeypatch)
    # d2/wavedrom = kroki svg-only → svg 요청 후 로컬 래스터화 결과 반환, png 시도 안 함
    assert render_kroki_png("a -> b", "d2") == _RASTER
    assert calls[-1].endswith("/d2/svg")
    assert not any(c.endswith("/d2/png") for c in calls)
    assert render_kroki_png("{}", "wavedrom") == _RASTER
    assert calls[-1].endswith("/wavedrom/svg")
    assert render_kroki_png("x", "vega-lite") == _RASTER       # vega-lite → vegalite (svg-only)
    assert calls[-1].endswith("/vegalite/svg")


def test_render_kroki_png_png_unsupported_falls_back_to_svg(monkeypatch):
    # png 네이티브로 분류됐는데 kroki가 png를 거부(400)하면 svg 래스터화로 fallback
    calls = _capture_kroki(monkeypatch, png_ok=False)
    assert render_kroki_png("graph TD; a-->b", "mermaid") == _RASTER
    assert any(c.endswith("/mermaid/png") for c in calls)   # png 먼저 시도
    assert calls[-1].endswith("/mermaid/svg")               # 실패 후 svg


def test_render_kroki_png_empty_none(monkeypatch):
    _capture_kroki(monkeypatch)
    assert render_kroki_png("   ", "d2") is None


def test_svg_to_png_no_chrome_returns_none(monkeypatch):
    monkeypatch.setattr(wp, "_chrome_bin", lambda: None)
    assert wp._svg_to_png(b'<svg width="10" height="10"></svg>') is None


# --- WaveDrom 톱니 제거 (리터럴 반복 → '.') ---
def test_collapse_wave_levels_folded():
    assert wp._collapse_wave("00110011") == "0.1.0.1."
    assert wp._collapse_wave("0000") == "0..."
    assert wp._collapse_wave("1111") == "1..."
    assert wp._collapse_wave("xxzz") == "x.z."
    assert wp._collapse_wave("0.1.") == "0.1."  # 이미 dotted면 그대로


def test_collapse_wave_preserves_glitch():
    # MUX_OUT의 의도된 1주기 글리치(…101…)는 보존
    assert wp._collapse_wave("00110011001011111111") == "0.1.0.1.0.101......."


def test_collapse_wave_preserves_clock_and_busdata():
    assert wp._collapse_wave("pppp") == "pppp"   # 클럭은 접지 않음(에지 의미)
    assert wp._collapse_wave("hlhl") == "hlhl"
    assert wp._collapse_wave("2222") == "2222"   # 버스 데이터(data[] 인덱스) 보존
    assert wp._collapse_wave("====") == "===="


def test_normalize_wavedrom_only_touches_wave_field():
    src = '{"signal":[{"name":"CLK0","wave":"00110011"},{"name":"D","wave":"0000"}]}'
    out = wp._normalize_wavedrom(src)
    assert '"wave":"0.1.0.1."' in out
    assert '"wave":"0..."' in out
    assert '"name":"CLK0"' in out  # 다른 필드 불변


def test_render_kroki_png_normalizes_wavedrom(monkeypatch):
    sent = {}

    def fake_post(url, data=None, **kw):
        sent["url"] = url
        sent["data"] = data.decode() if isinstance(data, bytes) else data
        return _Resp(200, _SVG)

    monkeypatch.setattr(wp.requests, "post", fake_post)
    monkeypatch.setattr(wp, "_svg_to_png", lambda svg, *a, **k: _RASTER)
    out = render_kroki_png('{"signal":[{"name":"C","wave":"0011"}]}', "wavedrom")
    assert out == _RASTER
    assert sent["url"].endswith("/wavedrom/svg")
    assert '"wave":"0.1."' in sent["data"]  # 정규화되어 전송됨


def _diagram_block(lang, code):
    return f'<pre><code class="language-{lang}">{code}</code></pre>'


def _styled_diagram_block(lang, code):
    # AI 변환기가 실제로 내보내는 형태: <pre>에 style 속성이 붙음
    return (f'<pre style="background-color:#f8f9fa;border-radius:8px;">'
            f'<code class="language-{lang}">{code}</code></pre>')


def test_render_diagrams_converts_d2_and_wavedrom(monkeypatch):
    monkeypatch.setattr(wp, "render_kroki_png", lambda code, t, *a, **k: _PNG)
    up = _uploader()
    up.upload_media = lambda *a, **k: {"id": 5, "url": "https://x/m.png"}
    html = _diagram_block("d2", "a -> b") + _diagram_block("wavedrom", "{}")
    out = up._render_diagrams_in_html(html)
    assert out.count("<figure") == 2          # 다이어그램 2개
    assert out.count('class="gm-lb"') == 2     # 각자 라이트박스 오버레이
    assert "language-d2" not in out and "language-wavedrom" not in out


def test_render_diagrams_matches_styled_pre(monkeypatch):
    # 회귀: <pre style="…">도 매칭해야 함(AI 변환기가 bare/styled를 비결정적으로 출력)
    monkeypatch.setattr(wp, "render_kroki_png", lambda code, t, *a, **k: _PNG)
    up = _uploader()
    up.upload_media = lambda *a, **k: {"id": 7, "url": "https://x/d.png"}
    html = _styled_diagram_block("mermaid", "graph TD; a-->b")
    out = up._render_diagrams_in_html(html)
    assert "<figure" in out and "language-mermaid" not in out


def test_render_diagrams_lightbox_style_once(monkeypatch):
    monkeypatch.setattr(wp, "render_kroki_png", lambda code, t, *a, **k: _PNG)
    up = _uploader()
    up.upload_media = lambda *a, **k: {"id": 5, "url": "https://x/m.png"}
    html = _diagram_block("d2", "a -> b") + _diagram_block("mermaid", "x")
    out = up._render_diagrams_in_html(html)
    assert out.count("data-gm-lightbox") == 1   # 스타일 블록은 글당 1회
    assert "cursor:zoom-in" in out              # 썸네일 확대 커서
    assert out.count('href="#gm-lb-') == 2      # 썸네일→오버레이 링크 2개


def test_render_diagrams_leaves_plain_code_untouched(monkeypatch):
    monkeypatch.setattr(wp, "render_kroki_png", lambda *a, **k: _PNG)
    up = _uploader()
    up.upload_media = lambda *a, **k: {"id": 5, "url": "https://x/m.png"}
    html = _diagram_block("python", "print('hi')") + _diagram_block("verilog", "module m;")
    out = up._render_diagrams_in_html(html)
    assert out == html  # 일반 코드 블록은 그대로
    assert "<img" not in out


def test_render_diagrams_keeps_block_on_render_failure(monkeypatch):
    monkeypatch.setattr(wp, "render_kroki_png", lambda *a, **k: None)  # 렌더 실패
    up = _uploader()
    up.upload_media = lambda *a, **k: {"id": 5, "url": "https://x/m.png"}
    html = _diagram_block("graphviz", "digraph{a->b}")
    out = up._render_diagrams_in_html(html)
    assert out == html  # 실패 시 원본 유지
