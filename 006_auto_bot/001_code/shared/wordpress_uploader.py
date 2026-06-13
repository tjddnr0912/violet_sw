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
import html as _html
import hashlib
import logging
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

_RE_MERMAID_BLOCK = re.compile(
    r'<pre>\s*<code[^>]*class="[^"]*language-mermaid[^"]*"[^>]*>(.*?)</code>\s*</pre>',
    re.S | re.I,
)

# 발행 끝에 붙는 '원본 데이터(raw source)' 접힘 블록 제거용
_RE_RAW_SOURCE = re.compile(
    r'(?:<!--\s*raw-source-details\s*-->\s*)?<details\b[^>]*>(?:(?!</details>).)*?'
    r'(?:원본 데이터 보기|raw source)(?:(?!</details>).)*?</details>',
    re.S | re.I,
)


def render_mermaid_png(code: str, timeout: int = 40) -> Optional[bytes]:
    """mermaid 소스 → PNG 바이트(kroki). 실패 시 None."""
    code = _html.unescape(code or "").strip()
    if not code:
        return None
    try:
        r = requests.post(
            f"{KROKI_URL.rstrip('/')}/mermaid/png",
            data=code.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=timeout,
        )
        if r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n":
            return r.content
        logger.warning(f"mermaid PNG 렌더 실패 {r.status_code}: {r.text[:120]}")
    except Exception as e:
        logger.error(f"mermaid PNG 렌더 오류: {e}")
    return None


def strip_raw_source(html: str) -> str:
    """발행 HTML 끝의 '원본 데이터 보기(raw source)' <details> 블록을 제거."""
    if not html:
        return html
    return _RE_RAW_SOURCE.sub('', html)


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

    def _render_diagrams_in_html(self, html_content: str) -> str:
        """<pre><code class="language-mermaid"> 블록을 PNG <img>로 치환.

        PNG로 렌더 → WP 미디어 업로드 → <figure><img>. 실패 시 원본 유지.
        동일 다이어그램은 해시 파일명으로 중복 업로드 방지.
        """
        if not html_content or "language-mermaid" not in html_content:
            return html_content

        def _repl(m):
            code = _html.unescape(m.group(1) or "").strip()
            png = render_mermaid_png(code)
            if not png:
                return m.group(0)
            digest = hashlib.md5(code.encode("utf-8")).hexdigest()[:12]
            media = self.upload_media(png, f"diagram-{digest}.png", "image/png")
            if not media or not media.get("url"):
                return m.group(0)
            return (
                '<figure style="margin:24px auto;text-align:center;">'
                f'<img src="{media["url"]}" alt="diagram" '
                'style="max-width:100%;height:auto;" loading="lazy" /></figure>'
            )

        return _RE_MERMAID_BLOCK.sub(_repl, html_content)

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

        payload: Dict = {
            "title": title,
            "content": content_html,
            "status": status or os.getenv("WORDPRESS_DEFAULT_STATUS", "publish"),
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
        if slug:
            payload["slug"] = slug
        if excerpt:
            payload["excerpt"] = excerpt
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
    ) -> Dict:
        """레거시 업로더 upload_post 호환 시그니처.

        labels→WP 태그, is_draft→status, 다이어그램 자동 렌더.
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
    """local_archive 형식(제목/태그/빈줄/HTML) 파일을 파싱.

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
