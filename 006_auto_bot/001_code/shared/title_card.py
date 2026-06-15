"""로컬 타이틀 카드 생성 — 봇 글의 대표 이미지(og:image용). 무료·무네트워크·결정론적.

WordPress featured image로 쓰기 위한 1200x630 PNG 바이트를 반환한다. Pillow +
시스템 한글 폰트만 사용하며, 폰트가 없거나 렌더에 실패하면 None을 반환한다
(이 경우 발행은 대표 이미지 없이 그대로 진행).
"""
from __future__ import annotations

import io
import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

W, H = 1200, 630  # og:image 표준 비율

# 카테고리(한글 이름) → 강조색 RGB. 없으면 슬레이트.
_ACCENTS = {
    "투자": (39, 174, 96), "일일시황": (39, 174, 96), "섹터": (39, 174, 96),
    "기술": (22, 160, 133), "SoC": (22, 160, 133), "SW": (22, 160, 133),
    "AI": (22, 160, 133),
    "뉴스": (52, 152, 219),
    "부동산": (217, 119, 6),
    "기타": (100, 116, 139),
}
_DEFAULT_ACCENT = (100, 116, 139)

_FONT_CANDIDATES = [
    os.getenv("TITLE_CARD_FONT", ""),
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def _font_path() -> Optional[str]:
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    return None


def accent_for(category: str) -> Tuple[int, int, int]:
    return _ACCENTS.get((category or "").strip(), _DEFAULT_ACCENT)


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _wrap(draw, text, fnt, max_w):
    """공백 우선 greedy 줄바꿈, 한 단어가 너무 길면 글자 단위로 분할."""
    lines, cur = [], ""
    for w in text.split(" "):
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        if draw.textlength(w, font=fnt) > max_w:
            chunk = ""
            for ch in w:
                if draw.textlength(chunk + ch, font=fnt) <= max_w:
                    chunk += ch
                else:
                    lines.append(chunk)
                    chunk = ch
            cur = chunk
        else:
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_title_card(title: str, category: str = "") -> Optional[bytes]:
    """제목·카테고리로 1200x630 다크 타이틀 카드 PNG 바이트 생성. 실패 시 None."""
    title = (title or "").strip()
    if not title:
        return None
    fp = _font_path()
    if not fp:
        logger.warning("title_card: 한글 폰트 없음 → 카드 생략")
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:  # Pillow 미설치 환경
        logger.warning(f"title_card: Pillow 없음({e}) → 카드 생략")
        return None
    try:
        def font(sz):
            return ImageFont.truetype(fp, sz)

        accent = accent_for(category)
        img = Image.new("RGB", (W, H), (15, 23, 42))
        d = ImageDraw.Draw(img)
        for y in range(H):  # 세로 그라데이션
            d.line([(0, y), (W, y)], fill=_lerp((15, 23, 42), (30, 41, 59), y / H))
        d.rectangle([0, 0, W, 9], fill=accent)  # 상단 강조 바

        M = 80
        y = 80
        cat = (category or "").strip()
        if cat:  # 카테고리 칩
            cf = font(30)
            asc, desc = cf.getmetrics()
            cw = d.textlength(cat, font=cf) + 40
            chh = asc + desc + 18
            d.rounded_rectangle([M, y, M + cw, y + chh], radius=16, fill=accent)
            d.text((M + 20, y + 9), cat, font=cf, fill=(255, 255, 255))
            y += chh + 46
        else:
            y += 20

        tf = font(66)  # 제목 (최대 3줄)
        lh = tf.getmetrics()[0] + tf.getmetrics()[1] + 16
        for ln in _wrap(d, title, tf, W - 2 * M)[:3]:
            d.text((M, y), ln, font=tf, fill=(241, 245, 249),
                   stroke_width=1, stroke_fill=(241, 245, 249))
            y += lh

        d.text((M, H - 92), "grace-moon.com", font=font(34), fill=accent)
        d.ellipse([W - 150, H - 118, W - 86, H - 54], outline=accent, width=5)

        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"title_card 생성 실패: {e}")
        return None
