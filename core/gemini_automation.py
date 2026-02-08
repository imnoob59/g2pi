"""
Modul login otomatis Gemini (untuk registrasi akun baru)
"""
import os
import json
import random
import string
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

from DrissionPage import ChromiumPage, ChromiumOptions
from core.base_task_service import TaskCancelledError


# Konstanta
AUTH_HOME_URL = "https://auth.business.gemini.google/"
DEFAULT_XSRF_TOKEN = "KdLRzKwwBTD5wo8nUollAbY6cW0"

# Path Chromium umum di Linux
CHROMIUM_PATHS = [
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
]


def _find_chromium_path() -> Optional[str]:
    """Cari path browser Chromium/Chrome yang tersedia"""
    for path in CHROMIUM_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class GeminiAutomation:
    """Login otomatis Gemini"""

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
        self._page = None
        self._user_data_dir = None
        self._last_send_error = ""

    def stop(self) -> None:
        """Request stop eksternal: usahakan tutup instance browser."""
        page = self._page
        if page:
            try:
                page.quit()
            except Exception:
                pass

    def login_and_extract(self, email: str, mail_client) -> dict:
        """Eksekusi login dan ekstrak konfigurasi"""
        page = None
        user_data_dir = None
        try:
            page = self._create_page()
            user_data_dir = getattr(page, 'user_data_dir', None)
            self._page = page
            self._user_data_dir = user_data_dir
            return self._run_flow(page, email, mail_client)
        except TaskCancelledError:
            raise
        except Exception as exc:
            self._log("error", f"automation error: {exc}")
            return {"success": False, "error": str(exc)}
        finally:
            if page:
                try:
                    page.quit()
                except Exception:
                    pass
            self._page = None
            self._cleanup_user_data(user_data_dir)
            self._user_data_dir = None

    def _create_page(self) -> ChromiumPage:
        """Buat halaman browser"""
        options = ChromiumOptions()

        # Deteksi otomatis path browser Chromium (Linux/Docker environment)
        chromium_path = _find_chromium_path()
        if chromium_path:
            options.set_browser_path(chromium_path)

        options.set_argument("--incognito")
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-setuid-sandbox")
        options.set_argument("--disable-blink-features=AutomationControlled")
        options.set_argument("--window-size=1280,800")
        options.set_user_agent(self.user_agent)

        # Pengaturan bahasa Indonesia
        options.set_argument("--lang=id-ID")
        options.set_pref("intl.accept_languages", "id-ID,id,en")

        if self.proxy:
            options.set_argument(f"--proxy-server={self.proxy}")

        if self.headless:
            # Gunakan headless mode versi baru, lebih mirip browser asli
            options.set_argument("--headless=new")
            options.set_argument("--disable-gpu")
            options.set_argument("--no-first-run")
            options.set_argument("--disable-extensions")
            # 
            options.set_argument("--disable-infobars")
            options.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        options.auto_port()
        page = ChromiumPage(options)
        page.set.timeouts(self.timeout)

        # ：
        if self.headless:
            try:
                page.run_cdp("Page.addScriptToEvaluateOnNewDocument", source="""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                    window.chrome = {runtime: {}};

                    // 
                    Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 1});
                    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                    Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});

                    //  headless 
                    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

                    //  permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({state: Notification.permission}) :
                            originalQuery(parameters)
                    );
                """)
            except Exception:
                pass

        return page

    def _run_flow(self, page, email: str, mail_client) -> dict:
        """"""

        # ，
        from datetime import datetime
        send_time = datetime.now()

        # Step 1:  Cookie
        self._log("info", f"🌐 : {email}")

        page.get(AUTH_HOME_URL, timeout=self.timeout)
        time.sleep(2)

        #  Cookie
        try:
            self._log("info", "🍪  Cookies...")
            page.set.cookies({
                "name": "__Host-AP_SignInXsrf",
                "value": DEFAULT_XSRF_TOKEN,
                "url": AUTH_HOME_URL,
                "path": "/",
                "secure": True,
            })
            #  reCAPTCHA Cookie
            page.set.cookies({
                "name": "_GRECAPTCHA",
                "value": "09ABCL...",
                "url": "https://google.com",
                "path": "/",
                "secure": True,
            })
        except Exception as e:
            self._log("warning", f"⚠️ Cookie : {e}")

        login_hint = quote(email, safe="")
        login_url = f"https://auth.business.gemini.google/login/email?continueUrl=https%3A%2F%2Fbusiness.gemini.google%2F&loginHint={login_hint}&xsrfToken={DEFAULT_XSRF_TOKEN}"

        # ，
        try:
            page.listen.start(
                targets=["batchexecute", "browserinfo", "verify-oob-code"],
                is_regex=False,
                method=("GET", "POST"),
                res_type=("XHR", "FETCH", "DOCUMENT"),
            )
        except Exception:
            pass

        page.get(login_url, timeout=self.timeout)
        time.sleep(5)

        # Step 2: 
        current_url = page.url
        self._log("info", f"📍  URL: {current_url}")
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            self._log("info", "✅ ，Ekstrak konfigurasi")
            return self._extract_config(page, email)

        # Step 3: （5，10）
        self._log("info", "📧 ...")
        max_send_rounds = 5
        send_round = 0
        while True:
            send_round += 1
            if self._click_send_code_button(page):
                break
            if send_round >= max_send_rounds:
                self._log("error", "❌ （），IP")
                self._save_screenshot(page, "send_code_button_failed")
                return {"success": False, "error": "send code failed after retries"}
            self._log("warning", f"⚠️ ，10 ({send_round}/{max_send_rounds})")
            time.sleep(10)

        # Step 4: 
        code_input = self._wait_for_code_input(page)
        if not code_input:
            self._log("error", "❌ ")
            self._save_screenshot(page, "code_input_missing")
            return {"success": False, "error": "code input not found"}

        # Step 5: （3，5）
        self._log("info", "📬 ...")
        # Set browser driver untuk generator.email
        if hasattr(mail_client, 'set_browser_driver'):
            mail_client.set_browser_driver(page, driver_type="dp")
        code = mail_client.poll_for_code(timeout=15, interval=5, since_time=send_time)

        if not code:
            self._log("warning", "⚠️ Timeout，15...")
            time.sleep(15)
            # （Klik tombol）
            send_time = datetime.now()
            # 
            if self._click_resend_code_button(page):
                # （3，5）
                # Set browser driver lagi (untuk generator.email)
                if hasattr(mail_client, 'set_browser_driver'):
                    mail_client.set_browser_driver(page, driver_type="dp")
                code = mail_client.poll_for_code(timeout=15, interval=5, since_time=send_time)
                if not code:
                    self._log("error", "❌ ")
                    self._save_screenshot(page, "code_timeout_after_resend")
                    return {"success": False, "error": "verification code timeout after resend"}
            else:
                self._log("error", "❌ Timeout")
                self._save_screenshot(page, "code_timeout")
                return {"success": False, "error": "verification code timeout"}

        self._log("info", f"✅ : {code}")

        # Step 6: 
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=3) or \
                     page.ele("css:input[type='tel']", timeout=2)

        if not code_input:
            self._log("error", "❌ ")
            return {"success": False, "error": "code input expired"}

        # ，
        self._log("info", "⌨️ ...")
        if not self._simulate_human_input(code_input, code):
            self._log("warning", "⚠️ ，")
            code_input.input(code, clear=True)
            time.sleep(0.5)

        # Find and click submit button instead of just pressing Enter (better for headless)
        self._log("info", "🔍 Submit button...")
        submit_button = None
        
        # Try multiple button selectors
        button_selectors = [
            "css:button[jsname='LgbsSe']",  # Google's next button
            "css:button[type='submit']",
            "css:div[role='button'][jsname='LgbsSe']"
        ]
        
        for selector in button_selectors:
            submit_button = page.ele(selector, timeout=2)
            if submit_button:
                self._log("info", f"✅ Submit button found: {selector}")
                break
        
        if submit_button:
            self._log("info", "🖱️ Click submit button...")
            submit_button.click()
            time.sleep(1)
        else:
            # Fallback: press Enter
            self._log("warning", "⚠️ Submit button not found, fallback to Enter key")
            code_input.input("\n")
            time.sleep(0.5)

        # Step 7: Wait for page navigation (with URL change detection)
        self._log("info", "⏳ Waiting for verification...")
        old_url = page.url
        
        # Wait up to 20 seconds for URL change
        for i in range(40):  # 40 * 0.5s = 20s max
            time.sleep(0.5)
            current_url = page.url
            if current_url != old_url and "verify-oob-code" not in current_url:
                self._log("info", f"✅ Page navigated from {old_url} to {current_url}")
                break
            if i > 0 and i % 4 == 0:
                self._log("info", f"⏳ Still waiting... ({i//2}s)")
        
        # Additional wait for page stability
        time.sleep(3)

        #  URL 
        current_url = page.url
        self._log("info", f"📍  URL: {current_url}")

        # （）
        if "verify-oob-code" in current_url:
            self._log("error", "❌ ")
            self._save_screenshot(page, "verification_submit_failed")
            return {"success": False, "error": "verification code submission failed"}

        # Step 8: （）
        self._handle_agreement_page(page)

        # Step 9: 
        current_url = page.url
        has_business_params = "business.gemini.google" in current_url and "csesidx=" in current_url and "/cid/" in current_url

        if has_business_params:
            return self._extract_config(page, email)

        # Step 10: ，
        if "business.gemini.google" not in current_url:
            page.get("https://business.gemini.google/", timeout=self.timeout)
            time.sleep(5)

        # Step 11: 
        if "cid" not in page.url:
            if self._handle_username_setup(page):
                time.sleep(5)

        # Step 12:  URL （csesidx  cid）
        if not self._wait_for_business_params(page):
            page.refresh()
            time.sleep(5)
            if not self._wait_for_business_params(page):
                self._log("error", "❌ URL ")
                self._save_screenshot(page, "params_missing")
                return {"success": False, "error": "URL parameters not found"}

        # Step 13: Ekstrak konfigurasi
        self._log("info", "🎊 Login berhasil，Ekstrak konfigurasi...")
        return self._extract_config(page, email)

    def _click_send_code_button(self, page) -> bool:
        """（）"""
        time.sleep(2)
        max_send_attempts = 5
        resend_delay_seconds = 10

        # 1: ID
        direct_btn = page.ele("#sign-in-with-email", timeout=5)
        if direct_btn:
            for attempt in range(1, max_send_attempts + 1):
                try:
                    self._last_send_error = ""
                    direct_btn.click()
                    if self._verify_code_send_by_network(page) or self._verify_code_send_status(page):
                        self._stop_listen(page)
                        return True
                    if self._last_send_error == "captcha_check_failed":
                        self._log("error", f"❌ ，IP ({attempt}/{max_send_attempts})")
                    else:
                        self._log("warning", f"⚠️ ，{resend_delay_seconds} ({attempt}/{max_send_attempts})")
                    time.sleep(resend_delay_seconds)
                except Exception as e:
                    self._log("warning", f"⚠️ : {e}")
            self._stop_listen(page)
            return False

        # 2: 
        keywords = ["", "", "email", "Email", "Send code", "Send verification", "Verification code"]
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip()
                if text and any(kw in text for kw in keywords):
                    for attempt in range(1, max_send_attempts + 1):
                        try:
                            self._last_send_error = ""
                            btn.click()
                            if self._verify_code_send_by_network(page) or self._verify_code_send_status(page):
                                self._stop_listen(page)
                                return True
                            if self._last_send_error == "captcha_check_failed":
                                self._log("error", f"❌ ，IP ({attempt}/{max_send_attempts})")
                            else:
                                self._log("warning", f"⚠️ ，{resend_delay_seconds} ({attempt}/{max_send_attempts})")
                            time.sleep(resend_delay_seconds)
                        except Exception as e:
                            self._log("warning", f"⚠️ : {e}")
                    self._stop_listen(page)
                    return False
        except Exception as e:
            self._log("warning", f"⚠️ : {e}")

        # 
        code_input = page.ele("css:input[jsname='ovqh0b']", timeout=2) or page.ele("css:input[name='pinInput']", timeout=1)
        if code_input:
            self._stop_listen(page)
            self._log("info", "✅ ")

            # （）
            if self._click_resend_code_button(page):
                self._log("info", "✅ ")
                return True
            else:
                self._log("warning", "⚠️ ，")
                return True

        self._stop_listen(page)
        self._log("error", "❌ ")
        return False

    def _stop_listen(self, page) -> None:
        """"""
        try:
            if hasattr(page, 'listen') and page.listen:
                page.listen.stop()
        except Exception:
            pass

    def _verify_code_send_by_network(self, page) -> bool:
        """"""
        try:
            time.sleep(1)

            packets = []
            max_wait_seconds = 6
            deadline = time.time() + max_wait_seconds
            try:
                while time.time() < deadline:
                    got_any = False
                    for packet in page.listen.steps(timeout=1, gap=1):
                        packets.append(packet)
                        got_any = True
                    if got_any:
                        time.sleep(0.2)
                    else:
                        break
            except Exception:
                return False

            if not packets:
                return False

            # （）
            self._save_network_packets(packets)

            found_batchexecute = False
            found_batchexecute_error = False

            for packet in packets:
                try:
                    url = str(packet.url) if hasattr(packet, 'url') else str(packet)

                    if 'batchexecute' in url:
                        found_batchexecute = True

                        try:
                            response = packet.response if hasattr(packet, 'response') else None
                            if response and hasattr(response, 'raw_body'):
                                body = response.raw_body
                                raw_body_str = str(body)
                                if "CAPTCHA_CHECK_FAILED" in raw_body_str:
                                    found_batchexecute_error = True
                                    self._last_send_error = "captcha_check_failed"
                                elif "SendEmailOtpError" in raw_body_str:
                                    found_batchexecute_error = True
                                    self._last_send_error = "send_email_otp_error"
                        except Exception:
                            pass

                except Exception:
                    continue

            if found_batchexecute:
                if found_batchexecute_error:
                    return False
                return True
            else:
                return False

        except Exception:
            return False

    def _verify_code_send_status(self, page) -> bool:
        """"""
        time.sleep(2)
        try:
            success_keywords = ["", "code sent", "email sent", "check your email", ""]
            error_keywords = [
                "",
                "something went wrong",
                "error",
                "failed",
                "try again",
                "",
                ""
            ]
            selectors = [
                "css:.zyTWof-gIZMF",
                "css:[role='alert']",
                "css:aside",
            ]
            for selector in selectors:
                try:
                    elements = page.eles(selector, timeout=1)
                    for elem in elements[:20]:
                        text = (elem.text or "").strip()
                        if not text:
                            continue
                        if any(kw in text for kw in error_keywords):
                            return False
                        if any(kw in text for kw in success_keywords):
                            return True
                except Exception:
                    continue
            return True
        except Exception:
            return True

    def _truncate_text(self, text: str, max_len: int = 2000) -> str:
        if text is None:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"...(truncated, total={len(text)})"

    def _save_network_packets(self, packets) -> None:
        """（）"""
        try:
            from core.storage import _data_file_path
            base_dir = _data_file_path(os.path.join("logs", "network"))
            os.makedirs(base_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_path = os.path.join(base_dir, f"network-{ts}.jsonl")

            def safe_str(value):
                try:
                    return value if isinstance(value, str) else str(value)
                except Exception:
                    return "<unprintable>"

            with open(file_path, "a", encoding="utf-8") as f:
                for packet in packets:
                    try:
                        req = packet.request if hasattr(packet, "request") else None
                        resp = packet.response if hasattr(packet, "response") else None
                        fail = packet.fail_info if hasattr(packet, "fail_info") else None

                        item = {
                            "url": safe_str(packet.url) if hasattr(packet, "url") else safe_str(packet),
                            "method": safe_str(packet.method) if hasattr(packet, "method") else "UNKNOWN",
                            "resourceType": safe_str(packet.resourceType) if hasattr(packet, "resourceType") else "",
                            "is_failed": bool(packet.is_failed) if hasattr(packet, "is_failed") else False,
                            "fail_info": safe_str(fail) if fail else "",
                            "request": {
                                "headers": req.headers if req and hasattr(req, "headers") else {},
                                "postData": req.postData if req and hasattr(req, "postData") else "",
                            },
                            "response": {
                                "status": resp.status if resp and hasattr(resp, "status") else 0,
                                "headers": resp.headers if resp and hasattr(resp, "headers") else {},
                                "raw_body": resp.raw_body if resp and hasattr(resp, "raw_body") else "",
                            },
                        }
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    except Exception as e:
                        f.write(json.dumps({"error": safe_str(e)}, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _wait_for_code_input(self, page, timeout: int = 30):
        """"""
        selectors = [
            "css:input[jsname='ovqh0b']",
            "css:input[type='tel']",
            "css:input[name='pinInput']",
            "css:input[autocomplete='one-time-code']",
        ]
        for _ in range(timeout // 2):
            for selector in selectors:
                try:
                    el = page.ele(selector, timeout=1)
                    if el:
                        return el
                except Exception:
                    continue
            time.sleep(2)
        return None

    def _simulate_human_input(self, element, text: str) -> bool:
        """（，）

        Args:
            element: 
            text: 

        Returns:
            bool: 
        """
        try:
            # 
            element.click()
            time.sleep(random.uniform(0.1, 0.3))

            # 
            for char in text:
                element.input(char)
                # ：（50-150ms/）
                time.sleep(random.uniform(0.05, 0.15))

            # 
            time.sleep(random.uniform(0.2, 0.5))
            return True
        except Exception:
            return False

    def _find_verify_button(self, page):
        """（）"""
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and "" not in text and "" not in text and "resend" not in text and "send" not in text:
                    return btn
        except Exception:
            pass
        return None

    def _click_resend_code_button(self, page) -> bool:
        """"""
        time.sleep(2)

        # （ _find_verify_button ）
        try:
            buttons = page.eles("tag:button")
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if text and ("" in text or "resend" in text):
                    try:
                        self._log("info", f"🔄 ")
                        btn.click()
                        time.sleep(2)
                        return True
                    except Exception:
                        pass
        except Exception:
            pass

        return False

    def _handle_agreement_page(self, page) -> None:
        """Handle Gemini Business agreement/setup page"""
        if "/admin/create" in page.url:
            self._log("info", "📋 Agreement page detected, looking for form...")
            
            # Wait a bit for page to fully load
            time.sleep(2)
            
            # Check if there's a name input field that needs to be filled
            name_input = None
            name_selectors = [
                "css:input[type='text']",
                "css:input[placeholder*='name' i]",
                "css:input[placeholder*='Full name' i]"
            ]
            
            for selector in name_selectors:
                name_input = page.ele(selector, timeout=2)
                if name_input:
                    self._log("info", f"✅ Found name input: {selector}")
                    break
            
            if name_input:
                # Fill in the name field
                import random, string
                suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
                full_name = f"Test User {suffix}"
                
                self._log("info", f"⌨️ Filling name: {full_name}")
                name_input.click()
                time.sleep(0.2)
                
                if not self._simulate_human_input(name_input, full_name):
                    name_input.input(full_name, clear=True)
                
                time.sleep(0.5)
            
            # Now find and click the agreement button
            button_found = False
            
            # Strategy 1: Find by class
            agree_btn = page.ele("css:button.agree-button", timeout=2)
            if agree_btn:
                self._log("info", "✅ Found button by class")
                agree_btn.click()
                button_found = True
            else:
                # Strategy 2: Find button containing "Agree" text
                self._log("info", "🔍 Trying to find button by text...")
                buttons = page.eles("tag:button", timeout=3)
                for btn in buttons:
                    btn_text = (btn.text or "").strip().lower()
                    if "agree" in btn_text or "get started" in btn_text:
                        self._log("info", f"✅ Found button: {btn.text}")
                        btn.click()
                        button_found = True
                        break
            
            if not button_found:
                # Strategy 3: Find by type='submit'
                submit_btn = page.ele("css:button[type='submit']", timeout=2)
                if submit_btn:
                    self._log("info", "✅ Found submit button")
                    submit_btn.click()
                    button_found = True
            
            if button_found:
                self._log("info", "✅ Agreement button clicked, waiting...")
                time.sleep(3)
            else:
                self._log("warning", "⚠️ No agreement button found, continuing anyway...")
                time.sleep(1)

    def _wait_for_cid(self, page, timeout: int = 10) -> bool:
        """URLcid"""
        for _ in range(timeout):
            if "cid" in page.url:
                return True
            time.sleep(1)
        return False

    def _wait_for_business_params(self, page, timeout: int = 30) -> bool:
        """（csesidx  cid）"""
        for _ in range(timeout):
            url = page.url
            if "csesidx=" in url and "/cid/" in url:
                return True
            time.sleep(1)
        return False

    def _handle_username_setup(self, page) -> bool:
        """"""
        current_url = page.url

        if "auth.business.gemini.google/login" in current_url:
            return False

        selectors = [
            "css:input[type='text']",
            "css:input[name='displayName']",
            "css:input[aria-label*='' i]",
            "css:input[aria-label*='display name' i]",
        ]

        username_input = None
        for selector in selectors:
            try:
                username_input = page.ele(selector, timeout=2)
                if username_input:
                    break
            except Exception:
                continue

        if not username_input:
            return False

        suffix = "".join(random.choices(string.ascii_letters + string.digits, k=3))
        username = f"Test{suffix}"

        try:
            # 
            username_input.click()
            time.sleep(0.2)
            username_input.clear()
            time.sleep(0.1)

            # ，
            if not self._simulate_human_input(username_input, username):
                username_input.input(username)
                time.sleep(0.3)

            buttons = page.eles("tag:button")
            submit_btn = None
            for btn in buttons:
                text = (btn.text or "").strip().lower()
                if any(kw in text for kw in ["", "", "", "submit", "continue", "confirm", "save", "", "", "next"]):
                    submit_btn = btn
                    break

            if submit_btn:
                submit_btn.click()
            else:
                username_input.input("\n")

            time.sleep(5)
            return True
        except Exception:
            return False

    def _extract_config(self, page, email: str) -> dict:
        """Ekstrak konfigurasi"""
        try:
            if "cid/" not in page.url:
                page.get("https://business.gemini.google/", timeout=self.timeout)
                time.sleep(3)

            url = page.url
            if "cid/" not in url:
                return {"success": False, "error": "cid not found"}

            config_id = url.split("cid/")[1].split("?")[0].split("/")[0]
            csesidx = url.split("csesidx=")[1].split("&")[0] if "csesidx=" in url else ""

            cookies = page.cookies()
            ses = next((c["value"] for c in cookies if c["name"] == "__Secure-C_SES"), None)
            host = next((c["value"] for c in cookies if c["name"] == "__Host-C_OSES"), None)

            ses_obj = next((c for c in cookies if c["name"] == "__Secure-C_SES"), None)
            # ，（Cookie expiry  UTC ）
            beijing_tz = timezone(timedelta(hours=8))
            if ses_obj and "expiry" in ses_obj:
                #  UTC ，12
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

    def _save_screenshot(self, page, name: str) -> None:
        """"""
        try:
            from core.storage import _data_file_path
            screenshot_dir = _data_file_path("automation")
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{name}_{int(time.time())}.png")
            page.get_screenshot(path=path)
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

    def _cleanup_user_data(self, user_data_dir: Optional[str]) -> None:
        """"""
        if not user_data_dir:
            return
        try:
            import shutil
            if os.path.exists(user_data_dir):
                shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _get_ua() -> str:
        """User-Agent"""
        v = random.choice(["120.0.0.0", "121.0.0.0", "122.0.0.0"])
        return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
