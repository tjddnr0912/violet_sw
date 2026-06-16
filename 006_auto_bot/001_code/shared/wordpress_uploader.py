"""WordPress REST 자동발행 업로더 (Blogger 대체).

grace-moon.com WordPress에 글을 발행한다.
인증: Application Password + HTTP Basic Auth.

환경변수(.env):
    WORDPRESS_URL=https://grace-moon.com
    WORDPRESS_USER=<login id>
    WORDPRESS_APP_PASSWORD=<application password>   # 공백 자동 제거
    WORDPRESS_DEFAULT_STATUS=publish

사용 예:
    from shared.wordpress_uploader import WordPressUploader
    wp = WordPressUploader()
    res = wp.create_post(title, html, categories=["뉴스"], tags=["AI"], status="publish")
    if res["success"]:
        print(res["url"])
"""

from __future__ import annotations

import os
import re
import math
import html as _html
import hashlib
import logging
import shutil
import subprocess
import tempfile
from typing import Optional, List, Dict, Union

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# grace-moon.com 카테고리 이름 → term_id (2026-06 생성)
CATEGORY_IDS: Dict[str, int] = {
    "투자": 2, "기술": 3, "기타": 4,
    "뉴스": 5, "일일시황": 6, "섹터": 7, "부동산": 8,
    "SoC": 9, "SW": 10, "AI": 11,
}

# term_id → 이름 (타이틀 카드 카테고리 라벨용 역매핑)
CATEGORY_NAMES: Dict[int, str] = {v: k for k, v in CATEGORY_IDS.items()}


def auto_draft_enabled() -> bool:
    """investment_bot 계열 자동봇(뉴스/버핏/섹터/부동산)의 강제 draft 토글.

    .env `AUTO_BOT_DRAFT_ONLY` (default true) — true면 자동봇이 발행하는 모든
    글을 publish 대신 draft로 올린다. 텔레그램 봇은 이 함수를 쓰지 않으므로
    영향을 받지 않는다(계속 publish). 다시 자동 발행하려면 false로 바꾼다.
    """
    return os.getenv("AUTO_BOT_DRAFT_ONLY", "true").strip().lower() == "true"


def auto_featured_card_enabled() -> bool:
    """봇 글에 대표 이미지(로컬 타이틀 카드)를 자동 생성·첨부할지 토글.

    .env `AUTO_FEATURED_CARD` (default false). true면 featured_media 미지정 글에
    제목·카테고리 기반 타이틀 카드를 만들어 og:image/썸네일로 붙인다. 카드 생성/
    업로드 실패 시 조용히 건너뛰고 발행은 그대로 진행한다.
    """
    return os.getenv("AUTO_FEATURED_CARD", "false").strip().lower() == "true"

# --- AdSense 제거 패턴 (본문 중간 광고 블록) ---
# <ins class="adsbygoogle" ...></ins>
_RE_ADS_INS = re.compile(r'<ins\b[^>]*adsbygoogle[^>]*>(?:(?!</ins>).)*?</ins>', re.S | re.I)
# 빈 로더: <script ... googlesyndication|adsbygoogle ...></script>
_RE_ADS_LOADER = re.compile(r'<script\b[^>]*(?:googlesyndication|adsbygoogle)[^>]*>\s*</script>', re.S | re.I)
# push 스크립트: <script> (adsbygoogle = ...).push({}) </script>  (다른 </script> 넘지 않음)
_RE_ADS_PUSH = re.compile(r'<script\b[^>]*>(?:(?!</script>).)*?adsbygoogle(?:(?!</script>).)*?</script>', re.S | re.I)
# 광고를 감싸던 빈 spacer div 가 2개 이상 연속되면 1개로 축소
_RE_SPACER_RUN = re.compile(r'(?:\s*<div style="margin:\s*24px 0;"></div>\s*){2,}', re.I)


def strip_adsense(html: str) -> str:
    """본문 HTML에서 Google AdSense 코드(ins/loader/push 스크립트)를 제거."""
    if not html:
        return html
    html = _RE_ADS_INS.sub('', html)
    html = _RE_ADS_LOADER.sub('', html)
    html = _RE_ADS_PUSH.sub('', html)
    html = _RE_SPACER_RUN.sub('\n<div style="margin: 24px 0;"></div>\n', html)
    return html


# --- Mermaid 다이어그램 → PNG 이미지 (kroki 렌더 + WP 미디어 업로드) ---
# 인라인 SVG는 WP 본문 처리(wpautop/style)에 의해 도형이 깨진다.
# 그래서 PNG로 평탄화해 미디어로 업로드하고 <img>로 삽입한다(어디서나 안전).
KROKI_URL = os.getenv("KROKI_URL", "https://kroki.io")

