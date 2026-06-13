"""발행 로컬 백업 아카이브 (WordPress 발행본의 로컬 사본).

봇이 생성한 한글 HTML을 '실제 오늘 날짜' 폴더에 저장한다.
사용자가 vim으로 확인한 뒤 그대로 복사해 티스토리에 붙여 넣는다.

파일 구성(순서 고정): 제목 → 태그 → 내용(HTML).

날짜는 호출 시점마다 datetime.now()로 다시 확인하므로,
프로그램이 자정을 넘겨 장시간 떠 있어도 항상 그날 폴더에 저장된다.
"""

from __future__ import annotations

import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_BASE = "~/blog_posts"  # env TISTORY_ARCHIVE_DIR 로 override


def _slugify(title: str, maxlen: int = 50) -> str:
    """파일명용 슬러그. 한글·영숫자는 보존, 나머지는 _로."""
    title = (title or "untitled").strip()
    s = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:maxlen] or "untitled"


def save_post_draft(
    title: str,
    tags,
    html: str,
    base_dir: str | None = None,
    when: datetime | None = None,
) -> str:
    """한글 HTML을 오늘 날짜 폴더에 저장하고 전체 경로를 반환.

    Args:
        title: 글 제목 (한글)
        tags: 태그 리스트 (Blogger 라벨과 동일). None 허용.
        html: 본문 HTML
        base_dir: 저장 루트 (기본 env TISTORY_ARCHIVE_DIR 또는 ~/blog_posts)
        when: 날짜/시각 주입 (테스트용). None이면 호출 시점 datetime.now().

    Returns:
        저장된 파일의 절대 경로.
    """
    now = when or datetime.now()
    base = os.path.expanduser(base_dir or os.getenv("TISTORY_ARCHIVE_DIR", DEFAULT_BASE))
    day_dir = os.path.join(base, now.strftime("%Y-%m-%d"))
    os.makedirs(day_dir, exist_ok=True)

    tags_line = ", ".join(t for t in (tags or []) if t)
    fname = f"{now.strftime('%H%M%S')}_{_slugify(title)}.txt"
    path = os.path.join(day_dir, fname)

    body = f"제목: {title}\n태그: {tags_line}\n\n{html or ''}\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)

    logger.info(f"Saved local backup: {path}")
    return path
