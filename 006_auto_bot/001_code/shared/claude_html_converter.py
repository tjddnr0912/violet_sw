"""
Claude CLI를 사용한 Markdown → HTML 변환 유틸리티

Google Blogger에 최적화된 HTML을 생성합니다.
"""

import subprocess
import os
import logging

logger = logging.getLogger(__name__)

# 프롬프트 파일 경로
PROMPT_FILE = os.path.join(
    os.path.dirname(__file__),
    '..', 'prompts', 'blogger_html_prompt.md'
)


def load_prompt_template() -> str:
    """프롬프트 템플릿 파일 로드"""
    if not os.path.exists(PROMPT_FILE):
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_FILE}")

    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def extract_html_from_response(response: str) -> str:
    """
    Claude 응답에서 순수 HTML만 추출

    - 코드 블록(```html ... ```) 내용 추출
    - 또는 <div class="news-summary-wrapper"로 시작하는 부분 추출
    """
    import re

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


def convert_md_to_html_via_claude(md_content: str, output_path: str = None) -> str:
    """
    Claude CLI를 사용하여 Markdown을 Blogger용 HTML로 변환

    Args:
        md_content: Markdown 콘텐츠
        output_path: HTML 저장 경로 (선택)

    Returns:
        변환된 HTML 문자열

    Raises:
        Exception: Claude CLI 실행 실패 시
    """
    import tempfile

    # 프롬프트 템플릿 로드 + 마크다운 콘텐츠 결합
    prompt_template = load_prompt_template()
    full_prompt = f"{prompt_template}\n\n{md_content}"

    logger.info(f"Calling Claude CLI for HTML conversion ({len(md_content)} chars)...")

    # 긴 프롬프트는 임시 파일에 저장 후 stdin으로 전달
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(full_prompt)
            temp_file = f.name

        # stdin으로 프롬프트 전달 (긴 인자 문제 방지)
        with open(temp_file, 'r', encoding='utf-8') as f:
            result = subprocess.run(
                ['claude', '-p', '-'],  # '-'는 stdin에서 읽음
                stdin=f,
                capture_output=True,
                text=True,
                timeout=600  # 10분 타임아웃 (HTML 디자인 생성에 시간 소요)
            )

        # 임시 파일 정리
        os.unlink(temp_file)

    except subprocess.TimeoutExpired:
        if 'temp_file' in locals():
            os.unlink(temp_file)
        logger.error("Claude CLI timed out after 600 seconds")
        raise Exception("Claude CLI timed out")
    except FileNotFoundError:
        if 'temp_file' in locals():
            os.unlink(temp_file)
        logger.error("Claude CLI not found. Is it installed and in PATH?")
        raise Exception("Claude CLI not found")

    if result.returncode != 0:
        error_msg = result.stderr or "Unknown error"
        logger.error(f"Claude CLI error (code {result.returncode}): {error_msg}")
        raise Exception(f"Claude CLI failed: {error_msg}")

    raw_output = result.stdout.strip()

    if not raw_output:
        logger.warning("Claude CLI returned empty content")
        raise Exception("Claude CLI returned empty content")

    # HTML 추출 (코드 블록이나 설명 텍스트 제거)
    html_content = extract_html_from_response(raw_output)

    logger.info(f"Claude CLI conversion complete ({len(html_content)} chars)")

    # HTML 파일로 저장 (선택)
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logger.info(f"HTML saved to: {output_path}")

    return html_content


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
        html = convert_md_to_html_via_claude(test_md)
        print("=== Generated HTML ===")
        print(html)
    except Exception as e:
        print(f"Error: {e}")
