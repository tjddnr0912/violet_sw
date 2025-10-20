#!/usr/bin/env python3
"""
Safety 설정 없이 테스트
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

import google.generativeai as genai

# API 키 설정
api_key = "AIzaSyDFLJVSXHHZAueuWZPxSap4KKCfNFySk78"
genai.configure(api_key=api_key)

# 모델 설정
model = genai.GenerativeModel('gemini-2.5-flash')

# Raw news 파일 읽기 (처음 5000자만)
raw_news_path = "../004_News_paper/20251020/raw_news_by_category_20251020_232949.md"

with open(raw_news_path, 'r', encoding='utf-8') as f:
    raw_markdown = f.read()[:5000]

print(f"📏 Input size: {len(raw_markdown)} characters\n")

# 간단한 프롬프트
prompt = f"""다음 텍스트를 한국어로 간단히 요약해주세요:

{raw_markdown}

요약:"""

print("🔄 Gemini API 호출 중 (safety 설정 없음)...\n")

try:
    # Safety 설정 완전 제거
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=1000,
        )
        # safety_settings 파라미터 완전 제거
    )

    if response.candidates:
        candidate = response.candidates[0]

        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"🔒 Safety ratings: {candidate.safety_ratings}\n")

        if candidate.finish_reason == 1:
            print(f"✅ 성공! ({len(response.text)} chars)")
            print("\n" + "="*60)
            print(response.text[:800])
            print("="*60)
        else:
            print(f"❌ Finish reason: {candidate.finish_reason}")

            # 더 자세한 정보 출력
            print(f"\nCandidate details:")
            print(f"  - finish_reason: {candidate.finish_reason}")
            print(f"  - safety_ratings: {candidate.safety_ratings}")
            if hasattr(candidate, 'finish_message'):
                print(f"  - finish_message: {candidate.finish_message}")

    else:
        print("❌ No candidates")
        print(f"Response prompt_feedback: {response.prompt_feedback}")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
