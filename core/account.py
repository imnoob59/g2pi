"""Modul manajemen akun

Bertanggung jawab untuk konfigurasi akun, koordinasi multi-akun dan manajemen cache sesi
"""
import asyncio
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, TYPE_CHECKING, Iterable

from fastapi import HTTPException

# Import lapisan storage (mendukung database)
from core import storage

if TYPE_CHECKING:
    from core.jwt import JWTManager

logger = logging.getLogger(__name__)

# Mapping nama error HTTP
HTTP_ERROR_NAMES = {
    400: "Error parameter",
    401: "Error autentikasi",
    403: "Error izin",
    429: "Rate limit",
    502: "Error gateway",
    503: "Layanan tidak tersedia"
}

# Definisi tipe kuota
QUOTA_TYPES = {
    "text": "Obrolan",
    "images": "Gambar",
    "videos": "Video"
}

@dataclass
class AccountConfig:
    """Konfigurasi akun tunggal"""
    account_id: str
    secure_c_ses: str
    host_c_oses: Optional[str]
    csesidx: str
    config_id: str
    expires_at: Optional[str] = None  # Waktu kedaluwarsa akun (Format: "2025-12-23 10:59:21")
    disabled: bool = False  # Status dinonaktifkan manual
    mail_provider: Optional[str] = None
    mail_address: Optional[str] = None
    mail_password: Optional[str] = None
    mail_client_id: Optional[str] = None
    mail_refresh_token: Optional[str] = None
    mail_tenant: Optional[str] = None
    # Field konfigurasi kustom email (untuk konfigurasi layanan email tingkat akun)
    mail_base_url: Optional[str] = None
    mail_jwt_token: Optional[str] = None
    mail_verify_ssl: Optional[bool] = None
    mail_domain: Optional[str] = None
    mail_api_key: Optional[str] = None

    def get_remaining_hours(self) -> Optional[float]:
        """Hitung sisa jam akun"""
        if not self.expires_at:
            return None
        try:
            # Parse waktu kedaluwarsa (diasumsikan waktu Beijing)
            beijing_tz = timezone(timedelta(hours=8))
            expire_time = datetime.strptime(self.expires_at, "%Y-%m-%d %H:%M:%S")
            expire_time = expire_time.replace(tzinfo=beijing_tz)

            # Waktu saat ini (waktu Beijing)
            now = datetime.now(beijing_tz)

            # Hitung sisa waktu
            remaining = (expire_time - now).total_seconds() / 3600
            return remaining
        except Exception:
            return None

    def is_expired(self) -> bool:
        """Cek apakah akun sudah kedaluwarsa"""
        remaining = self.get_remaining_hours()
        if remaining is None:
            return False  # Waktu kedaluwarsa tidak diset, default tidak kedaluwarsa
        return remaining <= 0


@dataclass(frozen=True)
class CooldownConfig:
    text: int
    images: int
    videos: int


@dataclass(frozen=True)
class RetryPolicy:
    cooldowns: CooldownConfig


def format_account_expiration(remaining_hours: Optional[float]) -> tuple:
    """
    Format tampilan waktu kedaluwarsa akun (berbasis siklus 12 jam)

    Args:
        remaining_hours: Sisa jam (None berarti waktu kedaluwarsa tidak diset)

    Returns:
        (status, status_color, expire_display) 
    """
    if remaining_hours is None:
        # ""
        return ("", "#9e9e9e", "")
    elif remaining_hours <= 0:
        return ("Sudah kedaluwarsa", "#f44336", "Sudah kedaluwarsa")
    elif remaining_hours < 3:  # 3
        return ("", "#ff9800", f"{remaining_hours:.1f} ")
    else:  # 3，
        return ("Normal", "#4caf50", f"{remaining_hours:.1f} ")


