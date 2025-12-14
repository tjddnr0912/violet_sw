#!/usr/bin/env python3
"""
HTML to Markdown Converter
--------------------------
티스토리 블로그 콘텐츠에 최적화된 HTML -> Markdown 변환기
"""

import re
from typing import Optional
from bs4 import BeautifulSoup, NavigableString, Tag

try:
    import markdownify
    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False

try:
    import html2text
    HAS_HTML2TEXT = True
except ImportError:
    HAS_HTML2TEXT = False


class HTMLToMarkdownConverter:
    """HTML을 Markdown으로 변환하는 클래스"""

    def __init__(self, use_library: str = 'auto'):
        """
        Initialize converter

        Args:
            use_library: 사용할 라이브러리
                        'markdownify', 'html2text', 'builtin', 'auto'
        """
        self.use_library = use_library

        if use_library == 'auto':
            if HAS_MARKDOWNIFY:
                self.use_library = 'markdownify'
            elif HAS_HTML2TEXT:
                self.use_library = 'html2text'
            else:
                self.use_library = 'builtin'

    def convert(self, html: str) -> str:
        """
        HTML을 Markdown으로 변환

        Args:
            html: HTML 문자열

        Returns:
            Markdown 문자열
        """
        if not html:
            return ""

        # 전처리
        html = self._preprocess(html)

        # 변환
        if self.use_library == 'markdownify':
            markdown = self._convert_markdownify(html)
        elif self.use_library == 'html2text':
            markdown = self._convert_html2text(html)
        else:
            markdown = self._convert_builtin(html)

        # 후처리
        markdown = self._postprocess(markdown)

        return markdown

    def _preprocess(self, html: str) -> str:
        """HTML 전처리"""
        soup = BeautifulSoup(html, 'html.parser')

        # 스크립트, 스타일 제거
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()

        # 빈 태그 정리
        for tag in soup.find_all():
            if tag.name in ['div', 'span', 'p'] and not tag.text.strip() and not tag.find('img'):
                tag.decompose()

        # 티스토리 특수 요소 처리
        # 코드 블록 (티스토리 syntax highlighter)
        for code_block in soup.select('.colorscripter-code, .hljs, pre code'):
            # 언어 감지 시도
            lang = ''
            classes = code_block.get('class', [])
            for cls in classes:
                if cls.startswith('language-'):
                    lang = cls.replace('language-', '')
                    break

            # 코드 블록으로 변환
            code_text = code_block.get_text()
            new_tag = soup.new_tag('pre')
            code_tag = soup.new_tag('code')
            if lang:
                code_tag['class'] = f'language-{lang}'
            code_tag.string = code_text
            new_tag.append(code_tag)
            code_block.replace_with(new_tag)

        # 인용구 처리
        for blockquote in soup.select('blockquote, .quote'):
            blockquote.name = 'blockquote'

        # 더보기 접기 처리
        for spoiler in soup.select('.moreless_content, .toggle_content'):
            # 내용을 일반 div로 변환
            spoiler.name = 'div'

        return str(soup)

    def _convert_markdownify(self, html: str) -> str:
        """markdownify 라이브러리 사용"""
        if not HAS_MARKDOWNIFY:
            return self._convert_builtin(html)

        return markdownify.markdownify(
            html,
            heading_style='atx',
            bullets='-',
            code_language='',
            strip=['script', 'style'],
            escape_asterisks=False,
            escape_underscores=False
        )

    def _convert_html2text(self, html: str) -> str:
        """html2text 라이브러리 사용"""
        if not HAS_HTML2TEXT:
            return self._convert_builtin(html)

        h = html2text.HTML2Text()
        h.body_width = 0  # 줄바꿈 비활성화
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False
        h.skip_internal_links = True
        h.inline_links = True
        h.protect_links = True
        h.unicode_snob = True

        return h.handle(html)

    def _convert_builtin(self, html: str) -> str:
        """내장 변환기 사용 (의존성 없음)"""
        soup = BeautifulSoup(html, 'html.parser')
        return self._element_to_markdown(soup)

    def _element_to_markdown(self, element, depth: int = 0) -> str:
        """HTML 요소를 Markdown으로 변환 (재귀)"""
        if isinstance(element, NavigableString):
            text = str(element)
            # 연속 공백 정리
            text = re.sub(r'\s+', ' ', text)
            return text

        if not isinstance(element, Tag):
            return ""

        tag_name = element.name.lower() if element.name else ""
        children_md = ''.join(
            self._element_to_markdown(child, depth)
            for child in element.children
        )

        # 태그별 변환
        if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_name[1])
            return f"\n{'#' * level} {children_md.strip()}\n\n"

        elif tag_name == 'p':
            return f"\n{children_md.strip()}\n\n"

        elif tag_name == 'br':
            return "  \n"

        elif tag_name in ['strong', 'b']:
            return f"**{children_md}**"

        elif tag_name in ['em', 'i']:
            return f"*{children_md}*"

        elif tag_name in ['del', 's', 'strike']:
            return f"~~{children_md}~~"

        elif tag_name == 'code':
            if element.parent and element.parent.name == 'pre':
                return children_md
            return f"`{children_md}`"

        elif tag_name == 'pre':
            code = element.find('code')
            if code:
                lang = ''
                classes = code.get('class', [])
                for cls in classes:
                    if cls.startswith('language-'):
                        lang = cls.replace('language-', '')
                        break
                code_text = code.get_text().strip()
                return f"\n```{lang}\n{code_text}\n```\n\n"
            return f"\n```\n{children_md.strip()}\n```\n\n"

        elif tag_name == 'blockquote':
            lines = children_md.strip().split('\n')
            quoted = '\n'.join(f"> {line}" for line in lines)
            return f"\n{quoted}\n\n"

        elif tag_name == 'a':
            href = element.get('href', '')
            title = element.get('title', '')
            text = children_md.strip() or href
            if title:
                return f'[{text}]({href} "{title}")'
            return f"[{text}]({href})"

        elif tag_name == 'img':
            src = element.get('src', element.get('data-src', ''))
            alt = element.get('alt', '')
            title = element.get('title', '')
            if title:
                return f'![{alt}]({src} "{title}")'
            return f"![{alt}]({src})"

        elif tag_name == 'ul':
            items = []
            for li in element.find_all('li', recursive=False):
                item_md = self._element_to_markdown(li, depth + 1).strip()
                items.append(f"{'  ' * depth}- {item_md}")
            return '\n' + '\n'.join(items) + '\n\n'

        elif tag_name == 'ol':
            items = []
            for i, li in enumerate(element.find_all('li', recursive=False), 1):
                item_md = self._element_to_markdown(li, depth + 1).strip()
                items.append(f"{'  ' * depth}{i}. {item_md}")
            return '\n' + '\n'.join(items) + '\n\n'

        elif tag_name == 'li':
            return children_md

        elif tag_name == 'hr':
            return "\n---\n\n"

        elif tag_name == 'table':
            return self._table_to_markdown(element)

        elif tag_name == 'figure':
            # figure 안의 이미지와 캡션 처리
            img = element.find('img')
            caption = element.find('figcaption')
            result = ""
            if img:
                result = self._element_to_markdown(img)
            if caption:
                result += f"\n*{caption.get_text().strip()}*\n"
            return result

        elif tag_name in ['div', 'section', 'article', 'main', 'span']:
            return children_md

        elif tag_name in ['script', 'style', 'noscript', 'nav', 'header', 'footer']:
            return ""

        else:
            return children_md

    def _table_to_markdown(self, table: Tag) -> str:
        """HTML 테이블을 Markdown 테이블로 변환"""
        rows = []

        # thead 처리
        thead = table.find('thead')
        if thead:
            header_row = thead.find('tr')
            if header_row:
                headers = [th.get_text().strip() for th in header_row.find_all(['th', 'td'])]
                if headers:
                    rows.append('| ' + ' | '.join(headers) + ' |')
                    rows.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

        # tbody 처리
        tbody = table.find('tbody') or table
        for tr in tbody.find_all('tr'):
            cells = [td.get_text().strip() for td in tr.find_all(['td', 'th'])]
            if cells:
                # 헤더 행이 없으면 첫 행을 헤더로
                if not rows:
                    rows.append('| ' + ' | '.join(cells) + ' |')
                    rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
                else:
                    rows.append('| ' + ' | '.join(cells) + ' |')

        if rows:
            return '\n' + '\n'.join(rows) + '\n\n'
        return ""

    def _postprocess(self, markdown: str) -> str:
        """Markdown 후처리"""
        # 연속된 빈 줄 정리
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # 문장 시작/끝 공백 정리
        markdown = markdown.strip()

        # 줄 끝 공백 정리 (줄바꿈 유지용 2칸 제외)
        lines = markdown.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.endswith('  '):  # 줄바꿈용 2칸 공백 유지
                cleaned_lines.append(line.rstrip() + '  ')
            else:
                cleaned_lines.append(line.rstrip())
        markdown = '\n'.join(cleaned_lines)

        # HTML 엔티티 변환
        html_entities = {
            '&nbsp;': ' ',
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&quot;': '"',
            '&#39;': "'",
            '&ldquo;': '"',
            '&rdquo;': '"',
            '&lsquo;': "'",
            '&rsquo;': "'",
            '&mdash;': '—',
            '&ndash;': '–',
            '&hellip;': '…',
            '&copy;': '©',
            '&reg;': '®',
            '&trade;': '™'
        }

        for entity, char in html_entities.items():
            markdown = markdown.replace(entity, char)

        return markdown


