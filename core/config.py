"""
Sistem manajemen konfigurasi terpadu

Aturan prioritas:
1. Konfigurasi keamanan: hanya variabel environment（ADMIN_KEY, SESSION_SECRET_KEY）
2. Konfigurasi bisnis: database > nilai default

Klasifikasi konfigurasi:
- Konfigurasi keamanan: hanya baca dari environment variable, tidak bisa hot update（ADMIN_KEY, SESSION_SECRET_KEY）
- ：，（API_KEY, BASE_URL, PROXY, ）
"""

import os
import shutil
import yaml
import secrets
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

from core import storage

#  .env 
load_dotenv()

def _parse_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "y", "on"):
            return True
        if lowered in ("0", "false", "no", "n", "off"):
            return False
    return default


# ====================  ====================

class BasicConfig(BaseModel):
    """"""
    api_key: str = Field(default="", description="API（，）")
    base_url: str = Field(default="", description="URL（）")
    proxy_for_auth: str = Field(default="", description="（//，）")
    proxy_for_chat: str = Field(default="", description="（JWT//，）")
    browser_engine: str = Field(default="dp", description="：uc  dp")
    browser_headless: bool = Field(default=False, description="")
    refresh_window_hours: int = Field(default=1, ge=0, le=24, description="（）")
    register_default_count: int = Field(default=1, ge=1, description="")


class ImageGenerationConfig(BaseModel):
    """"""
    enabled: bool = Field(default=False, description="")
    supported_models: List[str] = Field(
        default=[],
        description=""
    )
    output_format: str = Field(default="base64", description="：base64  url")


class VideoGenerationConfig(BaseModel):
    """"""
    output_format: str = Field(default="html", description="：html/url/markdown")

    @validator("output_format")
    def validate_output_format(cls, v):
        allowed = ["html", "url", "markdown"]
        if v not in allowed:
            raise ValueError(f"output_format  {allowed} ")
        return v


class RetryConfig(BaseModel):
    """"""
    max_account_switch_tries: int = Field(default=5, ge=1, le=20, description="")
    rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=43200, description="429（）")
    text_rate_limit_cooldown_seconds: int = Field(default=7200, ge=3600, le=86400, description="（）")
    images_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400, description="（）")
    videos_rate_limit_cooldown_seconds: int = Field(default=14400, ge=3600, le=86400, description="（）")
    session_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400, description="（，0）")
    auto_refresh_accounts_seconds: int = Field(default=60, ge=0, le=600, description="（，0）")
    # 
    scheduled_refresh_enabled: bool = Field(default=False, description="")
    scheduled_refresh_interval_minutes: int = Field(default=30, ge=0, le=720, description="（，0-12）")

class PublicDisplayConfig(BaseModel):
    """"""
    logo_url: str = Field(default="", description="Logo URL")
    chat_url: str = Field(default="", description="")


class SessionConfig(BaseModel):
    """Session"""
    expire_hours: int = Field(default=24, ge=1, le=168, description="Session（）")


class SecurityConfig(BaseModel):
    """（，）"""
    admin_key: str = Field(default="", description="Kunci admin（）")
    session_secret_key: str = Field(..., description="Session")


class AppConfig(BaseModel):
    """（）"""
    # （）
    security: SecurityConfig

    # （ >  > ）
    basic: BasicConfig
    image_generation: ImageGenerationConfig
    video_generation: VideoGenerationConfig = Field(default_factory=VideoGenerationConfig)
    retry: RetryConfig
    public_display: PublicDisplayConfig
    session: SessionConfig


# ====================  ====================

