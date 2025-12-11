#!/usr/bin/env python3
"""
Gemini API Multi-Model Test
"""
import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

from dotenv import load_dotenv
load_dotenv(override=True)

print("=" * 50)
print("Gemini API Multi-Model Test")
print("=" * 50)

api_key = os.getenv('GEMINI_API_KEY', '')
print(f"\nAPI Key: {api_key[:15]}...")

import google.generativeai as genai
genai.configure(api_key=api_key)

# Test multiple models
models_to_test = [
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash",
    "gemini-pro",
]

print("\nTesting models...")
for model_name in models_to_test:
    print(f"\n  [{model_name}]", end=" ")
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hi")
        print(f"✅ OK - {response.text.strip()[:30]}")
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)[:60].replace('\n', ' ')
        print(f"❌ {err_type}: {err_msg}...")

print("\n" + "=" * 50)