# 코드펜스 언어명 → kroki 경로명.
# 여기에 있는 언어만 다이어그램으로 렌더하고, 일반 코드 블록(python/c/verilog/bash 등
# 여기 없는 language-*)은 그대로 둔다. SoC/AI 기술 글에 유용한 타입 중심.
_LANG_TO_KROKI = {
    "mermaid": "mermaid",
    "d2": "d2",
    "graphviz": "graphviz", "dot": "graphviz",
    "plantuml": "plantuml", "puml": "plantuml",
    "wavedrom": "wavedrom",          # 디지털 신호 타이밍 다이어그램 (SoC/RTL)
    "vega-lite": "vegalite", "vegalite": "vegalite",
    "vega": "vega",
    "blockdiag": "blockdiag",
    "nomnoml": "nomnoml",
    "erd": "erd",
    "pikchr": "pikchr",
    "svgbob": "svgbob",
    "bytefield": "bytefield",
    "structurizr": "structurizr",
    "excalidraw": "excalidraw",
}

# language-<type> 코드 블록 일반 매칭. 타입 판별은 _repl에서 _LANG_TO_KROKI로.
# <pre>에 style 등 속성이 붙어도 매칭(AI 변환기가 <pre style="…">를 비결정적으로 붙임).
_RE_DIAGRAM_BLOCK = re.compile(
    r'<pre[^>]*>\s*<code[^>]*class="[^"]*language-([a-z0-9][a-z0-9-]*)[^"]*"[^>]*>'
    r'(.*?)</code>\s*</pre>',
    re.S | re.I,
)

# 다이어그램 클릭 확대(라이트박스): 순수 CSS :target (JS 없음 → WAF 안전).
# WordPress unfiltered_html 사용자라 <style> 블록이 보존됨(드래프트 프로브로 확인).
_LIGHTBOX_STYLE = (
    '<style data-gm-lightbox>'
    '.gm-lb{display:none;position:fixed;inset:0;z-index:99999;'
    'background:rgba(0,0,0,.9);align-items:center;justify-content:center;'
    'padding:16px;cursor:zoom-out;}'
    '.gm-lb:target{display:flex;}'
    '.gm-lb img{max-width:96vw;max-height:96vh;width:auto;height:auto;'
    'box-shadow:0 0 40px rgba(0,0,0,.5);}'
    '</style>'
)

# 코드블록 대비(contrast) 보정: AI가 <pre style="background:#2c3e50"><code> 같은 다크 박스로
# 수식/평문을 넣으면, 테마의 `code{background:연한색}` 규칙이 안쪽 <code>에 적용돼
# 밝은 글자가 밝은 배경에 묻혀 보이지 않는다(라이브 확인). inline-background를 가진 <pre>
# 안의 <code>만 배경 투명·색 상속으로 강제해 <pre>의 의도된 배경이 보이게 한다(일반 코드블록 무관).
_CODEFIX_STYLE = (
    '<style data-gm-codefix>'
    'pre[style*="background"] code{background:transparent!important;color:inherit!important}'
    '</style>'
)
_RE_STYLED_PRE_CODE = re.compile(r'<pre[^>]*style="[^"]*background[^"]*"[^>]*>\s*<code', re.I)


def fix_styled_code_contrast(html: str) -> str:
    """inline-background <pre><code> 다크 박스가 테마 code 배경에 묻히는 문제를 보정.

    해당 패턴이 있고 아직 보정 스타일이 없으면 스코프된 <style>를 1회 주입.
    """
    if not html or "data-gm-codefix" in html:
        return html
    if _RE_STYLED_PRE_CODE.search(html):
        return _CODEFIX_STYLE + html
    return html

# 발행 끝에 붙는 '원본 데이터(raw source)' 접힘 블록 제거용
_RE_RAW_SOURCE = re.compile(
    r'(?:<!--\s*raw-source-details\s*-->\s*)?<details\b[^>]*>(?:(?!</details>).)*?'
    r'(?:원본 데이터 보기|raw source)(?:(?!</details>).)*?</details>',
    re.S | re.I,
)


# kroki가 PNG 출력을 지원하지 않는(SVG 전용) 타입. 이들은 SVG를 받아 로컬에서
# PNG로 래스터화한다. 목록이 불완전해도 정상 동작(누락 시 png 1회 시도→실패→svg fallback)
# 하므로 어디까지나 불필요한 요청을 줄이는 최적화 힌트다. (kroki: d2/wavedrom 등은 svg-only)
_KROKI_SVG_ONLY = {
    "d2", "wavedrom", "nomnoml", "pikchr", "svgbob", "vega", "vegalite",
    "excalidraw", "bytefield", "structurizr", "wireviz", "symbolator",
    "tikz", "bpmn", "dbml",
}

# headless Chrome (SVG→PNG 래스터화용). env override 우선.
_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
]


def _chrome_bin() -> Optional[str]:
    cand = os.getenv("CHROME_BIN", "").strip()
    if cand and os.path.exists(cand):
        return cand
    for c in _CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("chrome")


