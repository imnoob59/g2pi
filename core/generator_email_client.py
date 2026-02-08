"""
Generator.email Client
Email provider tanpa API - menggunakan generator.email
"""

import random
import re
import string
import time
from typing import Optional


class GeneratorEmailClient:
    """
    Client untuk generator.email
    Generate email tanpa API, baca OTP langsung dari web via browser driver
    """

    def __init__(
        self,
        domains: list = None,
        proxy: str = "",
        log_callback=None,
    ) -> None:
        self.base_url = "https://generator.email"
        self.domains = domains or ["yourdomain.com"]  # Setup your own domain with MX record!
        self.log_callback = log_callback
        
        self.email: Optional[str] = None
        self.username: Optional[str] = None
        self.domain: Optional[str] = None
        self.password: str = ""  # Generator.email tidak perlu password
        
        # Browser driver (akan di-set dari automation)
        self._browser_driver = None
        self._driver_type = None  # "dp" atau "uc"

    def _log(self, level: str, message: str):
        """Log callback"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def set_credentials(self, email: str, password: str = "") -> None:
        """Set credentials (untuk kompatibilitas interface)"""
        self.email = email
        self.password = password

    def set_browser_driver(self, driver, driver_type: str = "dp"):
        """
        Set browser driver untuk akses web
        driver_type: "dp" (DrissionPage) atau "uc" (undetected-chromedriver)
        """
        self._browser_driver = driver
        self._driver_type = driver_type
        self._log("info", f"🌐 Browser driver set: {driver_type}")

    def generate_random_username(self, length: int = 10) -> str:
        """Generate random username"""
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choices(chars, k=length))

    def register_account(self, domain: Optional[str] = None) -> bool:
        """Generate email baru (tanpa API call)"""
        try:
            # Pilih domain
            self.domain = domain or random.choice(self.domains)
            
            # Generate username random
            self.username = self.generate_random_username()
            self.email = f"{self.username}@{self.domain}"
            
            self._log("info", f"✅ Email generated: {self.email}")
            self._log("info", f"🌐 Check email di: {self.base_url}/{self.email}")
            
            return True
            
        except Exception as e:
            self._log("error", f"❌ Gagal generate email: {e}")
            return False

    def poll_for_code(
        self,
        timeout: int = 120,
        interval: int = 5,
        since_time=None,
    ) -> Optional[str]:
        """
        Tunggu dan ambil kode verifikasi dari email
        Menggunakan browser driver untuk akses web
        """
        if not self.email:
            self._log("error", "❌ Email belum dibuat!")
            return None
        
        if not self._browser_driver:
            self._log("error", "❌ Browser driver tidak tersedia!")
            self._log("error", "   Pastikan set_browser_driver() sudah dipanggil dari automation")
            return None
        
        url = f"{self.base_url}/{self.email}"
        max_retries = timeout // interval
        
        self._log("info", f"⏱️ Polling OTP dari generator.email (timeout: {timeout}s, interval: {interval}s, max: {max_retries} retries)")
        self._log("info", f"🌐 URL: {url}")
        
        for attempt in range(1, max_retries + 1):
            self._log("info", f"🔄 Percobaan #{attempt}/{max_retries} - Cek email...")
            
            try:
                code = self._fetch_code_from_web(url)
                if code:
                    self._log("info", f"🎉 Kode verifikasi ditemukan: {code}")
                    return code
                
                if attempt < max_retries:
                    self._log("info", f"⏳ Belum ada email, tunggu {interval} detik...")
                    time.sleep(interval)
                    
            except Exception as e:
                self._log("error", f"❌ Error saat cek email: {e}")
                if attempt < max_retries:
                    time.sleep(interval)
        
        self._log("error", f"⏰ Timeout! Tidak dapat kode verifikasi dalam {timeout} detik")
        return None

    def _fetch_code_from_web(self, url: str) -> Optional[str]:
        """
        Fetch kode verifikasi dari web menggunakan browser driver
        """
        try:
            if self._driver_type == "dp":
                # DrissionPage
                return self._fetch_code_drissionpage(url)
            elif self._driver_type == "uc":
                # Undetected-chromedriver (Selenium)
                return self._fetch_code_selenium(url)
            else:
                self._log("error", f"❌ Driver type tidak dikenal: {self._driver_type}")
                return None
                
        except Exception as e:
            self._log("error", f"❌ Error fetch code from web: {e}")
            return None

    def _fetch_code_drissionpage(self, url: str) -> Optional[str]:
        """Fetch code menggunakan DrissionPage"""
        page = self._browser_driver
        
        # Simpan tab/window saat ini
        original_tab = page.latest_tab
        
        try:
            # Buka tab baru
            self._log("info", "📂 Buka tab baru untuk cek email...")
            page.new_tab(url)
            new_tab = page.latest_tab
            
            # Tunggu page load
            time.sleep(3)
            
            # Ambil HTML content
            html_content = new_tab.html
            
            # Parse untuk cari email items (cari dalam html raw)
            code = self._extract_code_from_html(html_content)
            
            if code:
                self._log("info", f"✅ Code found in page")
                return code
            
            # Jika belum ketemu, coba cari email list dan klik detail
            # Cari link/elemen yang mengandung "Google" atau "verification"
            try:
                # Coba berbagai selector
                email_items = (
                    new_tab.eles('css:.email-item') or
                    new_tab.eles('css:.message-item') or  
                    new_tab.eles('css:tr') or
                    new_tab.eles('css:.mail-item')
                )
                
                for item in email_items[:5]:  # Cek 5 email terbaru
                    text = item.text.lower()
                    if 'google' in text or 'verification' in text or 'verify' in text:
                        self._log("info", f"📧 Email Google ditemukan, coba klik...")
                        
                        # Coba klik item
                        item.click()
                        time.sleep(2)
                        
                        # Cek lagi di page
                        html_content = new_tab.html
                        code = self._extract_code_from_html(html_content)
                        if code:
                            return code
            except Exception as e:
                self._log("info", f"Info: {e}")
            
            return None
            
        finally:
            # Tutup tab baru dan kembali ke tab original
            try:
                if new_tab != original_tab:
                    new_tab.close()
                    page.set.tab(original_tab)
            except Exception:
                pass

    def _fetch_code_selenium(self, url: str) -> Optional[str]:
        """Fetch code menggunakan Selenium (undetected-chromedriver)"""
        driver = self._browser_driver
        
        # Simpan window handle saat ini
        original_window = driver.current_window_handle
        
        try:
            # Buka tab/window baru
            self._log("info", "📂 Buka tab baru untuk cek email...")
            driver.execute_script(f"window.open('{url}', '_blank');")
            
            # Switch ke window baru
            all_windows = driver.window_handles
            new_window = [w for w in all_windows if w != original_window][0]
            driver.switch_to.window(new_window)
            
            # Tunggu page load
            time.sleep(3)
            
            # Ambil HTML content
            html_content = driver.page_source
            
            # Extract code
            code = self._extract_code_from_html(html_content)
            
            if code:
                self._log("info", f"✅ Code found in page")
                return code
            
            # Jika belum ketemu, coba cari dan klik email detail
            try:
                from selenium.webdriver.common.by import By
                
                # Cari email items
                selectors = [
                    (By.CLASS_NAME, "email-item"),
                    (By.CLASS_NAME, "message-item"),
                    (By.TAG_NAME, "tr"),
                ]
                
                for by, selector in selectors:
                    try:
                        items = driver.find_elements(by, selector)
                        for item in items[:5]:  # Cek 5 email terbaru
                            text = item.text.lower()
                            if 'google' in text or 'verification' in text or 'verify' in text:
                                self._log("info", f"📧 Email Google ditemukan, coba klik...")
                                item.click()
                                time.sleep(2)
                                
                                # Cek lagi
                                html_content = driver.page_source
                                code = self._extract_code_from_html(html_content)
                                if code:
                                    return code
                        break  # Jika selector ketemu, break
                    except Exception:
                        continue
            except Exception as e:
                self._log("info", f"Info: {e}")
            
            return None
            
        finally:
            # Tutup window baru dan kembali ke original
            try:
                driver.close()
                driver.switch_to.window(original_window)
            except Exception:
                pass

    def _extract_code_from_html(self, html: str) -> Optional[str]:
        """Extract verification code dari HTML content"""
        if not html:
            return None
        
        import re
        
        # PRIORITY 1: Cari code dalam box/highlight yang biasa dipakai Google
        # Google biasanya taruh OTP dalam div dengan background color/border
        otp_box_patterns = [
            r'<div[^>]*(?:background|border)[^>]*>[\s\n]*([A-Z0-9]{6})[\s\n]*</div>',
            r'<td[^>]*(?:background|border)[^>]*>[\s\n]*([A-Z0-9]{6})[\s\n]*</td>',
            r'<span[^>]*(?:font-size|color)[^>]*>[\s\n]*([A-Z0-9]{6})[\s\n]*</span>',
        ]
        
        for pattern in otp_box_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE | re.DOTALL)
            for match in matches:
                code = match.group(1).upper()
                if self._is_valid_code(code):
                    self._log("info", f"✅ OTP dari box: {code}")
                    return code
        
        # PRIORITY 2: Cari dengan context "one-time" atau "verification code is:"
        context_patterns = [
            r"one-time.*?code.*?[:：\s]\s*([A-Z0-9]{6})\b",
            r"verification\s+code\s+is.*?[:：\s]\s*([A-Z0-9]{6})\b",
            r"Your\s+(?:one-time\s+)?(?:verification\s+)?code\s+is.*?[:：\s]\s*([A-Z0-9]{6})\b",
        ]
        
        # Remove HTML tags untuk text matching
        text = re.sub(r'<[^>]+>', ' ', html)
        
        for pattern in context_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                code = match.group(1).upper()
                if self._is_valid_code(code):
                    self._log("info", f"✅ OTP dari context: {code}")
                    return code
        
        # PRIORITY 3: Fallback - cari 6 karakter A-Z0-9 anywhere
        pattern = r"\b([A-Z0-9]{6})\b"
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.group(1).upper()
            if self._is_valid_code(code):
                self._log("info", f"⚠️ OTP fallback: {code}")
                return code
        
        return None

    def _is_valid_code(self, code: str) -> bool:
        """Validasi apakah code valid (bukan false positive)"""
        if not code or len(code) != 6:
            return False
        
        import re
        
        # Skip jika css units, colors, atau common words
        if re.match(r"^\d+(?:PX|PT|EM|REM|VH|VW|PC|FF|CC|EE|AA|BB|DD)$", code, re.IGNORECASE):
            return False
        
        # Skip common false positives (HTML/CSS/JS keywords)
        false_positives = [
            "SCRIPT", "IFRAME", "BUTTON", "CLICK", "MAILTO", "HTTPS",
            "GOOGLE", "VERIFY", "CHROME", "WINDOW", "MARGIN", "BORDER",
            "WEBKIT", "INLINE", "HEADER", "FOOTER", "CENTER", "BUYAPP"  # BUYAPP juga false positive!
        ]
        if code.upper() in false_positives:
            return False
        
        # OTP Google biasanya mix alpha-numeric, bukan pure alpha biasa
        # Acceptable: EKZT7E, 123ABC, dll
        return True
