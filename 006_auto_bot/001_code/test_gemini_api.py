#!/usr/bin/env python3
"""
Gemini API 연결 테스트 스크립트
"""

import os
import google.generativeai as genai

# API 키 확인
api_key = os.getenv('GEMINI_API_KEY', '')

if not api_key:
    print("❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    print("zshrc에서 읽어오기 시도...")

    # zshrc에서 직접 읽기
    import subprocess
    result = subprocess.run(['zsh', '-c', 'echo $GEMINI_API_KEY'], capture_output=True, text=True)
    api_key = result.stdout.strip()

    if api_key:
        print(f"✅ zshrc에서 API 키 읽기 성공: {api_key[:20]}...")
    else:
        print("❌ zshrc에서도 API 키를 찾을 수 없습니다.")
        exit(1)

print(f"\n📝 API 키: {api_key[:20]}...{api_key[-4:]}")
print(f"📏 API 키 길이: {len(api_key)} characters")

# API 연결 테스트
try:
    print("\n🔄 Gemini API 연결 테스트 중...")
    genai.configure(api_key=api_key)

    # 간단한 테스트 요청
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Safety settings: BLOCK_NONE
    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        }
    ]

    response = model.generate_content(
        "안녕하세요. 간단한 테스트입니다. '테스트 성공'이라고 답해주세요.",
        generation_config=genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=100,
        ),
        safety_settings=safety_settings
    )

    if response.candidates:
        candidate = response.candidates[0]
        print(f"\n✅ API 연결 성공!")
        print(f"📊 Finish reason: {candidate.finish_reason}")
        print(f"🔒 Safety ratings: {candidate.safety_ratings}")
        print(f"\n💬 응답:\n{response.text}")

        # 뉴스 요약 테스트
        print("\n" + "="*60)
        print("📰 뉴스 요약 테스트")
        print("="*60)

        test_news = """
# 테스트 뉴스

## 정치
- 국회에서 새로운 법안이 통과되었습니다.
- 정치권에서 논의가 활발합니다.

## 경제
- 주식 시장이 상승세를 보이고 있습니다.
- 금리 인상이 예상됩니다.
"""

        summary_response = model.generate_content(
            f"""다음 뉴스를 한국어로 간단히 요약해주세요:

{test_news}

요약:""",
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=500,
            ),
            safety_settings=safety_settings
        )

        if summary_response.candidates:
            summary_candidate = summary_response.candidates[0]
            print(f"📊 Finish reason: {summary_candidate.finish_reason}")
            print(f"🔒 Safety ratings: {summary_candidate.safety_ratings}")
            print(f"\n💬 뉴스 요약 결과:\n{summary_response.text}")
        else:
            print("❌ 요약 응답 없음")

    else:
        print("❌ API 응답 없음")
        print(f"Response: {response}")

except Exception as e:
    print(f"\n❌ API 테스트 실패: {str(e)}")
    import traceback
    traceback.print_exc()