def _svg_to_png(svg_bytes: bytes, scale: int = 2, max_px: int = 4000, timeout: int = 60) -> Optional[bytes]:
    """SVG 바이트 → PNG 바이트 (headless Chrome 래스터화). 실패/Chrome 부재 시 None.

    SVG 본연 크기(width/height 또는 viewBox)로 윈도우를 잡고 스크린샷한다.
    인라인 SVG는 WordPress wpautop/sanitize에 깨지므로, kroki가 svg만 주는 타입
    (d2/wavedrom 등)도 이렇게 PNG로 평탄화해 mermaid와 동일한 미디어 경로를 탄다.
    """
    chrome = _chrome_bin()
    if not chrome:
        logger.warning("SVG→PNG: Chrome 미발견(CHROME_BIN 설정 필요) — 다이어그램 렌더 스킵")
        return None
    try:
        text = svg_bytes.decode("utf-8", "replace")
        w = h = None
        mw = re.search(r'<svg[^>]*\bwidth="([\d.]+)', text)
        mh = re.search(r'<svg[^>]*\bheight="([\d.]+)', text)
        if mw and mh:
            w, h = float(mw.group(1)), float(mh.group(1))
        if not (w and h):
            vb = re.search(r'viewBox="[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)"', text)
            if vb:
                w, h = float(vb.group(1)), float(vb.group(2))
        if not (w and h) or w < 1 or h < 1:
            logger.warning("SVG→PNG: 크기 파싱 실패")
            return None
        W, H = int(math.ceil(w)), int(math.ceil(h))
        eff_scale = scale if (W * scale <= max_px and H * scale <= max_px) else 1
        with tempfile.TemporaryDirectory() as d:
            sp = os.path.join(d, "in.svg")
            pp = os.path.join(d, "out.png")
            with open(sp, "wb") as f:
                f.write(svg_bytes)
            cmd = [
                chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                f"--force-device-scale-factor={eff_scale}",
                "--default-background-color=FFFFFFFF",
                f"--screenshot={pp}", f"--window-size={W},{H}",
                "--virtual-time-budget=2000", f"file://{sp}",
            ]
            subprocess.run(cmd, capture_output=True, timeout=timeout)
            if os.path.exists(pp):
                with open(pp, "rb") as f:
                    png = f.read()
                if png[:8] == b"\x89PNG\r\n\x1a\n":
                    return png
        logger.warning("SVG→PNG: Chrome 스크린샷 산출 실패")
    except Exception as e:
        logger.error(f"SVG→PNG 래스터화 오류: {e}")
    return None


# WaveDrom 톱니 제거: 같은 레벨을 리터럴 반복(0000/1111)하면 매 주기 경계에 재샘플
# notch(톱니)가 생긴다. 인접 동일한 '레벨' 기호({0,1,x,z})만 '.'(이전 상태 유지)로 접어
# 톱니를 없앤다. 클럭(p/n/P/N/h/l/H/L)·버스 데이터(=,2-9; data[] 라벨 인덱스와 결합)·
# gap(|)은 반복에 의미가 있어 건드리지 않는다. 의도된 1주기 글리치(예: 101)는 인접
# 비동일이라 그대로 보존된다.
_WAVE_LEVEL = set("01xz")
_RE_WAVE_FIELD = re.compile(r'("wave"\s*:\s*")([^"\\]*)(")')


def _collapse_wave(wave: str) -> str:
    """wave 문자열에서 안전한 레벨 반복을 '.'로 접는다(클럭·버스데이터·글리치 보존)."""
    out: List[str] = []
    held = None  # 현재 유지 중인 레벨('.' 가 가리키는 값)
    for ch in wave:
        if ch == ".":
            out.append(".")
            continue
        if ch in _WAVE_LEVEL and ch == held:
            out.append(".")
        else:
            out.append(ch)
            held = ch
    return "".join(out)


def _normalize_wavedrom(code: str) -> str:
    """WaveDrom 소스의 모든 "wave": "..." 값을 _collapse_wave로 정규화.

    JSON 파싱 없이 wave 필드만 치환하므로 원본 포맷/loose-JSON에도 안전.
    """
    return _RE_WAVE_FIELD.sub(
        lambda m: m.group(1) + _collapse_wave(m.group(2)) + m.group(3), code
    )


