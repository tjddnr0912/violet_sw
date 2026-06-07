"""편집 레이어 (Editorial Layer) — 애드센스 승인 신호 주입.

봇이 생성한 본문 HTML 끝에 다음을 덧붙여 E-E-A-T(전문성·신뢰) 신호를 준다:
  - 저자 박스 (C1): 식별 가능한 저자 + 전문성
  - 면책/투명성 라인 (C4): 정보 제공 목적 고지 + "자동 분석 + 사람 감수" 투명성

설계 배경: docs/ADSENSE_EDITORIAL_LAYER.md
Blogger는 공개 미러로 두되, 이 콘텐츠가 승인된 Tistory로 복사되므로
편집 신호가 그대로 따라가 승인/검색 노출에 기여한다.

모든 HTML은 인라인 스타일만 사용한다(<script>/<style> 금지 — Tistory가 sanitize).
재실행 시 중복 삽입을 막기 위해 마커 주석을 검사한다.
"""

from __future__ import annotations

import json
import logging
import os
import html as _html
from datetime import datetime

logger = logging.getLogger(__name__)

_MARKER = "<!-- editorial-layer -->"
_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config",
    "authors.json",
)

# content_type → 면책 문구. 키가 없으면 면책 없이 투명성 라인만 붙는다.
_DISCLAIMERS = {
    "investment": "본 글은 정보 제공을 목적으로 하며, 특정 종목의 매수·매도 권유가 아닙니다. 모든 투자 판단과 책임은 투자자 본인에게 있습니다.",
    "buffett": "본 글은 가치투자 관점의 해석을 정보 제공 목적으로 제공하며, 특정 종목의 매수·매도 권유가 아닙니다. 투자 판단과 책임은 본인에게 있습니다.",
    "sector": "본 글은 섹터 동향 정보를 제공할 뿐 특정 종목·섹터의 매매를 권유하지 않습니다. 투자 판단과 책임은 본인에게 있습니다.",
    "realestate": "본 글은 공개 실거래 데이터를 바탕으로 한 정보 제공 목적이며, 특정 지역·물건의 매매를 권유하지 않습니다. 거래 판단과 책임은 본인에게 있습니다.",
}

# 중립적 신뢰 라인. blogger-html SKILL.md가 "AI/자동 생성 문구 금지"를 명시하므로
# 자동화/AI를 언급하지 않고 "데이터·출처 기반 + 최종 업데이트일"만 표기한다(신선도 신호).
_TRANSPARENCY = "본 글은 공개된 데이터와 출처를 바탕으로 작성했습니다."

_authors_cache: dict | None = None


def _load_authors() -> dict:
    global _authors_cache
    if _authors_cache is None:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                _authors_cache = json.load(f)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"authors.json load failed ({e}); using built-in default")
            _authors_cache = {}
    return _authors_cache


def get_author(author_key: str) -> dict:
    authors = _load_authors()
    if author_key in authors and isinstance(authors[author_key], dict):
        return authors[author_key]
    if "default" in authors and isinstance(authors["default"], dict):
        return authors["default"]
    return {
        "name": "오구 인베스트 리서치",
        "title": "데이터 기반 시장·투자 분석",
        "bio": "공개 데이터를 수집·집계하여 분석하고 발행 전 사람이 감수합니다.",
        "avatar": "",
        "links": [],
    }


def _avatar_html(author: dict) -> str:
    avatar = (author.get("avatar") or "").strip()
    if avatar:
        return (
            f'<img src="{_html.escape(avatar, quote=True)}" alt="" '
            'style="width:48px;height:48px;border-radius:50%;object-fit:cover;flex:0 0 auto;">'
        )
    initial = (author.get("name") or "O").strip()[:1]
    return (
        '<div style="width:48px;height:48px;border-radius:50%;flex:0 0 auto;'
        "background:#111827;color:#fff;display:flex;align-items:center;"
        'justify-content:center;font-weight:700;font-size:18px;">'
        f"{_html.escape(initial)}</div>"
    )


def _links_html(author: dict) -> str:
    links = author.get("links") or []
    if not links:
        return ""
    parts = []
    for ln in links:
        if not isinstance(ln, dict):
            continue
        url = (ln.get("url") or "").strip()
        label = (ln.get("label") or url).strip()
        if not url:
            continue
        parts.append(
            f'<a href="{_html.escape(url, quote=True)}" '
            'style="color:#2563eb;text-decoration:none;font-size:12px;margin-right:12px;">'
            f"{_html.escape(label)}</a>"
        )
    if not parts:
        return ""
    return '<div style="margin-top:10px;">' + "".join(parts) + "</div>"


def author_box_html(author_key: str) -> str:
    a = get_author(author_key)
    name = _html.escape(a.get("name", ""))
    title = _html.escape(a.get("title", ""))
    bio = _html.escape(a.get("bio", ""))
    return (
        '<div style="margin:40px 0 0;padding:20px 22px;border:1px solid #e5e7eb;'
        'border-radius:14px;background:#fafafa;">'
        '<div style="display:flex;align-items:center;gap:14px;">'
        f"{_avatar_html(a)}"
        "<div>"
        f'<div style="font-weight:700;font-size:15px;color:#111827;">{name}</div>'
        f'<div style="font-size:13px;color:#6b7280;margin-top:2px;">{title}</div>'
        "</div></div>"
        f'<p style="margin:12px 0 0;font-size:13px;line-height:1.7;color:#4b5563;">{bio}</p>'
        f"{_links_html(a)}"
        "</div>"
    )


def disclaimer_html(content_type: str) -> str:
    text = _DISCLAIMERS.get((content_type or "").lower())
    if not text:
        return ""
    return (
        '<div style="margin:16px 0 0;padding:12px 16px;border-left:3px solid #d1d5db;'
        'background:#f9fafb;font-size:12px;line-height:1.7;color:#6b7280;">'
        f"{_html.escape(text)}</div>"
    )


def transparency_html(updated_date: str | None = None) -> str:
    date = updated_date or datetime.now().strftime("%Y-%m-%d")
    return (
        '<p style="margin:14px 0 0;font-size:12px;color:#9ca3af;">'
        f"{_html.escape(_TRANSPARENCY)} 최종 업데이트: {_html.escape(date)}</p>"
    )


def apply_editorial(
    html: str,
    author_key: str = "default",
    content_type: str = "general",
    updated_date: str | None = None,
    include_disclaimer: bool = False,
) -> str:
    """본문 HTML 끝에 저자(E-E-A-T) 박스 + 신뢰/업데이트 라인을 덧붙인다.

    면책 조항은 기본적으로 blogger-html SKILL.md가 콘텐츠 맥락에 맞춰 본문에
    이미 넣으므로(중복 방지) 여기서는 추가하지 않는다. 결정적(deterministic)
    면책이 필요하면 include_disclaimer=True 로 content_type 기반 면책을 덧붙인다.

    이미 마커가 있으면(재실행) 중복 삽입하지 않는다.
    """
    if not html:
        return html
    if _MARKER in html:
        return html

    disclaimer = disclaimer_html(content_type) if include_disclaimer else ""
    block = (
        f"\n{_MARKER}\n"
        '<div style="margin-top:40px;border-top:1px solid #f0f0f0;padding-top:8px;">'
        f"{author_box_html(author_key)}"
        f"{disclaimer}"
        f"{transparency_html(updated_date)}"
        "</div>\n"
    )
    return html + block
