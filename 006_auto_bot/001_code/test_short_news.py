#!/usr/bin/env python3
"""
짧은 뉴스로 테스트
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# API 키 설정
api_key = "REDACTED_KEY"
genai.configure(api_key=api_key)

# 모델 설정
model = genai.GenerativeModel('gemini-2.5-flash')

# Raw news 파일 읽기 (처음 5000자만)
raw_news_path = "../004_News_paper/20251020/raw_news_by_category_20251020_232949.md"
print(f"📂 Reading: {raw_news_path}")

with open(raw_news_path, 'r', encoding='utf-8') as f:
    raw_markdown = f.read()[:10000]  # 처음 10000자만

print(f"📏 File size: {len(raw_markdown)} characters (truncated)\n")

# Prompt 구성
prompt = f"""You are a professional news blogger. Create a brief Korean summary of these news articles.

Raw News:
{raw_markdown}

Create a friendly blog-style summary in Korean. Focus on key points.

Summary:"""

print(f"📝 Prompt size: {len(prompt)} characters\n")

# Safety 설정: BLOCK_NONE
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

print("🔄 Gemini API 호출 중 (짧은 버전)...\n")

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

        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"🔒 Safety ratings: {candidate.safety_ratings}\n")

        if candidate.finish_reason == 1:
            blog_summary = response.text
            print(f"✅ 성공! ({len(blog_summary)} chars)")
            print("\n" + "="*60)
            print(blog_summary[:500])
            print("="*60)
        else:
            print(f"❌ Finish reason: {candidate.finish_reason}")
            print(f"Safety ratings: {candidate.safety_ratings}")

    else:
        print("❌ No candidates")

except Exception as e:
    print(f"❌ Error: {str(e)}")
