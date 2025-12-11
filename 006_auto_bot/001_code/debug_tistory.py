#!/usr/bin/env python3
"""Debug Tistory login flow"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

print("=" * 60)
print("Tistory Login Debug")
print("=" * 60)

options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_argument("--window-size=1920,1080")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    # Step 1: Go to login
    print("\n[Step 1] Opening Tistory login page...")
    driver.get("https://www.tistory.com/auth/login")
    
    input("\n>>> 카카오로 로그인 후 Enter를 누르세요...")
    
    print(f"\nCurrent URL: {driver.current_url}")
    print(f"Cookies on www.tistory.com: {len(driver.get_cookies())}")
    
    # Step 2: Try to navigate to blog manage page
    print("\n[Step 2] Navigating to gong-mil-le.tistory.com/manage...")
    driver.get("https://gong-mil-le.tistory.com/manage")
    time.sleep(3)
    
    print(f"Final URL: {driver.current_url}")
    print(f"Page title: {driver.title}")
    
    # Check page content
    source = driver.page_source
    if '권한이 없거나' in source:
        print("\n❌ ERROR: '권한이 없거나' found in page")
        print("\n[Step 3] 브라우저에서 직접 확인해보세요.")
        print("    주소창에 https://gong-mil-le.tistory.com/manage 를 입력해보세요.")
        input("\n>>> 확인 후 Enter를 누르세요...")
        
        print(f"\nCurrent URL now: {driver.current_url}")
        print(f"Cookies count: {len(driver.get_cookies())}")
        
        # Print all cookies
        print("\nAll cookies:")
        for c in driver.get_cookies():
            print(f"  {c['name']}: {c['domain']}")
    else:
        print("\n✅ SUCCESS: Manage page loaded!")
        print(f"Cookies: {len(driver.get_cookies())}")
        
    input("\n>>> 브라우저를 닫으려면 Enter...")
    
finally:
    driver.quit()