def render_kroki_png(code: str, diagram_type: str = "mermaid", timeout: int = 40) -> Optional[bytes]:
    """다이어그램 소스 → PNG 바이트. 실패 시 None.

    diagram_type: 코드펜스 언어명(mermaid/d2/graphviz/wavedrom/plantuml…) 또는 kroki 경로명.
    kroki가 PNG를 주면 그대로, **SVG만 주는 타입(d2/wavedrom 등)은 SVG→PNG 로컬 래스터화**.
    """
    code = _html.unescape(code or "").strip()
    if not code:
        return None
    t = (diagram_type or "").strip().lower()
    kroki_type = _LANG_TO_KROKI.get(t, t)
    if not kroki_type:
        return None
    if kroki_type == "wavedrom":
        code = _normalize_wavedrom(code)  # 리터럴 반복(0000) → '.'(톱니 제거)
    base = KROKI_URL.rstrip("/")
    # svg-only로 알려진 타입은 svg부터, 그 외는 png→(실패 시)svg 순으로 시도.
    formats = ["svg"] if kroki_type in _KROKI_SVG_ONLY else ["png", "svg"]
    try:
        for fmt in formats:
            r = requests.post(
                f"{base}/{kroki_type}/{fmt}",
                data=code.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=timeout,
            )
            if r.status_code != 200:
                logger.warning(f"{kroki_type}/{fmt} 렌더 실패 {r.status_code}: {r.text[:120]}")
                continue
            if fmt == "png":
                if r.content[:8] == b"\x89PNG\r\n\x1a\n":
                    return r.content
                # kroki가 png 미지원(보통 400) → svg fallback으로 진행
            else:  # svg → 로컬 PNG 래스터화
                if b"<svg" in r.content[:1000]:
                    png = _svg_to_png(r.content)
                    if png:
                        return png
                    logger.warning(f"{kroki_type}: svg→png 래스터화 실패(Chrome 확인)")
    except Exception as e:
        logger.error(f"{kroki_type} 렌더 오류: {e}")
    return None


def render_mermaid_png(code: str, timeout: int = 40) -> Optional[bytes]:
    """mermaid 소스 → PNG 바이트(kroki). 하위호환 래퍼 (render_kroki_png 위임)."""
    return render_kroki_png(code, "mermaid", timeout)


def strip_raw_source(html: str) -> str:
    """발행 HTML 끝의 '원본 데이터 보기(raw source)' <details> 블록을 제거."""
    if not html:
        return html
    return _RE_RAW_SOURCE.sub('', html)


# --- 본문 H1 강등 (테마가 글 제목을 <h1>로 렌더하므로 본문은 h2부터) ---
# Rank Math "Single H1" 규칙: 페이지에 H1은 1개여야 한다.
# 봇 본문이 헤드라인을 <h1>로 넣으면 테마 제목과 합쳐 2개가 되어 빨간 X.
_RE_H1_OPEN = re.compile(r'<h1(\s[^>]*)?>', re.I)
_RE_H1_CLOSE = re.compile(r'</h1\s*>', re.I)


def demote_body_h1(html: str) -> str:
    """본문 HTML의 <h1>…</h1>를 <h2>…</h2>로 강등(테마 제목 h1만 유일하게 남김)."""
    if not html:
        return html
    html = _RE_H1_OPEN.sub(lambda m: "<h2" + (m.group(1) or "") + ">", html)
    return _RE_H1_CLOSE.sub("</h2>", html)


# --- 출처/외부 링크 섹션 (Rank Math 'outbound links' + E-E-A-T + AdSense 가치) ---
# 봇이 조사한 출처 [{title, url}, …]를 본문 끝에 클릭 가능한 '참고 자료' 링크로 렌더한다.
# AI HTML 변환(blogger-html SKILL)은 '과정 흔적 제거' 단계에서 출처를 비결정적으로
# 누락시키므로, 모든 봇이 거치는 발행 단계(업로더)에서 결정론적으로 붙인다.
_RE_SOURCES_MARKER = re.compile(r'data-sources-section', re.I)
_RE_URL = re.compile(r'https?://', re.I)


def render_sources_section(sources, heading: str = "참고 자료", max_items: int = 12) -> str:
    """출처 리스트 → '참고 자료' 외부 링크 섹션 HTML. 빈/무효면 ''.

    - sources: [{"title": str, "url": str}, …] 또는 ["http…", …]
    - http(s) URL만, 중복 URL 제거(끝 슬래시 무시), 최대 max_items개.
    - 진짜 출처이므로 dofollow(rel="noopener", nofollow 아님) + 새 탭.
    """
    items: List[str] = []
    seen = set()
    for s in (sources or []):
        if isinstance(s, dict):
            url = (s.get("url") or "").strip()
            title = (s.get("title") or url).strip()
        elif isinstance(s, str):
            url = s.strip()
            title = url
        else:
            continue
        if not _RE_URL.match(url):
            continue
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        title_e = _html.escape(title or url)
        url_e = _html.escape(url, quote=True)
        items.append(
            f'<li style="margin:6px 0;"><a href="{url_e}" target="_blank" '
            f'rel="noopener" style="color:#2980b9 !important;">{title_e}</a></li>'
        )
        if len(items) >= max_items:
            break
    if not items:
        return ""
    h = _html.escape(heading)
    return (
        '\n<div data-sources-section style="margin:28px 0 0 0;">'
        f'<h2 style="font-size:22px;font-weight:700;color:#2c3e50 !important;'
        f'background:none !important;border:none !important;">{h}</h2>'
        '<ul style="list-style:none;padding-left:0;margin:12px 0 0 0;">'
        + "".join(items)
        + "</ul></div>\n"
    )


