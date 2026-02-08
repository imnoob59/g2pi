"""
SetFungsi

Format:
- http://127.0.0.1:7890
- http://user:pass@127.0.0.1:7890
- socks5h://127.0.0.1:7890
- socks5h://user:pass@127.0.0.1:7890 | no_proxy=localhost,127.0.0.1,.local

NO_PROXY Format:
- atau
- ， .local  *.local
"""

import re
from typing import Tuple, Callable, Any, Optional
from urllib.parse import urlparse
import functools


def parse_proxy_setting(proxy_str: str) -> Tuple[str, str]:
    """
    ParseSetString，Ekstrak URL dan NO_PROXY List

    Args:
        proxy_str: SetString，Format "http://127.0.0.1:7890 | no_proxy=localhost,127.0.0.1"

    Returns:
        Tuple[str, str]: (proxy_url, no_proxy_list)
        - proxy_url: ， "http://127.0.0.1:7890"
        - no_proxy_list: NO_PROXY ListString， "localhost,127.0.0.1"
    """
    if not proxy_str:
        return "", ""

    proxy_str = proxy_str.strip()
    if not proxy_str:
        return "", ""

    # CekYaTidak no_proxy Set
    # Format: proxy_url | no_proxy=host1,host2
    no_proxy = ""
    proxy_url = proxy_str

    #  | dan no_proxy
    if "|" in proxy_str:
        parts = proxy_str.split("|", 1)
        proxy_url = parts[0].strip()
        no_proxy_part = parts[1].strip()

        # Parse no_proxy=xxx Format
        no_proxy_match = re.match(r"no_proxy\s*=\s*(.+)", no_proxy_part, re.IGNORECASE)
        if no_proxy_match:
            no_proxy = no_proxy_match.group(1).strip()

    return proxy_url, no_proxy


def extract_host(url: str) -> str:
    """
     URL Ekstrak

    Args:
        url:  URL， "https://mail.chatgpt.org.uk/api/emails"

    Returns:
        str: ， "mail.chatgpt.org.uk"
    """
    if not url:
        return ""

    url = url.strip()
    if not url:
        return ""

    # JikaAda，Parse
    if not url.startswith(("http://", "https://", "socks5://", "socks5h://")):
        url = "http://" + url

    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


def no_proxy_matches(host: str, no_proxy: str) -> bool:
    """
    CekYaTidak NO_PROXY List

    Args:
        host: Cek， "mail.chatgpt.org.uk"
        no_proxy: NO_PROXY ListString， "localhost,127.0.0.1,.local"

    Returns:
        bool: JikaListReturn True，Jika tidakReturn False

    maka:
        - : "localhost"  "localhost"
        - : ".local"  "foo.local", "bar.foo.local"
        - IP : "127.0.0.1" 
    """
    if not host or not no_proxy:
        return False

    host = host.lower().strip()
    if not host:
        return False

    # Parse no_proxy List
    no_proxy_list = [item.strip().lower() for item in no_proxy.split(",") if item.strip()]

    for pattern in no_proxy_list:
        if not pattern:
            continue

        # 
        if host == pattern:
            return True

        #  ( .local  foo.local)
        if pattern.startswith("."):
            if host.endswith(pattern) or host == pattern[1:]:
                return True
        else:
            # tidak ( local  foo.local)
            if host.endswith("." + pattern):
                return True

    return False


def normalize_proxy_url(proxy_str: str) -> str:
    """
     URL Format

    Format:
    - http://127.0.0.1:7890
    - http://user:pass@127.0.0.1:7890
    - socks5://127.0.0.1:7890
    - socks5h://127.0.0.1:7890
    - 127.0.0.1:7890 ( http://)
    - host:port:user:pass (Format，Konversi)

    Returns:
        str:  URL
    """
    if not proxy_str:
        return ""

    proxy_str = proxy_str.strip()
    if not proxy_str:
        return ""

    # JikasudahYa URL Format，Return
    if proxy_str.startswith(("http://", "https://", "socks5://", "socks5h://")):
        return proxy_str

    # ParseFormat host:port:user:pass
    parts = proxy_str.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    elif len(parts) == 2:
        # host:port Format
        return f"http://{proxy_str}"

    # Tidak adaFormat， http:// 
    return f"http://{proxy_str}"


def request_with_proxy_fallback(request_func: Callable, *args, **kwargs) -> Any:
    """
    Gagal

    JikaKoneksiGagal，Retry

    Args:
        request_func: Fungsi
        *args, **kwargs: FungsiParameter

    Returns:
        Objek

    Raises:
        （JikaGagal）
    """
    # ErrorTipe
    PROXY_ERRORS = (
        "ProxyError",
        "ConnectTimeout",
        "ConnectionError",
        "407",  # Proxy Authentication Required
        "502",  # Bad Gateway ()
        "503",  # Service Unavailable ()
    )

    try:
        # （）
        return request_func(*args, **kwargs)
    except Exception as e:
        error_str = str(e)
        error_type = type(e).__name__

        # CekYaTidakYaError
        is_proxy_error = any(err in error_str or err in error_type for err in PROXY_ERRORS)

        if is_proxy_error and "proxies" in kwargs:
            # Retry
            original_proxies = kwargs.get("proxies")
            kwargs["proxies"] = None

            try:
                # Retry
                return request_func(*args, **kwargs)
            except Exception:
                # Gagal，Set
                kwargs["proxies"] = original_proxies
                raise e
        else:
            # tidakYaError，
            raise
