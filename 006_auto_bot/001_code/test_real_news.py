#!/usr/bin/env python3
"""
실제 raw news 파일로 Gemini API 테스트
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

# Raw news 파일 읽기
raw_news_path = "../004_News_paper/20251020/raw_news_by_category_20251020_232949.md"
print(f"📂 Reading: {raw_news_path}")

with open(raw_news_path, 'r', encoding='utf-8') as f:
    raw_markdown = f.read()

print(f"📏 File size: {len(raw_markdown)} characters\n")

# Prompt 구성
prompt = f"""You are a professional news blogger who creates engaging, easy-to-read news summaries in Korean.

IMPORTANT CONTEXT: You are receiving a collection of legitimate news articles from major Korean news organizations. Please create an informative blog post summarizing these articles for journalistic purposes.

Input: Raw news articles organized by category (정치, 경제, 사회, 국제, 문화, IT/과학)

Raw News Content:
{raw_markdown}

Your task:
1. Create a blog-style summary in Korean (한국어)
2. Organize by categories with emoji icons: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학
3. For each category:
   - Write a brief introduction (2-3 sentences)
   - Summarize 2-3 key news items in a conversational, engaging style
   - Use bullet points for key facts
   - Include important context and implications
4. Writing style:
   - Friendly, conversational Korean (반말 금지, 존댓말 사용)
   - Clear and easy to understand
   - Focus on "why this matters" not just "what happened"
   - Use natural transitions between topics
5. Structure:
   - Start with a brief greeting and overview
   - Category sections with summaries
   - End with a closing remark

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

print(f"📝 Prompt size: {len(prompt)} characters\n")

# Safety 설정: BLOCK_NONE
print("🔒 Safety settings: BLOCK_NONE (모든 필터 비활성화)\n")

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

print("🔄 Gemini API 호출 중...\n")

try:
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=4000,
        ),
        safety_settings=safety_settings
    )

    if response.candidates:
        candidate = response.candidates[0]

        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"   1 = STOP (성공)")
        print(f"   2 = SAFETY (차단)")
        print(f"   3 = MAX_TOKENS")
        print(f"   4 = OTHER\n")

        print(f"🔒 Safety ratings: {candidate.safety_ratings}\n")

        if candidate.finish_reason == 1:
            blog_summary = response.text
            print(f"✅ 성공! 블로그 요약 생성됨 ({len(blog_summary)} chars)")
            print("\n" + "="*60)
            print(blog_summary[:1000] + "...")  # 처음 1000자만 출력
            print("="*60)

            # 파일로 저장
            output_path = "../004_News_paper/20251020/test_blog_summary.md"
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(blog_summary)
            print(f"\n💾 저장됨: {output_path}")

        elif candidate.finish_reason == 2:
            print("❌ SAFETY 필터에 차단됨!")
            print(f"🔒 Safety ratings:\n{candidate.safety_ratings}")
        else:
            print(f"❌ 예상치 못한 finish_reason: {candidate.finish_reason}")

    else:
        print("❌ No candidates in response")
        print(f"Response: {response}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