# CLI 테스트용
if __name__ == '__main__':
    import sys

    test_html = """
    <h1>테스트 제목</h1>
    <p>이것은 <strong>굵은 글씨</strong>와 <em>기울임</em> 테스트입니다.</p>

    <h2>코드 예시</h2>
    <pre><code class="language-python">
def hello():
    print("Hello, World!")
    </code></pre>

    <h2>목록</h2>
    <ul>
        <li>항목 1</li>
        <li>항목 2</li>
        <li>항목 3</li>
    </ul>

    <h2>인용</h2>
    <blockquote>
        이것은 인용문입니다.
    </blockquote>

    <h2>이미지</h2>
    <img src="test.jpg" alt="테스트 이미지">

    <h2>링크</h2>
    <p><a href="https://example.com">예시 링크</a></p>

    <h2>테이블</h2>
    <table>
        <thead>
            <tr><th>이름</th><th>나이</th></tr>
        </thead>
        <tbody>
            <tr><td>홍길동</td><td>30</td></tr>
            <tr><td>김철수</td><td>25</td></tr>
        </tbody>
    </table>
    """

    converter = HTMLToMarkdownConverter()
    result = converter.convert(test_html)

    print("=" * 50)
    print("Converted Markdown:")
    print("=" * 50)
    print(result)