class AccountManager:
    """"""
    def __init__(
        self,
        config: AccountConfig,
        http_client,
        user_agent: str,
        retry_policy: RetryPolicy,
    ):
        self.config = config
        self.http_client = http_client
        self.user_agent = user_agent
        # 
        self.rate_limit_cooldown_seconds = retry_policy.cooldowns.text  # 
        self.text_rate_limit_cooldown_seconds = retry_policy.cooldowns.text
        self.images_rate_limit_cooldown_seconds = retry_policy.cooldowns.images
        self.videos_rate_limit_cooldown_seconds = retry_policy.cooldowns.videos
        self.jwt_manager: Optional['JWTManager'] = None  # 
        self.is_available = True
        self.last_error_time = 0.0  # 
        self.quota_cooldowns: Dict[str, float] = {}  # 
        self.conversation_count = 0  # （）
        self.failure_count = 0  # （）
        self.session_usage_count = 0  # （）

    def handle_non_http_error(self, error_context: str = "", request_id: str = "", quota_type: Optional[str] = None) -> None:
        """
        HTTP（、）- 

        Args:
            error_context: （"JWT"、"hari"）
            request_id: ID（）
            quota_type: （"text", "images", "videos"），
        """
        req_tag = f"[req_{request_id}] " if request_id else ""

        # ，Obrolan（Obrolan）
        if not quota_type or quota_type not in QUOTA_TYPES:
            quota_type = "text"

        self.quota_cooldowns[quota_type] = time.time()
        cooldown_seconds = self._get_quota_cooldown_seconds(quota_type)
        logger.warning(
            f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
            f"{error_context}，{QUOTA_TYPES[quota_type]}{cooldown_seconds}"
        )

    def _get_quota_cooldown_seconds(self, quota_type: Optional[str]) -> int:
        if quota_type == "images":
            return self.images_rate_limit_cooldown_seconds
        if quota_type == "videos":
            return self.videos_rate_limit_cooldown_seconds
        return self.text_rate_limit_cooldown_seconds

    def apply_retry_policy(self, retry_policy: RetryPolicy) -> None:
        """Apply updated retry policy to this account manager."""
        self.rate_limit_cooldown_seconds = retry_policy.cooldowns.text  # 
        self.text_rate_limit_cooldown_seconds = retry_policy.cooldowns.text
        self.images_rate_limit_cooldown_seconds = retry_policy.cooldowns.images
        self.videos_rate_limit_cooldown_seconds = retry_policy.cooldowns.videos

    def handle_http_error(self, status_code: int, error_detail: str = "", request_id: str = "", quota_type: Optional[str] = None) -> None:
        """
        HTTP - 

        Args:
            status_code: HTTP
            error_detail: 
            request_id: ID（）
            quota_type: （"text", "images", "videos"），

        ：
            - 400: Error parameter，（）
            - : （Obrolan）
        """
        req_tag = f"[req_{request_id}] " if request_id else ""

        # 400Error parameter：（）
        if status_code == 400:
            logger.warning(
                f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
                f"HTTP 400Error parameter（）{': ' + error_detail[:100] if error_detail else ''}"
            )
            return

        # ：（Obrolan）
        if not quota_type or quota_type not in QUOTA_TYPES:
            quota_type = "text"

        self.quota_cooldowns[quota_type] = time.time()
        cooldown_seconds = self._get_quota_cooldown_seconds(quota_type)
        error_type = HTTP_ERROR_NAMES.get(status_code, f"HTTP {status_code}")
        logger.warning(
            f"[ACCOUNT] [{self.config.account_id}] {req_tag}"
            f"{error_type}，{QUOTA_TYPES[quota_type]}{cooldown_seconds}"
            f"{': ' + error_detail[:100] if error_detail else ''}"
        )

    def is_quota_available(self, quota_type: str) -> bool:
        """（）。"""
        if quota_type not in QUOTA_TYPES:
            return True

        cooldown_time = self.quota_cooldowns.get(quota_type)
        if not cooldown_time:
            return True

        elapsed = time.time() - cooldown_time
        cooldown_seconds = self._get_quota_cooldown_seconds(quota_type)
        if elapsed < cooldown_seconds:
            return False

        # Sudah kedaluwarsa，
        del self.quota_cooldowns[quota_type]
        return True

    def are_quotas_available(self, quota_types: Optional[Iterable[str]] = None) -> bool:
        """
        。

        ：Obrolan，（Obrolan）
        """
        if not quota_types:
            return True
        if isinstance(quota_types, str):
            quota_types = [quota_types]

        # Obrolan，
        if not self.is_quota_available("text"):
            return False

        # 
        return all(self.is_quota_available(qt) for qt in quota_types if qt != "text")

    async def get_jwt(self, request_id: str = "") -> str:
        """ JWT token ()"""
        # 
        if self.config.is_expired():
            self.is_available = False
            logger.warning(f"[ACCOUNT] [{self.config.account_id}] Sudah kedaluwarsa，")
            raise HTTPException(403, f"Account {self.config.account_id} has expired")

        try:
            if self.jwt_manager is None:
                #  JWTManager ()
                from core.jwt import JWTManager
                self.jwt_manager = JWTManager(self.config, self.http_client, self.user_agent)
            jwt = await self.jwt_manager.get(request_id)
            self.is_available = True
            return jwt
        except Exception as e:
            # 
            if isinstance(e, HTTPException):
                self.handle_http_error(e.status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id)
            else:
                self.handle_non_http_error("JWT", request_id)
            raise

    def should_retry(self) -> bool:
        """ - ：（）"""
        # ，
        return True

    def get_cooldown_info(self) -> tuple[int, str | None]:
        """（）"""
        current_time = time.time()

        # （）
        max_quota_remaining = 0
        limited_quota_types = []  # （text/images/videos）
        quota_icons = {"text": "💬", "images": "🎨", "videos": "🎬"}

        for quota_type in QUOTA_TYPES:
            if quota_type in self.quota_cooldowns:
                cooldown_time = self.quota_cooldowns[quota_type]
                elapsed = current_time - cooldown_time
                cooldown_seconds = self._get_quota_cooldown_seconds(quota_type)
                if elapsed < cooldown_seconds:
                    remaining = int(cooldown_seconds - elapsed)
                    if remaining > max_quota_remaining:
                        max_quota_remaining = remaining
                    limited_quota_types.append(quota_type)

        # ，
        if max_quota_remaining > 0:
            #  emoji 
            icons = "".join([quota_icons[qt] for qt in limited_quota_types])

            # 
            if len(limited_quota_types) == 3:
                return (max_quota_remaining, f"{icons} ")
            elif len(limited_quota_types) == 1:
                # 
                quota_name = QUOTA_TYPES[limited_quota_types[0]]
                return (max_quota_remaining, f"{icons} {quota_name}")
            else:
                # （）
                quota_names = "/".join([QUOTA_TYPES[qt] for qt in limited_quota_types])
                return (max_quota_remaining, f"{icons} {quota_names}")

        # ，Normal
        return (0, None)

    def get_quota_status(self) -> Dict[str, any]:
        """
        （）

        Returns:
            {
                "quotas": {
                    "text": {"available": bool, "remaining_seconds": int},
                    "images": {"available": bool, "remaining_seconds": int},
                    "videos": {"available": bool, "remaining_seconds": int}
                },
                "limited_count": int,  # 
                "total_count": int,    # 
                "is_expired": bool     # /
            }
        """
        # 
        is_expired = self.config.is_expired() or self.config.disabled
        if is_expired:
            # ，
            quotas = {quota_type: {"available": False} for quota_type in QUOTA_TYPES}
            return {
                "quotas": quotas,
                "limited_count": len(QUOTA_TYPES),
                "total_count": len(QUOTA_TYPES),
                "is_expired": True
            }

        current_time = time.time()

        quotas = {}
        limited_count = 0
        expired_quotas = []  # Sudah kedaluwarsa
        text_limited = False  # Obrolan

        # ：
        for quota_type in QUOTA_TYPES:
            if quota_type in self.quota_cooldowns:
                cooldown_time = self.quota_cooldowns[quota_type]
                # （）
                elapsed = current_time - cooldown_time
                cooldown_seconds = self._get_quota_cooldown_seconds(quota_type)
                if elapsed < cooldown_seconds:
                    remaining = int(cooldown_seconds - elapsed)
                    quotas[quota_type] = {
                        "available": False,
                        "remaining_seconds": remaining
                    }
                    limited_count += 1
                    # Obrolan
                    if quota_type == "text":
                        text_limited = True
                else:
                    # ，
                    expired_quotas.append(quota_type)
                    quotas[quota_type] = {"available": True}
            else:
                # Rate limit
                quotas[quota_type] = {"available": True}

        # Sudah kedaluwarsa
        for quota_type in expired_quotas:
            del self.quota_cooldowns[quota_type]

        # Obrolan，（Obrolan）
        if text_limited:
            for quota_type in QUOTA_TYPES:
                if quota_type != "text" and quotas[quota_type].get("available", False):
                    quotas[quota_type] = {
                        "available": False,
                        "reason": "Obrolan"
                    }
                    limited_count += 1

        return {
            "quotas": quotas,
            "limited_count": limited_count,
            "total_count": len(QUOTA_TYPES),
            "is_expired": False
        }


