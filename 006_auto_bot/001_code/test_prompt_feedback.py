#!/usr/bin/env python3
"""
Prompt feedback 확인
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

import google.generativeai as genai

# API 키 설정
api_key = "REDACTED_KEY"
genai.configure(api_key=api_key)

# 모델 설정
model = genai.GenerativeModel('gemini-2.5-flash')

# Raw news 파일 읽기
raw_news_path = "../004_News_paper/20251020/raw_news_by_category_20251020_232949.md"

with open(raw_news_path, 'r', encoding='utf-8') as f:
    raw_markdown = f.read()[:3000]  # 3000자만

print(f"📏 Input size: {len(raw_markdown)} characters\n")
print("=" * 60)
print("입력 내용 미리보기:")
print(raw_markdown[:500])
print("...")
print("=" * 60)

# 매우 간단한 프롬프트
prompt = f"""Please summarize this text briefly in Korean:

{raw_markdown}"""

print("\n🔄 Gemini API 호출 중...\n")

try:
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.5,
            max_output_tokens=500,
        )
    )

    # Prompt feedback 확인 (입력이 차단되었는지)
    print("📋 Prompt Feedback:")
    print(f"   Block reason: {response.prompt_feedback.block_reason}")
    print(f"   Safety ratings: {response.prompt_feedback.safety_ratings}\n")

    if response.candidates:
        candidate = response.candidates[0]

        print(f"📊 Response Finish Reason: {candidate.finish_reason}")
        print(f"🔒 Response Safety Ratings: {candidate.safety_ratings}\n")

        if candidate.finish_reason == 1:
            print(f"✅ 성공! ({len(response.text)} chars)")
            print(response.text[:500])
        else:
            print(f"❌ 차단됨: finish_reason = {candidate.finish_reason}")

    else:
        print("❌ No candidates (입력 프롬프트가 차단되었을 수 있음)")

except Exception as e:
    print(f"❌ Error: {str(e)}")
