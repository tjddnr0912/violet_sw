"""
Claude CLI를 사용한 Markdown → HTML 변환 유틸리티

Google Blogger에 최적화된 HTML을 생성합니다.
"""

import subprocess
import os
import logging

logger = logging.getLogger(__name__)

# 프롬프트 소스: blogger-html 스킬 파일이 단일 소스
SKILL_FILE = os.path.expanduser('~/.claude/skills/blogger-html/SKILL.md')
# 한글 HTML → 영문 HTML (US 현지화 + WebSearch 재검증) 스킬
EN_SKILL_FILE = os.path.expanduser('~/.claude/skills/blogger-html-en/SKILL.md')


def _load_skill(skill_path: str) -> str:
    """스킬 파일에서 YAML frontmatter를 제거한 본문 프롬프트를 로드."""
    import re

    if not os.path.exists(skill_path):
        raise FileNotFoundError(
            f"HTML 변환 스킬 파일을 찾을 수 없습니다: {skill_path}"
        )
    with open(skill_path, 'r', encoding='utf-8') as f:
        content = f.read()
    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
    logger.info(f"Loaded HTML prompt from skill: {skill_path}")
    return content.strip()


def load_prompt_template() -> str:
    """프롬프트 템플릿 로드 — blogger-html 스킬 파일이 단일 소스"""
    return _load_skill(SKILL_FILE)


def _run_claude_cli(full_prompt: str, timeout: int = 900, model: str = None) -> str:
    """Claude CLI(-p)에 프롬프트를 stdin으로 넘기고 stdout(raw)을 반환.

    긴 프롬프트는 임시 파일에 써서 stdin으로 전달한다.
    --dangerously-skip-permissions 로 도구(WebSearch/WebFetch 등)를 허용한다.
    model 지정 시 `--model <alias>`로 모델을 고정한다(미지정이면 CLI 기본값).
    """
    import tempfile

    cmd = ['claude', '-p', '--dangerously-skip-permissions']
    if model:
        cmd += ['--model', model]
    cmd += ['-']

    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(full_prompt)
            temp_file = f.name
        with open(temp_file, 'r', encoding='utf-8') as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        logger.error(f"Claude CLI timed out after {timeout} seconds")
        raise Exception("Claude CLI timed out")
    except FileNotFoundError:
        logger.error("Claude CLI not found. Is it installed and in PATH?")
        raise Exception("Claude CLI not found")
    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)

    if result.returncode != 0:
        error_msg = result.stderr or "Unknown error"
        logger.error(f"Claude CLI error (code {result.returncode}): {error_msg}")
        raise Exception(f"Claude CLI failed: {error_msg}")

    raw_output = result.stdout.strip()
    if not raw_output:
        logger.warning("Claude CLI returned empty content")
        raise Exception("Claude CLI returned empty content")
    return raw_output


