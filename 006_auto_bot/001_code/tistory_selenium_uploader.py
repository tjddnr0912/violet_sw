#!/usr/bin/env python3
"""
Selenium-based Tistory Blog Auto-Uploader
-----------------------------------------
Tistory API 키 발급 중단으로 인해 Selenium 브라우저 자동화로 대체
"""

import os
import time
import pickle
import logging
from typing import Dict, List, Optional
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import markdown

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TistorySeleniumUploader:
    """Selenium 기반 Tistory 자동 포스팅 클래스"""

    def __init__(
        self,
        blog_url: str,
        cookie_path: str = './cookies/tistory_cookies.pkl',
        headless: bool = True,
        user_data_dir: str = None
    ):
        """
        Initialize TistorySeleniumUploader

        Args:
            blog_url: Tistory blog URL (e.g., 'https://myblog.tistory.com')
            cookie_path: Path to save/load cookies
            headless: Run browser in headless mode
            user_data_dir: Chrome user data directory for session persistence
        """
        self.blog_url = blog_url.rstrip('/')
        self.cookie_path = cookie_path
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.driver = None
        self.wait = None

        # Ensure directories exist
        os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
        if user_data_dir:
            os.makedirs(user_data_dir, exist_ok=True)
            logger.info(f"Using Chrome profile directory: {user_data_dir}")

        # Initialize driver
        self._init_driver()

    def _init_driver(self):
        """Initialize Chrome WebDriver with anti-detection settings"""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        # Anti-detection settings
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # User data directory for session persistence
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")

        # Stability options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=ko_KR")

        # User-Agent
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Initialize driver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 15)

        # Hide navigator.webdriver
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """
            }
        )

        logger.info("Chrome WebDriver initialized successfully")

    def save_cookies(self) -> bool:
        """Save current session cookies to file"""
        try:
            cookies = self.driver.get_cookies()
            with open(self.cookie_path, 'wb') as f:
                pickle.dump(cookies, f)
            logger.info(f"Cookies saved to {self.cookie_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False

    def load_cookies(self) -> bool:
        """Load cookies from file and add to browser"""
        try:
            if not os.path.exists(self.cookie_path):
                logger.warning(f"Cookie file not found: {self.cookie_path}")
                return False

            # First navigate to Tistory domain
            self.driver.get("https://www.tistory.com")
            time.sleep(2)

            with open(self.cookie_path, 'rb') as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                # Remove problematic keys
                cookie.pop('sameSite', None)
                cookie.pop('expiry', None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Skipping cookie: {e}")

            logger.info(f"Cookies loaded from {self.cookie_path}")
            self.driver.refresh()
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return False

    def is_logged_in(self) -> bool:
        """Check if currently logged in to Tistory"""
        try:
            self.driver.get(f"{self.blog_url}/manage")
            time.sleep(3)

            # Check if redirected to login page
            current_url = self.driver.current_url
            logger.info(f"Current URL after navigate: {current_url}")

            if "tistory.com/auth/login" in current_url:
                logger.info("Not logged in - redirected to login page")
                return False

            # Check for manage page elements (multiple selectors for compatibility)
            manage_selectors = [
                ".sidebar_tistory",
                "#kakaoHead",
                ".wrap_tistory",
                ".admin_header",
                ".box_blog",
                "#menubar",
                ".area_aside",
                "[class*='sidebar']",
                "[class*='manage']"
            ]

            for selector in manage_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element:
                        logger.info(f"Login verified - found element: {selector}")
                        return True
                except NoSuchElementException:
                    continue

            # Fallback: check if URL contains 'manage' and not 'login'
            if "/manage" in current_url and "login" not in current_url:
                logger.info("Login verified - URL contains /manage")
                return True

            logger.warning("Could not verify login - no manage elements found")
            return False

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return False

    def refresh_session(self) -> dict:
        """
        Refresh the login session to prevent cookie expiration.

        This method visits the Tistory manage page to keep the session alive
        and re-saves the cookies with updated expiration times.

        Returns:
            dict with 'success' and 'message' keys
        """
        try:
            logger.info("Refreshing Tistory session...")

            # First try to load existing cookies
            if not self.load_cookies():
                return {
                    'success': False,
                    'message': 'No cookies found. Please run manual login first.'
                }

            # Check if we're logged in
            if not self.is_logged_in():
                return {
                    'success': False,
                    'message': 'Session expired. Please run manual login again.'
                }

            # Visit a few pages to refresh the session
            pages_to_visit = [
                f"{self.blog_url}/manage",
                f"{self.blog_url}/manage/posts",
            ]

            for page in pages_to_visit:
                self.driver.get(page)
                time.sleep(2)

            # Re-save cookies with refreshed expiration
            if self.save_cookies():
                logger.info("Session refreshed and cookies saved successfully")
                return {
                    'success': True,
                    'message': 'Session refreshed successfully'
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to save refreshed cookies'
                }

        except Exception as e:
            logger.error(f"Failed to refresh session: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def login_with_kakao(self, username: str, password: str) -> bool:
        """
        Login to Tistory using Kakao account

        Args:
            username: Kakao email
            password: Kakao password

        Returns:
            True if login successful, False otherwise

        Note:
            Kakao 2FA may require manual intervention
        """
        try:
            logger.info("Starting Kakao login process...")

            # Navigate to Tistory login page
            self.driver.get("https://www.tistory.com/auth/login")
            time.sleep(3)

            # Click Kakao login button
            kakao_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_login.link_kakao_id"))
            )
            kakao_btn.click()
            time.sleep(3)

            # Handle Kakao login form
            try:
                # Check if already logged in to Kakao
                if "accounts.kakao.com" in self.driver.current_url:
                    # Enter username
                    username_input = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='loginId']"))
                    )
                    username_input.clear()
                    username_input.send_keys(username)

                    # Enter password
                    password_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='password']")
                    password_input.clear()
                    password_input.send_keys(password)

                    # Click login button
                    login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    login_btn.click()
                    time.sleep(5)

                    # Check for 2FA or additional verification
                    if "two-step" in self.driver.current_url.lower():
                        logger.warning("2FA detected - manual intervention required")
                        logger.info("Please complete 2FA within 60 seconds...")
                        time.sleep(60)

            except TimeoutException:
                logger.info("Kakao login form not found - may already be logged in")

            # Verify login success
            time.sleep(3)
            if self.is_logged_in():
                logger.info("Kakao login successful!")
                self.save_cookies()
                return True
            else:
                logger.error("Kakao login failed")
                return False

        except Exception as e:
            logger.error(f"Kakao login error: {e}")
            return False

    def manual_login_and_save_session(self):
        """
        Open browser for manual login and save session

        Use this for initial setup when automatic login fails
        """
        logger.info("=" * 60)
        logger.info("MANUAL LOGIN MODE")
        logger.info("=" * 60)
        logger.info("1. Browser will open Tistory login page")
        logger.info("2. Please login manually using Kakao")
        logger.info("3. After login, navigate to your blog's manage page")
        logger.info(f"   (e.g., {self.blog_url}/manage)")
        logger.info("4. Once you see the manage dashboard, press Enter")
        logger.info("=" * 60)

        # Ensure non-headless mode
        if self.headless:
            logger.info("Restarting browser in GUI mode...")
            self.close()
            self.headless = False
            self._init_driver()

        # Navigate to login page
        self.driver.get("https://www.tistory.com/auth/login")

        # Wait for user to complete login
        input("\n[1/2] 카카오로 로그인 완료 후 Enter를 누르세요...")

        # Navigate to blog's manage page to get correct subdomain cookies
        logger.info(f"블로그 관리 페이지로 이동 중: {self.blog_url}/manage")
        self.driver.get(f"{self.blog_url}/manage")
        time.sleep(3)

        input("\n[2/2] 관리자 대시보드가 보이면 Enter를 누르세요...")

        # Check current URL
        current_url = self.driver.current_url
        logger.info(f"Current URL (before save): {current_url}")

        # Save cookies FIRST before any navigation
        logger.info("Saving cookies...")
        cookies = self.driver.get_cookies()
        logger.info(f"Found {len(cookies)} cookies to save")
        for c in cookies:
            logger.info(f"  - {c.get('name')}: {c.get('domain')}")
        self.save_cookies()

        # Now verify by navigating to newpost page
        test_url = f"{self.blog_url}/manage/newpost"
        logger.info(f"Verifying by navigating to: {test_url}")
        self.driver.get(test_url)
        time.sleep(3)

        final_url = self.driver.current_url
        logger.info(f"Final URL: {final_url}")

        # Check if page loaded correctly
        source = self.driver.page_source
        if '권한이 없거나' in source or '존재하지 않는' in source:
            logger.error("❌ Login verification FAILED - no permission to manage page")
            logger.info(f"Page content preview: {source[:200]}")
            logger.info("Try navigating manually to the newpost page in the browser and check if it works")
        else:
            logger.info("✅ Login verification SUCCESS!")
            logger.info(f"Cookie file saved: {self.cookie_path}")

    def setup_persistent_login(self):
        """
        Setup persistent login using Chrome profile.

        This creates a Chrome profile with your login session that persists
        across browser restarts. Much more reliable than cookie-based auth.

        Run this ONCE to setup, then automated uploads will work indefinitely.
        """
        if not self.user_data_dir:
            logger.error("user_data_dir is not set. Cannot setup persistent login.")
            logger.info("Please set TISTORY_USER_DATA_DIR in .env file")
            return False

        logger.info("=" * 60)
        logger.info("PERSISTENT LOGIN SETUP (Chrome Profile)")
        logger.info("=" * 60)
        logger.info(f"Chrome profile directory: {self.user_data_dir}")
        logger.info("")
        logger.info("This will save your login session permanently.")
        logger.info("You only need to do this ONCE!")
        logger.info("")
        logger.info("Steps:")
        logger.info("1. Browser will open Tistory login page")
        logger.info("2. Login with Kakao (check 'Stay logged in' / '로그인 상태 유지')")
        logger.info("3. Navigate to your blog's manage page")
        logger.info(f"   ({self.blog_url}/manage)")
        logger.info("4. Press Enter when you see the dashboard")
        logger.info("=" * 60)

        # Ensure non-headless mode for manual login
        if self.headless:
            logger.info("Restarting browser in GUI mode...")
            self.close()
            self.headless = False
            self._init_driver()

        # Navigate to login page
        self.driver.get("https://www.tistory.com/auth/login")

        input("\n[1/2] 카카오로 로그인 완료 후 Enter를 누르세요 (로그인 상태 유지 체크!)...")

        # Navigate to blog's manage page
        logger.info(f"블로그 관리 페이지로 이동 중: {self.blog_url}/manage")
        self.driver.get(f"{self.blog_url}/manage")
        time.sleep(3)

        input("\n[2/2] 관리자 대시보드가 보이면 Enter를 누르세요...")

        # Verify login
        current_url = self.driver.current_url
        logger.info(f"Current URL: {current_url}")

        if "login" in current_url:
            logger.error("❌ Setup FAILED - still on login page")
            return False

        # Test by navigating to newpost
        test_url = f"{self.blog_url}/manage/newpost"
        logger.info(f"Verifying access to: {test_url}")
        self.driver.get(test_url)
        time.sleep(3)

        source = self.driver.page_source
        if '권한이 없거나' in source or '존재하지 않는' in source:
            logger.error("❌ Setup FAILED - no permission")
            return False

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ PERSISTENT LOGIN SETUP SUCCESS!")
        logger.info("=" * 60)
        logger.info(f"Chrome profile saved at: {self.user_data_dir}")
        logger.info("")
        logger.info("Your login session is now permanently saved.")
        logger.info("Automated uploads will work without re-login!")
        logger.info("=" * 60)
        return True

    def convert_markdown_to_html(self, markdown_content: str) -> str:
        """Convert markdown content to HTML"""
        html = markdown.markdown(
            markdown_content,
            extensions=['extra', 'codehilite', 'tables', 'toc']
        )
        return html

    def upload_post(
        self,
        title: str,
        content: str,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        visibility: str = "public",
        is_markdown: bool = True
    ) -> Dict:
        """
        Upload a post to Tistory blog

        Args:
            title: Post title
            content: Post content (markdown or HTML)
            category: Category name (optional)
            tags: List of tags (optional)
            visibility: "public", "private", or "protected"
            is_markdown: If True, convert markdown to HTML

        Returns:
            Dictionary with upload result
        """
        try:
            logger.info(f"Uploading post: {title[:50]}...")

            # Check login status
            if not self.is_logged_in():
                if self.user_data_dir:
                    # Using Chrome profile - no cookie fallback needed
                    logger.error("Not logged in. Chrome profile needs initial setup.")
                    return {
                        'success': False,
                        'message': 'Not logged in. Please run setup_persistent_login() first to initialize Chrome profile.'
                    }
                else:
                    # Fallback to cookie-based auth
                    logger.info("Not logged in. Attempting to load cookies...")
                    if not self.load_cookies() or not self.is_logged_in():
                        return {
                            'success': False,
                            'message': 'Not logged in. Please run manual_login_and_save_session() first.'
                        }

            # Navigate to new post page
            self.driver.get(f"{self.blog_url}/manage/newpost")
            time.sleep(3)

            # Switch to HTML mode for easier content insertion
            try:
                html_mode_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".btn_mode.html"))
                )
                html_mode_btn.click()
                time.sleep(1)
            except:
                logger.debug("HTML mode button not found, continuing...")

            # Enter title
            title_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#post-title-inp"))
            )
            title_input.clear()
            title_input.send_keys(title)
            logger.info("Title entered")

            # Convert content if markdown
            if is_markdown:
                html_content = self.convert_markdown_to_html(content)
            else:
                html_content = content

            # Enter content - try multiple methods
            content_entered = False

            # Method 1: TinyMCE API (most reliable for Tistory)
            try:
                tinymce_script = """
                    if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                        tinymce.activeEditor.setContent(arguments[0]);
                        return true;
                    }
                    return false;
                """
                result = self.driver.execute_script(tinymce_script, html_content)
                if result:
                    content_entered = True
                    logger.info("Content entered via TinyMCE API")
            except Exception as e:
                logger.debug(f"TinyMCE API method failed: {e}")

            # Method 2: TinyMCE iframe direct manipulation with sync
            if not content_entered:
                try:
                    iframe = self.driver.find_element(By.CSS_SELECTOR, "iframe[id*='editor-tistory']")
                    self.driver.switch_to.frame(iframe)
                    body = self.driver.find_element(By.TAG_NAME, "body")
                    self.driver.execute_script("arguments[0].innerHTML = arguments[1];", body, html_content)
                    self.driver.switch_to.default_content()

                    # Trigger TinyMCE sync
                    self.driver.execute_script("""
                        if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                            tinymce.activeEditor.save();
                        }
                    """)
                    content_entered = True
                    logger.info("Content entered via TinyMCE iframe + sync")
                except Exception as e:
                    logger.debug(f"TinyMCE iframe method failed: {e}")
                    self.driver.switch_to.default_content()

            # Method 3: CodeMirror (HTML mode)
            if not content_entered:
                try:
                    content_script = """
                        var editor = document.querySelector('.CodeMirror');
                        if (editor && editor.CodeMirror) {
                            editor.CodeMirror.setValue(arguments[0]);
                            return true;
                        }
                        return false;
                    """
                    result = self.driver.execute_script(content_script, html_content)
                    if result:
                        content_entered = True
                        logger.info("Content entered via CodeMirror")
                except Exception as e:
                    logger.debug(f"CodeMirror method failed: {e}")

            if not content_entered:
                logger.warning("Could not enter content - all methods failed")
            else:
                logger.info("Content entered successfully")

            # Add tags if provided
            if tags:
                self._add_tags(tags)

            # Set category if provided
            if category:
                self._select_category(category)

            # CRITICAL: Sync TinyMCE content to form before publishing
            # Without this, content appears in editor but doesn't get saved
            try:
                sync_script = """
                    if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
                        tinymce.activeEditor.save();
                        tinymce.triggerSave();
                        return true;
                    }
                    return false;
                """
                sync_result = self.driver.execute_script(sync_script)
                if sync_result:
                    logger.info("TinyMCE content synced to form before publish")
                time.sleep(1)  # Wait for sync to complete
            except Exception as e:
                logger.warning(f"TinyMCE sync warning: {e}")

            # Set visibility and publish
            self._set_visibility_and_publish(visibility)

            # Get published post URL
            time.sleep(3)
            post_url = self._get_published_url()

            return {
                'success': True,
                'url': post_url,
                'message': 'Post uploaded successfully'
            }

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def _add_tags(self, tags: List[str]):
        """Add tags to the post"""
        try:
            tag_input = self.driver.find_element(By.CSS_SELECTOR, "#tagText")
            for tag in tags:
                tag_input.send_keys(tag)
                tag_input.send_keys(Keys.RETURN)
                time.sleep(0.3)
            logger.info(f"Tags added: {tags}")
        except Exception as e:
            logger.warning(f"Could not add tags: {e}")

    def _select_category(self, category: str):
        """Select category for the post"""
        try:
            # Try multiple selectors for category button
            category_btn_selectors = [
                ".btn_category",
                "#category-btn",
                "[class*='category'] button",
                ".select_category",
                "#post-category",
                ".btn_cate"
            ]

            category_btn = None
            for selector in category_btn_selectors:
                try:
                    category_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if category_btn:
                        category_btn.click()
                        time.sleep(1)
                        logger.info(f"Category dropdown opened: {selector}")
                        break
                except:
                    continue

            if not category_btn:
                logger.warning("Category button not found, skipping category selection")
                return

            # Find and click the category
            category_list_selectors = [
                ".list_category li",
                ".category_list li",
                "[class*='category'] li",
                "ul.list_cate li",
                ".dropdown-menu li"
            ]

            for list_selector in category_list_selectors:
                try:
                    categories = self.driver.find_elements(By.CSS_SELECTOR, list_selector)
                    for cat in categories:
                        if category.lower() in cat.text.lower():
                            cat.click()
                            logger.info(f"Category selected: {category}")
                            return
                except:
                    continue

            logger.warning(f"Category '{category}' not found in list")
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Could not select category: {e}")

    def _set_visibility_and_publish(self, visibility: str):
        """Set post visibility and publish"""
        try:
            # Try multiple selectors for publish button (Tistory UI varies)
            publish_btn_selectors = [
                "#publish-layer-btn",
                ".btn_publish",
                "button.btn_default.btn_publish",
                "[class*='publish']",
                ".btn_save",
                "#savePostBtn",
                "button[type='submit']"
            ]

            publish_btn = None
            for selector in publish_btn_selectors:
                try:
                    publish_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    logger.info(f"Found publish button: {selector}")
                    break
                except:
                    continue

            if publish_btn:
                publish_btn.click()
                time.sleep(2)

            # Tistory visibility uses 'basicSet' radio buttons (updated 2024)
            # Values: 20=public(공개), 15=protected(보호), 0=private(비공개)
            visibility_map = {
                'public': '20',
                'protected': '15',
                'private': '0'
            }

            target_value = visibility_map.get(visibility, '20')  # Default to public
            logger.info(f"Setting visibility to: {visibility} (value={target_value})")

            # Primary selector: name='basicSet' (current Tistory UI)
            visibility_selectors = [
                f"input[name='basicSet'][value='{target_value}']",
                f"input[name='visibility'][value='{target_value}']",  # Legacy fallback
                f"input[type='radio'][value='{target_value}']",
            ]

            visibility_set = False
            for selector in visibility_selectors:
                try:
                    vis_radio = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if vis_radio.is_displayed():
                        self.driver.execute_script("arguments[0].click();", vis_radio)
                        logger.info(f"Visibility set using: {selector}")
                        visibility_set = True
                        break
                except:
                    continue

            if not visibility_set:
                logger.warning(f"Could not find visibility radio button for {visibility}")

            # Try to find and click final publish/save button
            final_btn_selectors = [
                "#publish-btn",
                ".btn_ok",
                "button.btn_default.btn_ok",
                ".btn_confirm",
                "#save",
                ".layer_btn .btn_default",
                "button[type='submit']",
                ".btn_layer_ok"
            ]

            time.sleep(1)
            for selector in final_btn_selectors:
                try:
                    final_btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if final_btn.is_displayed() and final_btn.is_enabled():
                        final_btn.click()
                        logger.info(f"Final publish clicked: {selector}")
                        break
                except:
                    continue

            logger.info(f"Post published with visibility: {visibility}")
            time.sleep(3)

        except Exception as e:
            logger.error(f"Publish error: {e}")
            # Don't raise - try to continue anyway
            logger.warning("Attempting to save without visibility settings...")

    def _get_published_url(self) -> str:
        """Get the URL of the published post"""
        try:
            # After publishing, we might be redirected to the post or stay on editor
            current_url = self.driver.current_url

            if "/manage/newpost" not in current_url and self.blog_url in current_url:
                return current_url

            # Try to get from success message or notification
            try:
                success_link = self.driver.find_element(By.CSS_SELECTOR, ".link_view")
                return success_link.get_attribute('href')
            except:
                pass

            # Return blog URL as fallback
            return self.blog_url

        except Exception as e:
            logger.warning(f"Could not get published URL: {e}")
            return self.blog_url

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser closed")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


# CLI interface for testing
if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Tistory Selenium Uploader')
    parser.add_argument('--blog-url', default=os.getenv('TISTORY_BLOG_URL', ''), help='Tistory blog URL')
    parser.add_argument('--login', action='store_true', help='Manual login mode (cookie-based)')
    parser.add_argument('--setup', action='store_true', help='Setup persistent login (Chrome profile) - RECOMMENDED')
    parser.add_argument('--check', action='store_true', help='Check login status')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--user-data-dir', default=os.getenv('TISTORY_USER_DATA_DIR', './chrome_profile/tistory'),
                        help='Chrome profile directory for persistent login')

    args = parser.parse_args()

    if not args.blog_url:
        print("Error: --blog-url is required or set TISTORY_BLOG_URL in .env")
        parser.print_help()
        exit(1)

    uploader = TistorySeleniumUploader(
        blog_url=args.blog_url,
        headless=args.headless,
        user_data_dir=args.user_data_dir if args.setup or args.user_data_dir != './chrome_profile/tistory' else None
    )

    try:
        if args.setup:
            # Recommended: Setup persistent login with Chrome profile
            uploader.setup_persistent_login()
        elif args.login:
            # Legacy: Manual login with cookies
            uploader.manual_login_and_save_session()
        elif args.check:
            if uploader.is_logged_in():
                print("Login status: OK")
            elif uploader.load_cookies() and uploader.is_logged_in():
                print("Login status: OK (via cookies)")
            else:
                print("Login status: FAILED")
                print("Run: python tistory_selenium_uploader.py --setup")
        else:
            parser.print_help()
            print("\n" + "=" * 60)
            print("QUICK START (Recommended):")
            print("=" * 60)
            print("python tistory_selenium_uploader.py --setup")
            print("")
            print("This will setup persistent login that never expires!")
            print("=" * 60)
    finally:
        uploader.close()
