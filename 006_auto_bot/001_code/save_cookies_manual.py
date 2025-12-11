#!/usr/bin/env python3
"""Manual cookie saver - do everything manually in browser"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pickle
import os
import time

print("=" * 60)
print("수동 쿠키 저장 도구")
print("=" * 60)
print("""
[사용 방법]
1. 브라우저가 열립니다
2. https://www.tistory.com 에서 카카오로 로그인하세요
3. 로그인 후 직접 주소창에 입력:
   https://gong-mil-le.tistory.com/manage
4. 관리자 대시보드가 보이면 이 터미널에서 Enter를 누르세요
5. 쿠키가 저장됩니다
""")
print("=" * 60)

options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_argument("--window-size=1920,1080")
options.add_argument("--lang=ko_KR")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    driver.get("https://www.tistory.com/auth/login")
    
    input("\n>>> 관리자 대시보드(gong-mil-le.tistory.com/manage)가 보이면 Enter...")
    
    print(f"\nCurrent URL: {driver.current_url}")
    
    # Get ALL cookies
    cookies = driver.get_cookies()
    print(f"Found {len(cookies)} cookies:")
    for c in cookies:
        print(f"  - {c['name']}: {c['domain']}")
    
    # Save cookies
    os.makedirs('./cookies', exist_ok=True)
    with open('./cookies/tistory_cookies.pkl', 'wb') as f:
        pickle.dump(cookies, f)
    
    print(f"\n✅ Cookies saved to ./cookies/tistory_cookies.pkl")
    
    # Quick verification
    print("\n[검증 중...]")
    driver.get("https://gong-mil-le.tistory.com/manage/newpost")
    time.sleep(3)
    
    if '권한이 없거나' in driver.page_source:
        print("❌ 검증 실패 - newpost 페이지 접근 불가")
        print("   브라우저에서 직접 해당 URL로 이동되는지 확인해보세요")
    else:
        print("✅ 검증 성공 - newpost 페이지 접근 가능!")
        
finally:
    input("\n>>> Enter를 누르면 브라우저가 닫힙니다...")
    driver.quit()
