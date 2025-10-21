#!/usr/bin/env python3
"""
Gemini 사용 가능한 모델 목록 확인
"""

import os
import google.generativeai as genai

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY environment variable is not set. Please set it in .env file or export it.")

print(f"📝 API 키: {api_key[:20]}...{api_key[-4:]}")
print("\n🔍 사용 가능한 Gemini 모델 목록:\n")

genai.configure(api_key=api_key)

for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"✅ {model.name}")
        print(f"   Display: {model.display_name}")
        print(f"   Description: {model.description[:100]}...")
        print()
