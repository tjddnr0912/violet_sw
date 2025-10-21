#!/usr/bin/env python3
"""
간단한 뉴스 요약 테스트
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# API 키 설정
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY environment variable is not set. Please set it in .env file or export it.")
genai.configure(api_key=api_key)

# 모델 설정
model = genai.GenerativeModel('gemini-2.5-flash')

# Safety 설정
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
}

# 테스트 뉴스
test_news = """
# 원본 뉴스 기사 모음

## 🏛️ 정치

### 1. 캄보디아 사망 대학생 유해 고국으로

**출처:** 연합뉴스
**발행일:** 2025-10-20 13:36

캄보디아 범죄 단지에서 고문 후 살해된 대학생의 유해가 국내로 곧 송환됩니다.
21일 오전 우리나라에 도착할 예정이며, 한국 경찰과 캄보디아 수사당국이 부검을 진행한 결과
시신 훼손은 발견되지 않았습니다.

## 💰 경제

### 2. 주식 시장 상승세

**출처:** SBS
**발행일:** 2025-10-20 14:00

코스피가 3,700선을 돌파하며 강세를 보이고 있습니다.
외국인 투자자들의 순매수가 이어지면서 시장에 활기를 더하고 있습니다.
"""

prompt = f"""You are a professional news blogger who creates engaging, easy-to-read news summaries in Korean.

Input: Raw news articles organized by category

Raw News Content:
{test_news}

Your task:
1. Create a blog-style summary in Korean (한국어)
2. Organize by categories with emoji icons
3. For each category, summarize key points in a conversational style
4. Keep it friendly and easy to understand

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

print("🔄 뉴스 요약 테스트 시작...\n")
print(f"📝 Input size: {len(prompt)} chars")
print(f"📰 Test news size: {len(test_news)} chars\n")

try:
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=2000,
        ),
        safety_settings=safety_settings
    )

    if response.candidates:
        candidate = response.candidates[0]
        print(f"✅ Gemini 응답 받음!")
        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"   1 = STOP (성공)")
        print(f"   2 = SAFETY (차단)")
        print(f"   3 = MAX_TOKENS")
        print(f"   4 = OTHER\n")

        if candidate.finish_reason == 1:
            print(f"💬 요약 결과 ({len(response.text)} chars):")
            print("="*60)
            print(response.text)
            print("="*60)
        else:
            print(f"❌ 요약 실패!")
            print(f"🔒 Safety ratings: {candidate.safety_ratings}")
    else:
        print("❌ No candidates in response")

except Exception as e:
    print(f"❌ Error: {str(e)}")
