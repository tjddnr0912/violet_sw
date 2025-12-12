#!/usr/bin/env python3
"""
Tistory Persistent Login Setup
==============================
Run this script ONCE to setup permanent login.
After setup, automated uploads will work indefinitely without re-login.

Usage:
    python setup_tistory_login.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Change to script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from tistory_selenium_uploader import TistorySeleniumUploader

def main():
    blog_url = os.getenv('TISTORY_BLOG_URL')
    user_data_dir = os.getenv('TISTORY_USER_DATA_DIR', './chrome_profile/tistory')

    if not blog_url:
        print("Error: TISTORY_BLOG_URL not set in .env file")
        print("Please add: TISTORY_BLOG_URL=https://your-blog.tistory.com")
        sys.exit(1)

    print("=" * 60)
    print("Tistory Persistent Login Setup")
    print("=" * 60)
    print(f"Blog URL: {blog_url}")
    print(f"Chrome Profile: {user_data_dir}")
    print("=" * 60)
    print()

    uploader = TistorySeleniumUploader(
        blog_url=blog_url,
        user_data_dir=user_data_dir,
        headless=False  # Need GUI for manual login
    )

    try:
        success = uploader.setup_persistent_login()
        if success:
            print()
            print("Setup complete! You can now run automated uploads.")
        else:
            print()
            print("Setup failed. Please try again.")
            sys.exit(1)
    finally:
        uploader.close()

if __name__ == '__main__':
    main()