class ConfigManager:
    """（）"""

    def __init__(self, yaml_path: str = None):
        # 
        if yaml_path is None:
            yaml_path = ""
        self.yaml_path = Path(yaml_path)
        self._config: Optional[AppConfig] = None
        self.load()

    def load(self):
        """
        

        Aturan prioritas:
        1. （ADMIN_KEY, SESSION_SECRET_KEY）：
        2. Konfigurasi bisnis: database > nilai default
        """
        # 1. 
        yaml_data = self._load_yaml()

        # 2. （， Web ）
        security_config = SecurityConfig(
            admin_key=os.getenv("ADMIN_KEY", ""),
            session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
        )

        # 3. （ > ）
        basic_data = yaml_data.get("basic", {})
        refresh_window_raw = basic_data.get("refresh_window_hours", 1)
        register_default_raw = basic_data.get("register_default_count", 1)

        # ： proxy ，
        old_proxy = basic_data.get("proxy", "")
        old_proxy_for_auth_bool = basic_data.get("proxy_for_auth")
        old_proxy_for_chat_bool = basic_data.get("proxy_for_chat")

        # ，
        proxy_for_auth = basic_data.get("proxy_for_auth", "")
        proxy_for_chat = basic_data.get("proxy_for_chat", "")

        # ，
        if not proxy_for_auth and old_proxy:
            #  proxy_for_auth  True， proxy
            if isinstance(old_proxy_for_auth_bool, bool) and old_proxy_for_auth_bool:
                proxy_for_auth = old_proxy

        if not proxy_for_chat and old_proxy:
            #  proxy_for_chat  True， proxy
            if isinstance(old_proxy_for_chat_bool, bool) and old_proxy_for_chat_bool:
                proxy_for_chat = old_proxy

        basic_config = BasicConfig(
            api_key=basic_data.get("api_key") or "",
            base_url=basic_data.get("base_url") or "",
            proxy_for_auth=str(proxy_for_auth or "").strip(),
            proxy_for_chat=str(proxy_for_chat or "").strip(),
            browser_engine=basic_data.get("browser_engine") or "dp",
            browser_headless=_parse_bool(basic_data.get("browser_headless"), False),
            refresh_window_hours=int(refresh_window_raw),
            register_default_count=int(register_default_raw),
        )

        # 4. （，）
        try:
            image_generation_config = ImageGenerationConfig(
                **yaml_data.get("image_generation", {})
            )
        except Exception as e:
            print(f"[WARN] ，: {e}")
            image_generation_config = ImageGenerationConfig()

        # 
        try:
            video_generation_config = VideoGenerationConfig(
                **yaml_data.get("video_generation", {})
            )
        except Exception as e:
            print(f"[WARN] ，: {e}")
            video_generation_config = VideoGenerationConfig()

        # （Pydantic ）
        try:
            retry_config = RetryConfig(**yaml_data.get("retry", {}))
        except Exception as e:
            print(f"[WARN] ，: {e}")
            retry_config = RetryConfig()

        try:
            public_display_config = PublicDisplayConfig(
                **yaml_data.get("public_display", {})
            )
        except Exception as e:
            print(f"[WARN] ，: {e}")
            public_display_config = PublicDisplayConfig()

        try:
            session_config = SessionConfig(
                **yaml_data.get("session", {})
            )
        except Exception as e:
            print(f"[WARN] Session，: {e}")
            session_config = SessionConfig()

        # 5. 
        self._config = AppConfig(
            security=security_config,
            basic=basic_config,
            image_generation=image_generation_config,
            video_generation=video_generation_config,
            retry=retry_config,
            public_display=public_display_config,
            session=session_config
        )

    def _load_yaml(self) -> dict:
        """（）。"""
        if storage.is_database_enabled():
            try:
                data = storage.load_settings_sync()

                # ：None 
                if data is None:
                    print("[WARN]  settings（），")
                    return {}

                if isinstance(data, dict):
                    return data

                return {}
            except RuntimeError:
                #  RuntimeError
                raise
            except Exception as e:
                print(f"[ERROR] : {e}")
                raise RuntimeError(f": {e}")

        print("[ERROR] ")
        raise RuntimeError(" DATABASE_URL，")

    def _generate_secret(self) -> str:
        """"""
        return secrets.token_urlsafe(32)

    def save_yaml(self, data: dict):
        """（）"""
        if not storage.is_database_enabled():
            raise RuntimeError("Database is not enabled")

        #  Pydantic 
        try:
            # 
            security_config = SecurityConfig(
                admin_key=os.getenv("ADMIN_KEY", ""),
                session_secret_key=os.getenv("SESSION_SECRET_KEY", self._generate_secret())
            )

            basic_data = data.get("basic", {})
            basic_config = BasicConfig(**basic_data)

            image_generation_config = ImageGenerationConfig(
                **data.get("image_generation", {})
            )

            video_generation_config = VideoGenerationConfig(
                **data.get("video_generation", {})
            )

            retry_config = RetryConfig(**data.get("retry", {}))

            public_display_config = PublicDisplayConfig(
                **data.get("public_display", {})
            )

            session_config = SessionConfig(
                **data.get("session", {})
            )

            # ，
            test_config = AppConfig(
                security=security_config,
                basic=basic_config,
                image_generation=image_generation_config,
                video_generation=video_generation_config,
                retry=retry_config,
                public_display=public_display_config,
                session=session_config
            )
        except Exception as e:
            # ，
            raise ValueError(f": {str(e)}")

        # 
        try:
            saved = storage.save_settings_sync(data)
            if saved:
                return
        except Exception as e:
            print(f"[WARN] : {e}")
        raise RuntimeError("Database write failed")

    def reload(self):
        """（）"""
        self.load()

    @property
    def config(self) -> AppConfig:
        """"""
        return self._config

    # ====================  ====================

    @property
    def api_key(self) -> str:
        """API"""
        return self._config.basic.api_key

    @property
    def admin_key(self) -> str:
        """Kunci admin"""
        return self._config.security.admin_key

    @property
    def session_secret_key(self) -> str:
        """Session"""
        return self._config.security.session_secret_key

    @property
    def proxy_for_auth(self) -> str:
        """"""
        return self._config.basic.proxy_for_auth

    @property
    def proxy_for_chat(self) -> str:
        """"""
        return self._config.basic.proxy_for_chat

    @property
    def base_url(self) -> str:
        """URL"""
        return self._config.basic.base_url

    @property
    def logo_url(self) -> str:
        """Logo URL"""
        return self._config.public_display.logo_url

    @property
    def chat_url(self) -> str:
        """"""
        return self._config.public_display.chat_url

    @property
    def image_generation_enabled(self) -> bool:
        """"""
        return self._config.image_generation.enabled

    @property
    def image_generation_models(self) -> List[str]:
        """"""
        return self._config.image_generation.supported_models

    @property
    def image_output_format(self) -> str:
        """"""
        return self._config.image_generation.output_format

    @property
    def video_output_format(self) -> str:
        """"""
        return self._config.video_generation.output_format

    @property
    def session_expire_hours(self) -> int:
        """Session（）"""
        return self._config.session.expire_hours

    @property
    def max_account_switch_tries(self) -> int:
        """"""
        return self._config.retry.max_account_switch_tries

    @property
    def rate_limit_cooldown_seconds(self) -> int:
        # 429 cooldown (seconds)
        if hasattr(self._config.retry, 'text_rate_limit_cooldown_seconds'):
            return self._config.retry.text_rate_limit_cooldown_seconds
        return self._config.retry.rate_limit_cooldown_seconds

    @property
    def text_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.text_rate_limit_cooldown_seconds

    @property
    def images_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.images_rate_limit_cooldown_seconds

    @property
    def videos_rate_limit_cooldown_seconds(self) -> int:
        return self._config.retry.videos_rate_limit_cooldown_seconds

    @property
    def session_cache_ttl_seconds(self) -> int:
        # Session cache TTL (seconds)
        return self._config.retry.session_cache_ttl_seconds

    @property
    def auto_refresh_accounts_seconds(self) -> int:
        # Auto refresh accounts interval (seconds)
        return self._config.retry.auto_refresh_accounts_seconds


# ====================  ====================

config_manager = ConfigManager()

# ： config_manager.config， reload() 
#  config_manager.config 
def get_config() -> AppConfig:
    """（）"""
    return config_manager.config

# ， config ，
class _ConfigProxy:
    """，"""
    @property
    def basic(self):
        return config_manager.config.basic

    @property
    def security(self):
        return config_manager.config.security

    @property
    def image_generation(self):
        return config_manager.config.image_generation

    @property
    def video_generation(self):
        return config_manager.config.video_generation

    @property
    def retry(self):
        return config_manager.config.retry

    @property
    def public_display(self):
        return config_manager.config.public_display

    @property
    def session(self):
        return config_manager.config.session

config = _ConfigProxy()
