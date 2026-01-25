# Blogger HTML 변환 프롬프트

아래 마크다운 콘텐츠를 Google Blogger에 최적화된 HTML로 변환해줘.

## Order Guide

1. **보충자료 필요성 검토, 자료 보충 (2026년 최신자료)**
2. **블로그 스타일로 재구성 (이모지 사용)**
3. **HTML 포맷으로 작성**
   - 심플하고 핵심이 돋보이는 모던한 디자인
   - 예시 코드들의 경우 가독성 있는 코드 포맷 사용
   - text wrap은 mobile과 PC web에서 오차가 생기지 않게 맞출 것
   - ASCII 다이어그램이 깨지는 경우가 많음. ASCII 아트 대신 **HTML/CSS 박스 기반 다이어그램** 사용할 것
4. **구글 블로그스팟과 충돌나지 않게 CSS, ::before 등에 주의**

## 외부 플랫폼 삽입용 HTML 필수 사항

1. 전체를 고유한 wrapper 클래스로 감싸기 (예: `.news-summary-wrapper`)
2. 모든 `color`, `background-color` 속성에 `!important` 사용
3. h1~h6, p, span, td, th 등 텍스트 요소에 인라인 style로 색상 명시
4. heading 태그에 `background: none !important`, `border: none !important` 추가
5. 외부 테마가 덮어쓸 수 있는 기본 스타일(margin, padding, font-size) 모두 명시적 지정

## 출력 형식 (매우 중요! 반드시 준수!)

**절대 금지:**
- 파일 저장 요청하지 말 것 (파일 쓰기 권한 요청 금지)
- 설명문, 소개문, 결론문 출력 금지
- 코드블록(```) 사용 금지
- 마크다운 문법 사용 금지
- "변환 완료", "저장됩니다" 등의 안내 문구 금지

**필수 사항:**
- `<html>`, `<head>`, `<body>` 태그 제외 (Blogger가 추가함)
- 첫 글자부터 마지막 글자까지 **순수 HTML 코드만** 출력
- 응답의 첫 문자는 반드시 `<`로 시작
- 응답은 반드시 `<div class="news-summary-wrapper"`로 시작해야 함
- 응답의 마지막은 반드시 `</div>`로 끝나야 함
- 중간에 어떤 설명이나 텍스트도 삽입하지 말 것

**요약: HTML 태그만 출력하세요. 다른 어떤 것도 출력하지 마세요.**

---

## 변환할 마크다운:
