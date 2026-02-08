"""
Login otomatis Gemini（ undetected-chromedriver）
，
"""
import random
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from core.base_task_service import TaskCancelledError


# Konstanta
AUTH_HOME_URL = "https://auth.business.gemini.google/"
LOGIN_URL = "https://auth.business.gemini.google/login?continueUrl=https:%2F%2Fbusiness.gemini.google%2F&wiffid=CAoSJDIwNTlhYzBjLTVlMmMtNGUxZS1hY2JkLThmOGY2ZDE0ODM1Mg"
DEFAULT_XSRF_TOKEN = "KdLRzKwwBTD5wo8nUollAbY6cW0"


class GeminiAutomationUC:
    """Login otomatis Gemini（ undetected-chromedriver）"""

    def __init__(
        self,
        user_agent: str = "",
        proxy: str = "",
        headless: bool = True,
        timeout: int = 60,
        log_callback=None,
    ) -> None:
        self.user_agent = user_agent or self._get_ua()
        self.proxy = proxy
        self.headless = headless
        self.timeout = timeout
        self.log_callback = log_callback
        self.driver = None
        self.user_data_dir = None

    def stop(self) -> None:
        """Request stop eksternal: usahakan tutup instance browser."""
        try:
            self._cleanup()
        except Exception:
            pass

    def login_and_extract(self, email: str, mail_client) -> dict:
        """Eksekusi login dan ekstrak konfigurasi"""
        try:
            self._create_driver()
            return self._run_flow(email, mail_client)
        except TaskCancelledError:
            raise
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            self._cleanup()

    def _create_driver(self):
        """"""
        import tempfile
        options = uc.ChromeOptions()

        # 
        self.user_data_dir = tempfile.mkdtemp(prefix='uc-profile-')
        options.add_argument(f"--user-data-dir={self.user_data_dir}")

        # 
        options.add_argument("--incognito")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--window-size=1280,800")

        # Pengaturan bahasa Indonesia
        options.add_argument("--lang=id-ID")
        options.add_experimental_option("prefs", {
            "intl.accept_languages": "id-ID,id,en"
        })

        # 
        if self.proxy:
            options.add_argument(f"--proxy-server={self.proxy}")

        # 
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-dev-shm-usage")

        # User-Agent
        if self.user_agent:
            options.add_argument(f"--user-agent={self.user_agent}")

        # （undetected-chromedriver ）
        self.driver = uc.Chrome(
            options=options,
            version_main=None,  #  Chrome 
            use_subprocess=True,
        )

        # Timeout
        self.driver.set_page_load_timeout(self.timeout)
        self.driver.implicitly_wait(10)

    def _run_flow(self, email: str, mail_client) -> dict:
        """"""

        # ，
        from datetime import datetime
        send_time = datetime.now()

        self._log("info", f"navigating to login page for {email}")

        # 
        self.driver.get(LOGIN_URL)
        time.sleep(3)

        # 
        current_url = self.driver.current_url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            return self._extract_config(email)

        # Masukkan alamat email
        try:
            self._log("info", "entering email address")
            email_input = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[1]/div[1]/div/span[2]/input"))
            )
            email_input.click()
            email_input.clear()
            for char in email:
                email_input.send_keys(char)
                time.sleep(0.02)
            time.sleep(0.5)
        except Exception as e:
            self._log("error", f"failed to enter email: {e}")
            self._save_screenshot("email_input_failed")
            return {"success": False, "error": f"failed to enter email: {e}"}

        # 
        try:
            continue_btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/button"))
            )
            self.driver.execute_script("arguments[0].click();", continue_btn)
            time.sleep(2)
        except Exception as e:
            self._log("error", f"failed to click continue: {e}")
            self._save_screenshot("continue_button_failed")
            return {"success": False, "error": f"failed to click continue: {e}"}

        # ""
        self._log("info", "clicking send verification code button")
        if not self._click_send_code_button():
            self._log("error", "send code button not found")
            self._save_screenshot("send_code_button_missing")
            return {"success": False, "error": "send code button not found"}

        # 
        code_input = self._wait_for_code_input()
        if not code_input:
            self._log("error", "code input not found")
            self._save_screenshot("code_input_missing")
            return {"success": False, "error": "code input not found"}

        # （）
        self._log("info", "polling for verification code")
        # Set browser driver untuk generator.email
        if hasattr(mail_client, 'set_browser_driver'):
            mail_client.set_browser_driver(self.driver, driver_type="uc")
        code = mail_client.poll_for_code(timeout=40, interval=4, since_time=send_time)

        if not code:
            self._log("error", "verification code timeout")
            self._save_screenshot("code_timeout")
            return {"success": False, "error": "verification code timeout"}

        self._log("info", f"code received: {code}")

        # 
        time.sleep(1)
        try:
            code_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']"))
            )
            code_input.click()
            time.sleep(0.1)
            for char in code:
                code_input.send_keys(char)
                time.sleep(0.05)
        except Exception:
            try:
                span = self.driver.find_element(By.CSS_SELECTOR, "span[data-index='0']")
                span.click()
                time.sleep(0.2)
                self.driver.switch_to.active_element.send_keys(code)
            except Exception as e:
                self._log("error", f"failed to input code: {e}")
                self._save_screenshot("code_input_failed")
                return {"success": False, "error": f"failed to input code: {e}"}

        # Submit verification code
        time.sleep(0.5)
        self._log("info", "🔍 Looking for submit button...")
        button_clicked = False
        
        try:
            verify_btn = self.driver.find_element(By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button")
            self.driver.execute_script("arguments[0].click();", verify_btn)
            button_clicked = True
            self._log("info", "✅ Verify button clicked (XPATH)")
        except Exception:
            try:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "" in btn.text:
                        self.driver.execute_script("arguments[0].click();", btn)
                        button_clicked = True
                        self._log("info", "✅ Verify button clicked (text match)")
                        break
            except Exception as e:
                self._log("warning", f"⚠️ Failed to click verify button: {e}")

        if button_clicked:
            # Wait for page navigation after button click
            self._log("info", "⏳ Waiting for verification...")
            time.sleep(8)
        else:
            self._log("warning", "⚠️ No verify button clicked, waiting 5s...")
            time.sleep(5)

        # 
        self._handle_agreement_page()

        # 
        self._log("info", "navigating to business page")
        self.driver.get("https://business.gemini.google/")
        time.sleep(3)

        # 
        if "cid" not in self.driver.current_url:
            if self._handle_username_setup():
                time.sleep(3)

        #  URL （csesidx  cid）
        self._log("info", "waiting for URL parameters")
        if not self._wait_for_business_params():
            self._log("warning", "URL parameters not generated, trying refresh")
            self.driver.refresh()
            time.sleep(3)
            if not self._wait_for_business_params():
                self._log("error", "URL parameters generation failed")
                self._save_screenshot("params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # Ekstrak konfigurasi
        self._log("info", "login success")
        return self._extract_config(email)

    def _click_send_code_button(self) -> bool:
        """（）"""
        time.sleep(2)

        # 1: ID
        try:
            direct_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "sign-in-with-email"))
            )
            self.driver.execute_script("arguments[0].click();", direct_btn)
            time.sleep(2)
            return True
        except TimeoutException:
            pass

        # 2: 
        keywords = ["", "", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                text = btn.text.strip() if btn.text else ""
                if text and any(kw in text for kw in keywords):
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(2)
                    return True
        except Exception:
            pass

        # 3: 
        try:
            code_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='pinInput']")
            if code_input:
                return True
        except NoSuchElementException:
            pass

        return False

    def _wait_for_code_input(self, timeout: int = 30):
        """"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='pinInput']"))
            )
            return element
        except TimeoutException:
            return None

    def _find_code_input(self):
        """"""
        try:
            return self.driver.find_element(By.CSS_SELECTOR, "input[name='pinInput']")
        except NoSuchElementException:
            return None

    def _find_verify_button(self):
        """"""
        try:
            return self.driver.find_element(By.XPATH, "/html/body/c-wiz/div/div/div[1]/div/div/div/form/div[2]/div/div[1]/span/div[1]/button")
        except NoSuchElementException:
            pass

        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                text = btn.text.strip()
                if text and "" in text:
                    return btn
        except Exception:
            pass

        return None

    def _handle_agreement_page(self) -> None:
        """Handle Gemini Business agreement/setup page"""
        if "/admin/create" in self.driver.current_url:
            self._log("info", "📋 Agreement page detected, looking for form...")
            time.sleep(2)
            
            # Check if there's a name input field that needs to be filled
            name_input = None
            name_selectors = [
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.CSS_SELECTOR, "input[placeholder*='name']"),
                (By.CSS_SELECTOR, "input[placeholder*='Full name']")
            ]
            
            for by, selector in name_selectors:
                try:
                    name_input = self.driver.find_element(by, selector)
                    if name_input:
                        self._log("info", f"✅ Found name input: {selector}")
                        break
                except:
                    pass
            
            if name_input:
                # Fill in the name field
                import random, string
                suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
                full_name = f"Test User {suffix}"
                
                self._log("info", f"⌨️ Filling name: {full_name}")
                name_input.click()
                time.sleep(0.2)
                name_input.clear()
                for char in full_name:
                    name_input.send_keys(char)
                    time.sleep(0.05)
                time.sleep(0.5)
            
            # Now find and click the agreement button
            button_found = False
            
            try:
                agree_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.agree-button"))
                )
                self._log("info", "✅ Found button by class")
                agree_btn.click()
                button_found = True
            except TimeoutException:
                # Try finding button by text
                self._log("info", "🔍 Trying to find button by text...")
                try:
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        btn_text = (btn.text or "").strip().lower()
                        if "agree" in btn_text or "get started" in btn_text:
                            self._log("info", f"✅ Found button: {btn.text}")
                            self.driver.execute_script("arguments[0].click();", btn)
                            button_found = True
                            break
                except:
                    pass
            
            if button_found:
                self._log("info", "✅ Agreement button clicked, waiting...")
                time.sleep(3)
            else:
                self._log("warning", "⚠️ No agreement button found, continuing anyway...")
                time.sleep(1)

    def _wait_for_cid(self, timeout: int = 10) -> bool:
        """URLcid"""
        for _ in range(timeout):
            if "cid" in self.driver.current_url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, timeout: int = 30) -> bool:
        """（csesidx  cid）"""
        for _ in range(timeout):
            url = self.driver.current_url
            if "csesidx=" in url and "/cid/" in url:
                self._log("info", f"business params ready: {url}")
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self) -> bool:
        """"""
        current_url = self.driver.current_url

        if "auth.business.gemini.google/login" in current_url:
            return False

        selectors = [
            "input[formcontrolname='fullName']",
            "input[placeholder='']",
            "input[placeholder='Full name']",
            "input#mat-input-0",
            "input[type='text']",
            "input[name='displayName']",
        ]

        username_input = None
        for _ in range(30):
            for selector in selectors:
                try:
                    username_input = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if username_input.is_displayed():
                        break
                except Exception:
                    continue
            if username_input and username_input.is_displayed():
                break
            time.sleep(1)

        if not username_input or not username_input.is_displayed():
            return False

        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"Test{suffix}"

        try:
            username_input.click()
            time.sleep(0.2)
            username_input.clear()
            for char in username:
                username_input.send_keys(char)
                time.sleep(0.02)
            time.sleep(0.3)

            from selenium.webdriver.common.keys import Keys
            username_input.send_keys(Keys.ENTER)
            time.sleep(1)

            return True
        except Exception:
            return False

    def _extract_config(self, email: str) -> dict:
        """Ekstrak konfigurasi"""
        try:
            if "cid/" not in self.driver.current_url:
                self.driver.get("https://business.gemini.google/")
                time.sleep(3)

            url = self.driver.current_url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            # 
            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            #  Cookie
            cookies = self.driver.get_cookies()
            ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
            host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)

            # （，）
            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                # Cookie expiry  UTC ，12
                cookie_expire_beijing = datetime.fromtimestamp(ses_obj["expiry"], tz=beijing_tz)
                expires_at = (cookie_expire_beijing - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                expires_at = (datetime.now(beijing_tz) + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")

            config = {
                "id": email,
                "csesidx": csesidx,
                "config_id": config_id,
                "secure_c_ses": ses,
                "host_c_oses": host,
                "expires_at": expires_at,
            }
            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_screenshot(self, name: str) -> None:
        """"""
        try:
            from core.storage import _data_file_path
            screenshot_dir = _data_file_path("automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            self.driver.save_screenshot(path)
        except Exception:
            pass

    def _cleanup(self) -> None:
        """Bersihkan resource"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

        if self.user_data_dir:
            try:
                import shutil
                import os
                if os.path.exists(self.user_data_dir):
                    shutil.rmtree(self.user_data_dir, ignore_errors=True)
            except Exception:
                pass

    def _log(self, level: str, message: str) -> None:
        """"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except TaskCancelledError:
                raise
            except Exception:
                pass

    @staticmethod
    def _get_ua() -> str:
        """User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