def extract_title_from_response(response: str) -> str:
    """Claude 응답에서 BLOG_TITLE: 라인을 추출"""
    import re
    match = re.search(r'^BLOG_TITLE:\s*(.+)$', response, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # 마크다운 서식 제거 (혹시 포함된 경우)
        title = re.sub(r'\*{1,2}(.+?)\*{1,2}', r'\1', title)
        title = re.sub(r'^#+\s*', '', title)
        logger.info(f"Extracted BLOG_TITLE: {title}")
        return title
    return ""


def extract_html_from_response(response: str) -> str:
    """
    Claude 응답에서 순수 HTML만 추출

    - BLOG_TITLE: 라인 제거
    - 코드 블록(```html ... ```) 내용 추출
    - 또는 <div class="news-summary-wrapper"로 시작하는 부분 추출
    """
    import re

    # BLOG_TITLE: 라인 제거
    response = re.sub(r'^BLOG_TITLE:.*\n?', '', response, count=1, flags=re.MULTILINE).strip()

    # 코드 블록에서 HTML 추출
    code_block_pattern = r'```(?:html)?\s*([\s\S]*?)```'
    matches = re.findall(code_block_pattern, response)
    if matches:
        # 가장 긴 매치 사용 (전체 HTML일 가능성 높음)
        html = max(matches, key=len).strip()
        if html.startswith('<'):
            return html

    # <div class="news-summary-wrapper"로 시작하는 부분 찾기
    div_pattern = r'(<div class="news-summary-wrapper"[\s\S]*</div>)\s*$'
    match = re.search(div_pattern, response)
    if match:
        return match.group(1).strip()

    # 그냥 <로 시작하는 경우
    if response.strip().startswith('<'):
        return response.strip()

    # 추출 실패 시 원본 반환
    logger.warning("Could not extract pure HTML from response, using as-is")
    return response.strip()


def convert_md_to_html_via_claude(
    md_content: str,
    output_path: str = None,
    include_investment_disclaimer: bool = False,  # deprecated, 무시됨
    editorial: dict = None,
    apply_editorial_box: bool = True,
) -> tuple:
    """
    Claude CLI를 사용하여 Markdown을 Blogger용 HTML로 변환

    Args:
        md_content: Markdown 콘텐츠
        output_path: HTML 저장 경로 (선택)
        include_investment_disclaimer: deprecated - Claude가 내용에 따라 자체 판단
        editorial: 편집 레이어 컨텍스트(선택). 예:
            {"author": "sector", "content_type": "sector"}
            None이면 env EDITORIAL_ENABLED(기본 true) 기준으로 기본 author/disclaimer 적용.
            author 박스 + 투명성/면책 라인을 본문 끝에 덧붙여 E-E-A-T 신호를 준다.
            (Blogger는 공개 미러; 이 콘텐츠가 Tistory로 복사되어 승인/노출에 기여)

    Returns:
        tuple: (html_content, blog_title) — blog_title은 없으면 빈 문자열

    Raises:
        Exception: Claude CLI 실행 실패 시
    """
    # 프롬프트 템플릿 로드
    prompt_template = load_prompt_template()

    # 마크다운 콘텐츠 결합
    full_prompt = f"{prompt_template}\n\n{md_content}"

    logger.info(f"Calling Claude CLI for HTML conversion ({len(md_content)} chars)...")

    raw_output = _run_claude_cli(full_prompt, timeout=900, model='opus')  # opus: 긴 HTML 생성 시 출력 잘림 방지

    # 제목 추출
    blog_title = extract_title_from_response(raw_output)

    # HTML 추출 (코드 블록이나 설명 텍스트 제거)
    html_content = extract_html_from_response(raw_output)

    logger.info(f"Claude CLI conversion complete ({len(html_content)} chars)")

    # 이미지 마커 처리 (2026-05-28~)
    # SKILL.md가 본문에 [[IMAGE: <prompt>]] 마커를 1~3개 삽입할 수 있다.
    # 기능 활성화: env BLOGGER_IMAGES_ENABLED=true (default off, 호환성 보존)
    # 비활성화 모드에서도 마커는 반드시 제거 — 그렇지 않으면 원본 텍스트로 발행됨.
    html_content = _maybe_inject_images(html_content)

    # 편집 레이어 (2026-06-07~)
    # 저자(E-E-A-T) 박스 + 투명성/면책 라인을 본문 끝에 덧붙인다.
    # (AdSense 인라인 삽입은 폐지 — WordPress는 광고를 플러그인으로 처리한다.)
    # apply_editorial_box=False면 본문(body)만 반환 — 호출부가 따로 저자 박스를
    # 입힐 수 있게 한다(텔레그램봇 등).
    if apply_editorial_box:
        html_content = _maybe_apply_editorial(html_content, blog_title, editorial)

    # HTML 파일로 저장 (선택)
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML saved to: {output_path}")

    return html_content, blog_title


def _maybe_inject_images(html: str) -> str:
    """Conditionally process `[[IMAGE: prompt]]` markers in Claude HTML output.

    Modes (env BLOGGER_IMAGES_ENABLED, default 'false'):
        - 'true' / 'on' / '1' / 'yes': call shared.blogger_html_inject.inject_images
              which generates via Imagen + uploads to Cloudinary + replaces with <img>.
        - anything else: strip markers (replace with HTML comment) so they don't
              leak into published posts. Bots can write SKILL-conformant output
              without worrying whether the image pipeline is configured.

    If activation fails (missing credentials, import error), gracefully falls
    back to strip mode and logs a warning. Never blocks the upload pipeline.
    """
    import re
    import time

    enabled = os.getenv("BLOGGER_IMAGES_ENABLED", "false").lower() in ("true", "on", "1", "yes")
    marker_re = re.compile(r"\[\[IMAGE\s*:\s*(.+?)\s*\]\]", re.DOTALL)

    # Claude가 마커를 HTML 주석으로 감싸 출력하는 경우(`<!-- [[IMAGE: ...]] -->`)가 있다.
    # 그대로 두면 아래 strip/inject가 안쪽 마커만 치환해 주석이 중첩되고
    # (`<!-- <!-- ... --> -->`), 브라우저가 첫 -->에서 주석을 닫아 남은 `-->`가
    # 본문에 노출된다. 처리 전에 마커를 감싼 주석 래퍼를 먼저 벗긴다.
    html = re.sub(
        r"<!--\s*(\[\[IMAGE\s*:\s*.+?\s*\]\])\s*-->",
        r"\1",
        html,
        flags=re.DOTALL,
    )

    # Quick exit if no markers.
    if not marker_re.search(html):
        return html

    if not enabled:
        # Strip mode: replace each marker with a brief HTML comment.
        marker_count = len(marker_re.findall(html))
        logger.info(
            f"Image markers found ({marker_count}) but BLOGGER_IMAGES_ENABLED=false; stripping"
        )
        return marker_re.sub(
            lambda _: "<!-- image marker stripped (BLOGGER_IMAGES_ENABLED=false) -->",
            html,
        )

    # Active mode: delegate to the inject module.
    try:
        from shared.blogger_html_inject import inject_images
        run_id = os.getenv("BLOGGER_IMAGE_RUN_ID") or f"auto_{int(time.time())}"
        injected, stats = inject_images(html, run_id=run_id)
        logger.info(
            f"Image inject done: markers={stats.markers_found} "
            f"uploaded={stats.images_uploaded} failed={stats.failed} "
            f"run_id={run_id}"
        )
        return injected
    except Exception as e:
        # Never block publishing on image failure.
        logger.warning(f"Image inject pipeline failed ({e}); stripping markers")
        return marker_re.sub(
            lambda _: f"<!-- image inject failed: {str(e)[:80]} -->",
            html,
        )


def _maybe_apply_editorial(html: str, title: str, editorial) -> str:
    """편집 레이어(저자 박스 + 투명성/면책)를 본문 끝에 덧붙인다.

    - editorial(dict): {"author": <key>, "content_type": <key>} (둘 다 선택)
    - editorial=None이면 env 기본값으로 동작:
        EDITORIAL_ENABLED(기본 true), EDITORIAL_AUTHOR(기본 default),
        EDITORIAL_CONTENT_TYPE(기본 general).
    실패해도 발행 파이프라인을 막지 않는다(경고 후 원본 반환).
    """
    enabled = os.getenv("EDITORIAL_ENABLED", "true").lower() in ("true", "on", "1", "yes")
    if not enabled:
        return html

    ctx = editorial or {}
    author_key = ctx.get("author") or os.getenv("EDITORIAL_AUTHOR", "default")
    content_type = ctx.get("content_type") or os.getenv("EDITORIAL_CONTENT_TYPE", "general")

    try:
        from shared.editorial import apply_editorial
        return apply_editorial(html, author_key=author_key, content_type=content_type)
    except Exception as e:
        logger.warning(f"Editorial layer failed ({e}); skipping")
        return html


if __name__ == "__main__":
    # 테스트용
    test_md = """# 테스트 제목

오늘의 뉴스 요약입니다.

## 🏛️ 정치

1. **첫 번째 뉴스**: 중요한 내용입니다.
2. **두 번째 뉴스**: 또 다른 중요한 내용입니다.

## 💰 경제

- 경제 뉴스 1
- 경제 뉴스 2
"""

    try:
        html, title = convert_md_to_html_via_claude(test_md)
        print(f"=== Blog Title: {title} ===")
        print("=== Generated HTML ===")
        print(html)
    except Exception as e:
        print(f"Error: {e}")