# --- 메타 설명용 자동 excerpt (Rank Math가 글 발췌를 메타 description으로 사용) ---
_RE_HEADING_BLOCK = re.compile(r'<h[1-6]\b[^>]*>.*?</h[1-6]>', re.S | re.I)
_RE_TAG = re.compile(r'<[^>]+>')
_RE_WS = re.compile(r'\s+')


def auto_excerpt(html: str, max_len: int = 155) -> str:
    """본문 HTML에서 메타 설명용 발췌를 생성.

    헤딩 블록을 건너뛴 첫 본문 텍스트를 max_len 자 내에서 단어 경계로 자른다.
    """
    if not html:
        return ""
    text = _RE_HEADING_BLOCK.sub(" ", html)
    text = _RE_TAG.sub(" ", text)
    text = _html.unescape(text)
    text = _RE_WS.sub(" ", text).strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    sp = cut.rfind(" ")
    if sp > max_len * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" .,") + "…"


# --- 한글 제목 → ASCII 슬러그 (국립국어원 로마자 표기, 단순화) ---
_RR_CHO = ['g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's', 'ss',
           '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h']
_RR_JUNG = ['a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa', 'wae',
            'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'eu', 'ui', 'i']
_RR_JONG = ['', 'k', 'k', 'ks', 'n', 'nj', 'nh', 't', 'l', 'lk', 'lm', 'lb',
            'ls', 'lt', 'lp', 'lh', 'm', 'p', 'ps', 't', 't', 'ng', 't', 't',
            'k', 't', 'p', 't']


def _romanize_char(ch: str) -> str:
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        cho, rem = divmod(code, 21 * 28)
        jung, jong = divmod(rem, 28)
        return _RR_CHO[cho] + _RR_JUNG[jung] + _RR_JONG[jong]
    if ch.isalnum() and ch.isascii():
        return ch
    return " "


def slugify(text: str, max_words: int = 6, max_len: int = 60) -> str:
    """한글/영문 제목을 ASCII 케밥 슬러그로 변환(로마자 표기). 빈 결과면 ''."""
    if not text:
        return ""
    romanized = "".join(_romanize_char(c) for c in text).lower()
    words = [w for w in _RE_WS.sub(" ", romanized).split(" ") if w]
    slug = "-".join(words[:max_words])[:max_len].strip("-")
    return slug


_RE_HANGUL = re.compile(r"[가-힣]")


def _kebab(text: str, max_words: int = 8, max_len: int = 70) -> str:
    """임의 텍스트 → 소문자 ASCII 케밥(영숫자만, 단어/길이 캡)."""
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    words = [w for w in text.split("-") if w]
    return "-".join(words[:max_words])[:max_len].strip("-")


def english_slug(title: str) -> str:
    """제목 → 의미가 담긴 영어 슬러그.

    한글이 없으면 그대로 케밥화. 한글이면 Gemini로 짧은 영어 슬러그를 번역
    생성하고, 실패하면 로마자 표기(`slugify`)로 폴백한다.
    """
    if not title:
        return ""
    if not _RE_HANGUL.search(title):
        return _kebab(title) or slugify(title)
    try:
        from shared.gemini_cli import call_gemini_with_fallback
        prompt = (
            "Convert this Korean blog post title into a concise, SEO-friendly "
            "English URL slug.\n"
            "Rules: lowercase, 3-7 words, hyphen-separated, no articles (a/the/of), "
            "no punctuation, keep technical acronyms (AI, PQC, SoC, GPU, ETF). "
            "Output ONLY the slug, nothing else.\n\n"
            f"Title: {title}"
        )
        resp = call_gemini_with_fallback(
            prompt, use_grounding=False, temperature=0.0, max_output_tokens=40
        )
        slug = _kebab(resp.text or "")
        if slug and slug.isascii() and len(slug) >= 3:
            return slug
        logger.warning(f"english_slug 결과 부적합('{slug}'), 로마자 폴백")
    except Exception as e:
        logger.warning(f"english_slug Gemini 실패({e}), 로마자 폴백")
    return slugify(title)


class WordPressUploader:
    """WordPress REST API 글 발행기."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        user: Optional[str] = None,
        app_password: Optional[str] = None,
        timeout: int = 30,
        default_categories: Optional[List[Union[str, int]]] = None,
        default_status: Optional[str] = None,
        strip_ads_default: bool = False,
        force_draft: bool = False,
        **_ignored,  # 레거시 호환: blog_id/credentials_path/token_path 등 무시
    ):
        self.base_url = (base_url or os.getenv("WORDPRESS_URL", "")).rstrip("/")
        self.user = user or os.getenv("WORDPRESS_USER", "")
        pw = app_password or os.getenv("WORDPRESS_APP_PASSWORD", "")
        self.app_password = pw.replace(" ", "")  # WP는 표시용 공백 제거 후 검증
        self.timeout = timeout
        self.api = f"{self.base_url}/wp-json/wp/v2"
        self.auth = HTTPBasicAuth(self.user, self.app_password)
        self._tag_cache: Dict[str, int] = {}
        # Blogger 드롭인용 기본값
        self.default_categories = default_categories or []
        self.default_status = default_status
        self.strip_ads_default = strip_ads_default
        # True면 status 인자와 무관하게 항상 draft로 발행(자동봇 일시정지용)
        self.force_draft = force_draft

    # --- 상태 ---
    def is_configured(self) -> bool:
        return bool(self.base_url and self.user and self.app_password)

    def verify(self) -> bool:
        """자격증명 유효성 확인 (GET /users/me)."""
        if not self.is_configured():
            logger.warning("WordPress 설정 누락 (.env WORDPRESS_* 확인)")
            return False
        try:
            r = requests.get(f"{self.api}/users/me", auth=self.auth, timeout=self.timeout)
            ok = r.status_code == 200
            if not ok:
                logger.error(f"WP verify 실패 {r.status_code}: {r.text[:160]}")
            return ok
        except Exception as e:
            logger.error(f"WP verify 오류: {e}")
            return False

    # --- 카테고리/태그 해석 ---
    def resolve_categories(self, categories) -> List[int]:
        """이름('뉴스') 또는 ID(5) 혼합 리스트 → term_id 리스트."""
        out: List[int] = []
        for c in (categories or []):
            if isinstance(c, int):
                out.append(c)
            elif isinstance(c, str) and c.strip().isdigit():
                out.append(int(c.strip()))
            elif isinstance(c, str) and c.strip() in CATEGORY_IDS:
                out.append(CATEGORY_IDS[c.strip()])
            else:
                logger.warning(f"알 수 없는 카테고리(건너뜀): {c!r}")
        return out

    def ensure_tags(self, names) -> List[int]:
        """태그 이름 리스트 → tag_id 리스트(없으면 생성)."""
        ids: List[int] = []
        for name in (names or []):
            name = (name or "").strip()
            if not name:
                continue
            if name in self._tag_cache:
                ids.append(self._tag_cache[name])
                continue
            tid = self._find_or_create_tag(name)
            if tid:
                self._tag_cache[name] = tid
                ids.append(tid)
        return ids

    def _find_or_create_tag(self, name: str) -> Optional[int]:
        try:
            r = requests.get(f"{self.api}/tags", params={"search": name},
                             auth=self.auth, timeout=self.timeout)
            if r.ok:
                for t in r.json():
                    if t.get("name", "").strip().lower() == name.lower():
                        return t["id"]
            r = requests.post(f"{self.api}/tags", json={"name": name},
                              auth=self.auth, timeout=self.timeout)
            if r.status_code in (200, 201):
                return r.json().get("id")
            data = r.json() if r.content else {}
            if data.get("code") == "term_exists":
                d = data.get("data", {})
                return d.get("term_id") or d.get("resource_id")
            logger.warning(f"태그 생성 실패 {name!r}: {r.status_code} {r.text[:120]}")
        except Exception as e:
            logger.error(f"태그 처리 오류 {name!r}: {e}")
        return None

    # --- 미디어 ---
    def upload_media(self, data: bytes, filename: str, mime: str = "image/png") -> Optional[Dict]:
        """이미지 바이트를 WP 미디어로 업로드. 반환 {id, url} 또는 None."""
        try:
            r = requests.post(
                f"{self.api}/media",
                data=data,
                headers={
                    "Content-Type": mime,
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
                auth=self.auth,
                timeout=self.timeout,
            )
            if r.status_code in (200, 201):
                d = r.json()
                return {"id": d.get("id"), "url": d.get("source_url")}
            logger.error(f"미디어 업로드 실패 {r.status_code}: {r.text[:160]}")
        except Exception as e:
            logger.error(f"미디어 업로드 오류: {e}")
        return None

    def _category_label(self, categories) -> str:
        """카드 칩에 쓸 카테고리 이름 1개를 고른다(이름/ID 혼합 리스트 허용)."""
        for c in (categories or []):
            if isinstance(c, str) and c.strip() in CATEGORY_IDS:
                return c.strip()
            try:
                cid = int(c)
            except (TypeError, ValueError):
                continue
            if cid in CATEGORY_NAMES:
                return CATEGORY_NAMES[cid]
        return ""

    def _ensure_title_card(self, title, categories) -> Optional[int]:
        """제목·카테고리로 타이틀 카드를 만들어 미디어 업로드. 반환 media id 또는 None."""
        try:
            from shared.title_card import make_title_card
        except Exception:
            return None
        label = self._category_label(categories)
        png = make_title_card(title, label)
        if not png:
            return None
        digest = hashlib.md5(f"{title}|{label}".encode("utf-8")).hexdigest()[:12]
        media = self.upload_media(png, f"card-{digest}.png", "image/png")
        return media.get("id") if media else None

    def _render_diagrams_in_html(self, html_content: str) -> str:
        """<pre [..]><code class="language-{mermaid|d2|graphviz|wavedrom|plantuml…}">
        블록을 kroki로 PNG 렌더 → WP 미디어 업로드 → <figure><img>로 치환.

        - 지원 다이어그램 언어(_LANG_TO_KROKI)만 변환. 일반 코드 블록
          (python/c/verilog 등)은 그대로 둔다.
        - 동일 다이어그램은 (타입+소스) 해시 파일명으로 중복 업로드 방지.
        - 렌더/업로드 실패 시 원본 블록 유지.
        - 각 다이어그램 이미지는 클릭 시 원본 크기로 확대되는 라이트박스(순수 CSS)로 감싼다.
        """
        if not html_content or "language-" not in html_content:
            return html_content

        rendered = []  # 라이트박스 <style> 1회 주입 판단용

        def _repl(m):
            lang = (m.group(1) or "").lower()
            kroki_type = _LANG_TO_KROKI.get(lang)
            if not kroki_type:
                return m.group(0)  # 일반 코드 블록 — 변환하지 않음
            code = _html.unescape(m.group(2) or "").strip()
            png = render_kroki_png(code, kroki_type)
            if not png:
                return m.group(0)
            digest = hashlib.md5(f"{kroki_type}|{code}".encode("utf-8")).hexdigest()[:12]
            media = self.upload_media(png, f"diagram-{kroki_type}-{digest}.png", "image/png")
            if not media or not media.get("url"):
                return m.group(0)
            rendered.append(digest)
            url = media["url"]
            lb_id = f"gm-lb-{kroki_type}-{digest}"
            # 썸네일(클릭=확대) + 풀스크린 오버레이(클릭=닫기). 순수 CSS :target.
            return (
                '<figure style="margin:24px auto;text-align:center;">'
                f'<a href="#{lb_id}" aria-label="원본 크기로 확대">'
                f'<img src="{url}" alt="{kroki_type} diagram" '
                'style="max-width:100%;height:auto;cursor:zoom-in;" loading="lazy" /></a>'
                '</figure>'
                f'<a href="#_" class="gm-lb" id="{lb_id}" aria-hidden="true">'
                f'<img src="{url}" alt="{kroki_type} diagram (원본)" /></a>'
            )

        out = _RE_DIAGRAM_BLOCK.sub(_repl, html_content)
        # 라이트박스 스타일은 글당 1회만(이미 있으면 생략 — 재렌더 idempotent).
        if rendered and "data-gm-lightbox" not in out:
            out = _LIGHTBOX_STYLE + out
        return out

    # --- 발행 ---
    def create_post(
        self,
        title: str,
        content_html: str,
        categories: Optional[List[Union[str, int]]] = None,
        tags: Optional[List[Union[str, int]]] = None,
        status: Optional[str] = None,
        slug: Optional[str] = None,
        excerpt: Optional[str] = None,
        featured_media: Optional[int] = None,
        strip_ads: bool = False,
        render_diagrams: bool = False,
        strip_raw: bool = False,
        sources: Optional[List] = None,
    ) -> Dict:
        """글 1건 발행. 반환: {success, id, url, status} 또는 {success: False, error}."""
        if not self.is_configured():
            return {"success": False, "error": "WordPress 설정 누락"}

        if strip_ads:
            content_html = strip_adsense(content_html)
        if strip_raw:
            content_html = strip_raw_source(content_html)
        if render_diagrams:
            content_html = self._render_diagrams_in_html(content_html)
        # 테마가 글 제목을 <h1>로 렌더 → 본문 h1은 h2로 강등(Single-H1, Rank Math)
        content_html = demote_body_h1(content_html)
        # 출처를 결정론적으로 '참고 자료' 외부 링크 섹션으로 추가(Rank Math outbound).
        # 이미 섹션이 있으면(중복 호출) 다시 붙이지 않는다.
        if sources and not _RE_SOURCES_MARKER.search(content_html):
            content_html = content_html + render_sources_section(sources)
        # 다크 코드박스(수식 등) 대비 보정 — 테마 code 배경이 글자를 묻는 문제 방지
        content_html = fix_styled_code_contrast(content_html)

        _status = status or os.getenv("WORDPRESS_DEFAULT_STATUS", "publish")
        if self.force_draft and _status != "draft":
            logger.info("force_draft 활성 → status '%s'→'draft' 강제", _status)
            _status = "draft"
        payload: Dict = {
            "title": title,
            "content": content_html,
            "status": _status,
        }
        cat_ids = self.resolve_categories(categories)
        if cat_ids:
            payload["categories"] = cat_ids
        if tags:
            if all(isinstance(t, int) for t in tags):
                tag_ids = list(tags)
            else:
                tag_ids = self.ensure_tags(tags)
            if tag_ids:
                payload["tags"] = tag_ids
        # 슬러그 미지정 시 제목에서 의미 담긴 영어 슬러그 자동 생성
        # (한글 퍼센트 인코딩·발음 로마자 URL 방지; Gemini 실패 시 로마자 폴백)
        if not slug:
            slug = english_slug(title)
        if slug:
            payload["slug"] = slug
        # 발췌 미지정 시 본문에서 자동 생성(Rank Math 메타 description 소스)
        if not excerpt:
            excerpt = auto_excerpt(content_html)
        if excerpt:
            payload["excerpt"] = excerpt
        # 대표 이미지 미지정 시 타이틀 카드 자동 생성·첨부(og:image/썸네일). 실패 시 생략.
        if featured_media is None and auto_featured_card_enabled():
            featured_media = self._ensure_title_card(title, categories)
        if featured_media:
            payload["featured_media"] = featured_media

        try:
            r = requests.post(f"{self.api}/posts", json=payload,
                              auth=self.auth, timeout=self.timeout)
            if r.status_code in (200, 201):
                d = r.json()
                logger.info(f"WP 발행 OK id={d.get('id')} {d.get('link')}")
                return {
                    "success": True,
                    "id": d.get("id"),
                    "url": d.get("link"),
                    "status": d.get("status"),
                }
            logger.error(f"WP 발행 실패 {r.status_code}: {r.text[:200]}")
            return {"success": False, "error": f"{r.status_code} {r.text[:200]}"}
        except Exception as e:
            logger.error(f"WP 발행 오류: {e}")
            return {"success": False, "error": str(e)}

    # --- 레거시 업로더 드롭인 호환 어댑터 (봇 호출부 무수정 교체용) ---
    def _md_to_html(self, md: str) -> str:
        try:
            import markdown
            return markdown.markdown(md, extensions=["extra", "sane_lists", "nl2br"])
        except Exception:
            return md  # 변환 불가 시 원문 그대로

    def upload_post(
        self,
        title: str,
        content: str,
        labels: Optional[List[str]] = None,
        is_draft: bool = False,
        is_markdown: bool = False,
        categories: Optional[List[Union[str, int]]] = None,
        slug: Optional[str] = None,
        excerpt: Optional[str] = None,
        strip_ads: Optional[bool] = None,
        sources: Optional[List] = None,
    ) -> Dict:
        """레거시 업로더 upload_post 호환 시그니처.

        labels→WP 태그, is_draft→status, 다이어그램 자동 렌더.
        sources→본문 끝 '참고 자료' 외부 링크 섹션(있을 때만).
        반환은 레거시 형식({success, url, post_id, message})으로 맞춘다.
        """
        html_content = self._md_to_html(content) if is_markdown else content
        status = "draft" if is_draft else (
            self.default_status or os.getenv("WORDPRESS_DEFAULT_STATUS", "publish")
        )
        res = self.create_post(
            title=title,
            content_html=html_content,
            categories=categories or self.default_categories,
            tags=labels,
            status=status,
            slug=slug,
            excerpt=excerpt,
            strip_ads=self.strip_ads_default if strip_ads is None else strip_ads,
            render_diagrams=True,
            strip_raw=True,  # raw source 블록은 WP에 올리지 않음
            sources=sources,
        )
        if res.get("success"):
            return {
                "success": True,
                "url": res.get("url"),
                "post_id": res.get("id"),
                "message": "Post uploaded successfully",
            }
        return {"success": False, "message": res.get("error", "WP 발행 실패")}

    # 레거시 업로더처럼 with 문에서 쓸 수 있도록
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def parse_archive_file(path: str) -> Dict:
    """제목/태그/빈줄/HTML 형식 백업 .txt 파일을 파싱(일회성 마이그레이션용).

    Returns: {"title": str, "tags": [..], "content": html}
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    title, tags, body_lines = "", [], []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("제목:"):
            title = line[len("제목:"):].strip()
        elif line.startswith("태그:"):
            raw = line[len("태그:"):].strip()
            tags = [t.strip() for t in raw.split(",") if t.strip()]
        elif line.strip() == "" and title:
            body_lines = lines[i + 1:]
            break
        i += 1
    return {"title": title, "tags": tags, "content": "\n".join(body_lines).strip()}