class MultiAccountManager:
    """"""
    def __init__(self, session_cache_ttl_seconds: int):
        self.accounts: Dict[str, AccountManager] = {}
        self.account_list: List[str] = []  # ID ()
        self.current_index = 0
        self._cache_lock = asyncio.Lock()  # 
        self._counter_lock = threading.Lock()  # 
        self._request_counter = 0  # 
        self._last_account_count = 0  # 
        # ：{conv_key: {"account_id": str, "session_id": str, "updated_at": float}}
        self.global_session_cache: Dict[str, dict] = {}
        self.cache_max_size = 1000  # 
        self.cache_ttl = session_cache_ttl_seconds  # （）
        # Session：Obrolan
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks_lock = asyncio.Lock()  # 
        self._session_locks_max_size = 2000  # 

    def _clean_expired_cache(self):
        """"""
        current_time = time.time()
        expired_keys = [
            key for key, value in self.global_session_cache.items()
            if current_time - value["updated_at"] > self.cache_ttl
        ]
        for key in expired_keys:
            del self.global_session_cache[key]
        if expired_keys:
            logger.info(f"[CACHE]  {len(expired_keys)} ")

    def _ensure_cache_size(self):
        """（LRU）"""
        if len(self.global_session_cache) > self.cache_max_size:
            # ，20%
            sorted_items = sorted(
                self.global_session_cache.items(),
                key=lambda x: x[1]["updated_at"]
            )
            remove_count = len(sorted_items) - int(self.cache_max_size * 0.8)
            for key, _ in sorted_items[:remove_count]:
                del self.global_session_cache[key]
            logger.info(f"[CACHE] LRU {remove_count} ")

    async def start_background_cleanup(self):
        """（5）"""
        try:
            while True:
                await asyncio.sleep(300)  # 5
                async with self._cache_lock:
                    self._clean_expired_cache()
                    self._ensure_cache_size()
        except asyncio.CancelledError:
            logger.info("[CACHE] ")
        except Exception as e:
            logger.error(f"[CACHE] : {e}")

    async def set_session_cache(self, conv_key: str, account_id: str, session_id: str):
        """"""
        async with self._cache_lock:
            self.global_session_cache[conv_key] = {
                "account_id": account_id,
                "session_id": session_id,
                "updated_at": time.time()
            }
            # 
            self._ensure_cache_size()

    async def update_session_time(self, conv_key: str):
        """"""
        async with self._cache_lock:
            if conv_key in self.global_session_cache:
                self.global_session_cache[conv_key]["updated_at"] = time.time()

    async def acquire_session_lock(self, conv_key: str) -> asyncio.Lock:
        """Obrolan（Obrolan）"""
        async with self._session_locks_lock:
            # （LRU：）
            if len(self._session_locks) > self._session_locks_max_size:
                # 
                valid_keys = set(self.global_session_cache.keys())
                keys_to_remove = [k for k in self._session_locks if k not in valid_keys]
                for k in keys_to_remove[:len(keys_to_remove)//2]:  # 
                    del self._session_locks[k]

            if conv_key not in self._session_locks:
                self._session_locks[conv_key] = asyncio.Lock()
            return self._session_locks[conv_key]

    def update_http_client(self, http_client):
        """ http_client（）"""
        for account_mgr in self.accounts.values():
            account_mgr.http_client = http_client
            if account_mgr.jwt_manager is not None:
                account_mgr.jwt_manager.http_client = http_client

    def add_account(
        self,
        config: AccountConfig,
        http_client,
        user_agent: str,
        retry_policy: RetryPolicy,
        global_stats: dict,
    ):
        """"""
        manager = AccountManager(config, http_client, user_agent, retry_policy)
        # Obrolan
        if "account_conversations" in global_stats:
            manager.conversation_count = global_stats["account_conversations"].get(config.account_id, 0)
        if "account_failures" in global_stats:
            manager.failure_count = global_stats["account_failures"].get(config.account_id, 0)
        self.accounts[config.account_id] = manager
        self.account_list.append(config.account_id)
        logger.debug(f"[MULTI] [ACCOUNT] : {config.account_id}")

    def get_available_accounts(
        self,
        required_quota_types: Optional[Iterable[str]] = None
    ) -> List[AccountManager]:
        """（、、）

        Args:
            required_quota_types: （ ["text"], ["images"], ["text", "videos"]）

        Returns:
            

        ：
            1. disabled=True → （）
            2. is_expired() → （）
            3. are_quotas_available() → （）
        """
        available = []

        for acc in self.accounts.values():
            # 1. 
            if acc.config.disabled:
                continue

            # 2. 
            if acc.config.is_expired():
                continue

            # 3. （）
            if not acc.are_quotas_available(required_quota_types):
                continue

            available.append(acc)

        return available

    async def get_account(
        self,
        account_id: Optional[str] = None,
        request_id: str = "",
        required_quota_types: Optional[Iterable[str]] = None
    ) -> AccountManager:
        """ - Round-Robin

        Args:
            account_id: ID（，）
            request_id: ID（）
            required_quota_types: 

        Returns:
            

        Raises:
            HTTPException(404): 
            HTTPException(503): 
        """
        req_tag = f"[req_{request_id}] " if request_id else ""

        # ID
        if account_id:
            if account_id not in self.accounts:
                raise HTTPException(404, f"Account {account_id} not found")
            account = self.accounts[account_id]
            if not account.should_retry():
                raise HTTPException(503, f"Account {account_id} temporarily unavailable")
            if not account.are_quotas_available(required_quota_types):
                raise HTTPException(503, f"Account {account_id} quota temporarily unavailable")
            return account

        # 
        available_accounts = self.get_available_accounts(required_quota_types)

        if not available_accounts:
            raise HTTPException(503, "No available accounts")

        # 
        with self._counter_lock:
            if len(available_accounts) != self._last_account_count:
                self._request_counter = random.randint(0, 999999)
                self._last_account_count = len(available_accounts)
            index = self._request_counter % len(available_accounts)
            self._request_counter += 1

        selected = available_accounts[index]
        selected.session_usage_count += 1

        logger.info(f"[MULTI] [ACCOUNT] {req_tag}: {selected.config.account_id} "
                    f"(: {index}/{len(available_accounts)}, : {selected.session_usage_count})")
        return selected


# ----------  ----------

def save_accounts_to_file(accounts_data: list):
    """（）。"""
    if not storage.is_database_enabled():
        raise RuntimeError("Database is not enabled")
    saved = storage.save_accounts_sync(accounts_data)
    if not saved:
        raise RuntimeError("Database write failed")


def load_accounts_from_source() -> list:
    """。"""
    env_accounts = os.environ.get('ACCOUNTS_CONFIG')
    if env_accounts:
        try:
            accounts_data = json.loads(env_accounts)
            if accounts_data:
                logger.info(f"[CONFIG] ， {len(accounts_data)} ")
            else:
                logger.warning("[CONFIG]  ACCOUNTS_CONFIG ")
            return accounts_data
        except Exception as e:
            logger.error(f"[CONFIG] : {str(e)}")

    if storage.is_database_enabled():
        try:
            accounts_data = storage.load_accounts_sync()

            # ：，
            if accounts_data is None:
                logger.error("[CONFIG] ❌ ")
                logger.error("[CONFIG]  DATABASE_URL ")
                raise RuntimeError("，")

            if accounts_data:
                logger.info(f"[CONFIG] ， {len(accounts_data)} ")
            else:
                logger.warning("[CONFIG] ")
                logger.warning("[CONFIG] ，: python scripts/migrate_to_database.py")

            return accounts_data
        except RuntimeError:
            #  RuntimeError（）
            raise
        except Exception as e:
            logger.error(f"[CONFIG] ❌ : {e}")
            raise RuntimeError(f": {e}")

    logger.error("[CONFIG]  ACCOUNTS_CONFIG")
    return []


def get_account_id(acc: dict, index: int) -> str:
    """ID（ID，ID）"""
    return acc.get("id", f"account_{index}")


def load_multi_account_config(
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """"""
    manager = MultiAccountManager(session_cache_ttl_seconds)

    accounts_data = load_accounts_from_source()

    for i, acc in enumerate(accounts_data, 1):
        # 
        required_fields = ["secure_c_ses", "csesidx", "config_id"]
        missing_fields = [f for f in required_fields if f not in acc]
        if missing_fields:
            raise ValueError(f" {i} : {', '.join(missing_fields)}")

        config = AccountConfig(
            account_id=get_account_id(acc, i),
            secure_c_ses=acc["secure_c_ses"],
            host_c_oses=acc.get("host_c_oses"),
            csesidx=acc["csesidx"],
            config_id=acc["config_id"],
            expires_at=acc.get("expires_at"),
            disabled=acc.get("disabled", False),  # Status dinonaktifkan manual，False
            mail_provider=acc.get("mail_provider"),
            mail_address=acc.get("mail_address"),
            mail_password=acc.get("mail_password") or acc.get("email_password"),
            mail_client_id=acc.get("mail_client_id"),
            mail_refresh_token=acc.get("mail_refresh_token"),
            mail_tenant=acc.get("mail_tenant"),
        )

        # Cek apakah akun sudah kedaluwarsa（Sudah kedaluwarsa）
        is_expired = config.is_expired()
        if is_expired:
            logger.debug(f"[CONFIG]  {config.account_id} Sudah kedaluwarsa，")

        manager.add_account(config, http_client, user_agent, retry_policy, global_stats)

        # 
        account_mgr = manager.accounts[config.account_id]
        if "quota_cooldowns" in acc:
            account_mgr.quota_cooldowns = dict(acc["quota_cooldowns"])
        if "conversation_count" in acc:
            account_mgr.conversation_count = int(acc.get("conversation_count", 0))
        if "failure_count" in acc:
            account_mgr.failure_count = int(acc.get("failure_count", 0))

        if is_expired:
            manager.accounts[config.account_id].is_available = False

    if not manager.accounts:
        logger.warning(f"[CONFIG] ，，")
    else:
        logger.info(f"[CONFIG]  {len(manager.accounts)} ")
    return manager


def reload_accounts(
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """Reload account config and preserve runtime cooldown/error state."""
    # Preserve stats + runtime state to avoid clearing cooldowns on reload.
    old_stats = {}
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        old_stats[account_id] = {
            "conversation_count": account_mgr.conversation_count,
            "failure_count": account_mgr.failure_count,
            "is_available": account_mgr.is_available,
            "last_error_time": account_mgr.last_error_time,
            "session_usage_count": account_mgr.session_usage_count,
            "quota_cooldowns": dict(account_mgr.quota_cooldowns),
        }

    # Clear session cache and reload config.
    multi_account_mgr.global_session_cache.clear()
    new_mgr = load_multi_account_config(
        http_client,
        user_agent,
        retry_policy,
        session_cache_ttl_seconds,
        global_stats
    )

    # Restore stats + runtime state.
    for account_id, stats in old_stats.items():
        if account_id in new_mgr.accounts:
            account_mgr = new_mgr.accounts[account_id]
            account_mgr.conversation_count = stats["conversation_count"]
            account_mgr.failure_count = stats.get("failure_count", 0)
            account_mgr.is_available = stats.get("is_available", True)
            account_mgr.last_error_time = stats.get("last_error_time", 0.0)
            account_mgr.session_usage_count = stats.get("session_usage_count", 0)
            account_mgr.quota_cooldowns = stats.get("quota_cooldowns", {})
            logger.debug(f"[CONFIG] Account {account_id} refreshed; runtime state preserved")

    logger.info(
        f"[CONFIG] Reloaded config; accounts={len(new_mgr.accounts)}; cooldown/error state preserved"
    )
    return new_mgr


def update_accounts_config(
    accounts_data: list,
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """（）"""
    save_accounts_to_file(accounts_data)
    return reload_accounts(
        multi_account_mgr,
        http_client,
        user_agent,
        retry_policy,
        session_cache_ttl_seconds,
        global_stats
    )


def delete_account(
    account_id: str,
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> MultiAccountManager:
    """"""
    if storage.is_database_enabled():
        deleted = storage.delete_accounts_sync([account_id])
        if deleted <= 0:
            raise ValueError(f" {account_id} ")
        return reload_accounts(
            multi_account_mgr,
            http_client,
            user_agent,
            retry_policy,
            session_cache_ttl_seconds,
            global_stats
        )

    accounts_data = load_accounts_from_source()

    filtered = [
        acc for i, acc in enumerate(accounts_data, 1)
        if get_account_id(acc, i) != account_id
    ]

    if len(filtered) == len(accounts_data):
        raise ValueError(f" {account_id} ")

    save_accounts_to_file(filtered)
    return reload_accounts(
        multi_account_mgr,
        http_client,
        user_agent,
        retry_policy,
        session_cache_ttl_seconds,
        global_stats
    )


def update_account_disabled_status(
    account_id: str,
    disabled: bool,
    multi_account_mgr: MultiAccountManager,
) -> MultiAccountManager:
    """（：）。"""
    if storage.is_database_enabled():
        updated = storage.update_account_disabled_sync(account_id, disabled)
        if not updated:
            raise ValueError(f" {account_id} ")
        if account_id in multi_account_mgr.accounts:
            multi_account_mgr.accounts[account_id].config.disabled = disabled
        return multi_account_mgr

    if account_id not in multi_account_mgr.accounts:
        raise ValueError(f" {account_id} ")
    account_mgr = multi_account_mgr.accounts[account_id]
    account_mgr.config.disabled = disabled

    accounts_data = load_accounts_from_source()
    for i, acc in enumerate(accounts_data, 1):
        if get_account_id(acc, i) == account_id:
            acc["disabled"] = disabled
            break

    save_accounts_to_file(accounts_data)

    status_text = "" if disabled else ""
    logger.info(f"[CONFIG]  {account_id} {status_text}")
    return multi_account_mgr


def bulk_update_account_disabled_status(
    account_ids: list[str],
    disabled: bool,
    multi_account_mgr: MultiAccountManager,
) -> tuple[int, list[str]]:
    """，20。"""
    if storage.is_database_enabled():
        updated, missing = storage.bulk_update_accounts_disabled_sync(account_ids, disabled)
        for account_id in account_ids:
            if account_id in multi_account_mgr.accounts:
                multi_account_mgr.accounts[account_id].config.disabled = disabled
        errors = [f"{account_id}: " for account_id in missing]
        status_text = "" if disabled else ""
        logger.info(f"[CONFIG] {status_text} {updated}/{len(account_ids)} ")
        return updated, errors

    success_count = 0
    errors = []

    for account_id in account_ids:
        if account_id not in multi_account_mgr.accounts:
            errors.append(f"{account_id}: ")
            continue
        account_mgr = multi_account_mgr.accounts[account_id]
        account_mgr.config.disabled = disabled
        success_count += 1

    accounts_data = load_accounts_from_source()
    account_id_set = set(account_ids)

    for i, acc in enumerate(accounts_data, 1):
        acc_id = get_account_id(acc, i)
        if acc_id in account_id_set:
            acc["disabled"] = disabled

    save_accounts_to_file(accounts_data)

    status_text = "" if disabled else ""
    logger.info(f"[CONFIG] {status_text} {success_count}/{len(account_ids)} ")
    return success_count, errors


def bulk_delete_accounts(
    account_ids: list[str],
    multi_account_mgr: MultiAccountManager,
    http_client,
    user_agent: str,
    retry_policy: RetryPolicy,
    session_cache_ttl_seconds: int,
    global_stats: dict
) -> tuple[MultiAccountManager, int, list[str]]:
    """，20。"""
    if storage.is_database_enabled():
        existing_ids = set(multi_account_mgr.accounts.keys())
        missing = [account_id for account_id in account_ids if account_id not in existing_ids]
        deleted = storage.delete_accounts_sync(account_ids)
        errors = [f"{account_id}: " for account_id in missing]
        if deleted > 0:
            multi_account_mgr = reload_accounts(
                multi_account_mgr,
                http_client,
                user_agent,
                retry_policy,
                session_cache_ttl_seconds,
                global_stats
            )
        logger.info(f"[CONFIG]  {deleted}/{len(account_ids)} ")
        return multi_account_mgr, deleted, errors

    errors = []
    account_id_set = set(account_ids)

    accounts_data = load_accounts_from_source()
    kept: list[dict] = []
    deleted_ids: list[str] = []

    for i, acc in enumerate(accounts_data, 1):
        acc_id = get_account_id(acc, i)
        if acc_id in account_id_set:
            deleted_ids.append(acc_id)
            continue
        kept.append(acc)

    missing = account_id_set.difference(deleted_ids)
    for account_id in missing:
        errors.append(f"{account_id}: ")

    if deleted_ids:
        save_accounts_to_file(kept)
        multi_account_mgr = reload_accounts(
            multi_account_mgr,
            http_client,
            user_agent,
            retry_policy,
            session_cache_ttl_seconds,
            global_stats
        )

    success_count = len(deleted_ids)
    logger.info(f"[CONFIG]  {success_count}/{len(account_ids)} ")
    return multi_account_mgr, success_count, errors


async def save_account_cooldown_state(account_id: str, account_mgr: AccountManager) -> bool:
    """（：）"""
    if not storage.is_database_enabled():
        return False

    try:
        cooldown_data = {
            "quota_cooldowns": dict(account_mgr.quota_cooldowns),
            "conversation_count": account_mgr.conversation_count,
            "failure_count": account_mgr.failure_count,
        }

        success = await storage.update_account_cooldown(account_id, cooldown_data)
        if success:
            logger.debug(f"[COOLDOWN]  {account_id} ")
        else:
            logger.warning(f"[COOLDOWN]  {account_id} ")
        return success
    except Exception as e:
        logger.error(f"[COOLDOWN]  {account_id} : {e}")
        return False


def save_account_cooldown_state_sync(account_id: str, account_mgr: AccountManager) -> bool:
    """（）"""
    try:
        return asyncio.run(save_account_cooldown_state(account_id, account_mgr))
    except Exception as e:
        logger.error(f"[COOLDOWN]  {account_id} : {e}")
        return False


async def save_all_cooldown_states(multi_account_mgr: MultiAccountManager) -> int:
    """（：）"""
    if not storage.is_database_enabled():
        return 0

    # 
    updates = []
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        has_cooldown = (
            account_mgr.quota_cooldowns or
            account_mgr.conversation_count > 0 or
            account_mgr.failure_count > 0
        )

        if has_cooldown:
            cooldown_data = {
                "quota_cooldowns": dict(account_mgr.quota_cooldowns),
                "conversation_count": account_mgr.conversation_count,
                "failure_count": account_mgr.failure_count,
            }
            updates.append((account_id, cooldown_data))

    if not updates:
        logger.info(f"[COOLDOWN] ：")
        return 0

    success_count, missing = await storage.bulk_update_accounts_cooldown(updates)

    if missing:
        logger.warning(f"[COOLDOWN] {len(missing)} : {missing[:5]}")

    logger.info(f"[COOLDOWN] : {success_count}/{len(updates)} （ {len(multi_account_mgr.accounts) - len(updates)} ）")
    return success_count

