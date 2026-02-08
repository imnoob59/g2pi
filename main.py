import json, time, os, asyncio, uuid, ssl, re, yaml, base64
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Union, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
import logging
from dotenv import load_dotenv

import httpx
import aiofiles
from fastapi import FastAPI, HTTPException, Header, Request, Body, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from util.streaming_parser import parse_json_array_stream_async
from collections import deque
from threading import Lock
from core.database import stats_db

# ---------- Konfigurasi Direktori Data ----------
DATA_DIR = "./data"
logger_prefix = "[LOCAL]"

# Pastikan direktori data ada
os.makedirs(DATA_DIR, exist_ok=True)

# Path file data terpusat
TASK_HISTORY_MTIME: float = 0.0
IMAGE_DIR = os.path.join(DATA_DIR, "images")
VIDEO_DIR = os.path.join(DATA_DIR, "videos")

# Pastikan direktori gambar dan video ada
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

# Import modul autentikasi
from core.auth import verify_api_key
from core.session_auth import is_logged_in, login_user, logout_user, require_login, generate_session_secret

# Import modul inti
from core.message import (
    get_conversation_key,
    parse_last_message,
    build_full_context_text
)
from core.google_api import (
    get_common_headers,
    create_google_session,
    upload_context_file,
    get_session_file_metadata,
    download_image_with_jwt,
    save_image_to_hf
)
from core.account import (
    AccountManager,
    MultiAccountManager,
    RetryPolicy,
    CooldownConfig,
    format_account_expiration,
    load_multi_account_config,
    load_accounts_from_source,
    reload_accounts as _reload_accounts,
    update_accounts_config as _update_accounts_config,
    delete_account as _delete_account,
    update_account_disabled_status as _update_account_disabled_status,
    bulk_update_account_disabled_status as _bulk_update_account_disabled_status,
    bulk_delete_accounts as _bulk_delete_accounts
)
from core.proxy_utils import parse_proxy_setting

# Import Uptime tracker
from core import uptime as uptime_tracker

# Import manajemen konfigurasi dan sistem template
from core.config import config_manager, config

# Dukungan database storage
from core import storage, account

# Mapping model ke tipe kuota
MODEL_TO_QUOTA_TYPE = {
    "gemini-imagen": "images",
    "gemini-veo": "videos"
}

# ---------- Konfigurasi Logging ----------

# Buffer log memori (simpan 1000 log terakhir, hapus setelah restart)
log_buffer = deque(maxlen=1000)
log_lock = Lock()

# Persistensi data statistik
stats_lock = asyncio.Lock()  # Async lock

async def load_stats():
    """Load data statistik (async). Gunakan default memori jika database tidak tersedia."""
    data = None
    if storage.is_database_enabled():
        try:
            has_stats = await asyncio.to_thread(storage.has_stats_sync)
            if has_stats:
                data = await asyncio.to_thread(storage.load_stats_sync)
                if not isinstance(data, dict):
                    data = None
        except Exception as e:
            logger.error(f"[STATS] Gagal load database: {str(e)[:50]}")

    if data is None:
        data = {
            "total_visitors": 0,
            "total_requests": 0,
            "success_count": 0,
            "failed_count": 0,
            "request_timestamps": [],
            "model_request_timestamps": {},
            "failure_timestamps": [],
            "rate_limit_timestamps": [],
            "visitor_ips": {},
            "account_conversations": {},
            "account_failures": {},
            "recent_conversations": []
        }

    if isinstance(data.get("request_timestamps"), list):
        data["request_timestamps"] = deque(data["request_timestamps"], maxlen=20000)
    if isinstance(data.get("failure_timestamps"), list):
        data["failure_timestamps"] = deque(data["failure_timestamps"], maxlen=10000)
    if isinstance(data.get("rate_limit_timestamps"), list):
        data["rate_limit_timestamps"] = deque(data["rate_limit_timestamps"], maxlen=10000)

    return data

async def save_stats(stats):
    """Simpan data statistik (async). Tidak simpan ke disk jika database tidak tersedia."""
    def convert_deques(obj):
        """Konversi rekursif semua objek deque ke list"""
        if isinstance(obj, deque):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_deques(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_deques(item) for item in obj]
        return obj

    stats_to_save = convert_deques(stats)

    if storage.is_database_enabled():
        try:
            saved = await asyncio.to_thread(storage.save_stats_sync, stats_to_save)
            if saved:
                return
        except Exception as e:
            logger.error(f"[STATS] Gagal simpan ke database: {str(e)[:50]}")
    return

# Inisialisasi data statistik (perlu async load saat startup)
global_stats = {
    "total_visitors": 0,
    "total_requests": 0,
    "success_count": 0,
    "failed_count": 0,
    "request_timestamps": deque(maxlen=20000),
    "model_request_timestamps": {},
    "failure_timestamps": deque(maxlen=10000),
    "rate_limit_timestamps": deque(maxlen=10000),
    "visitor_ips": {},
    "account_conversations": {},
    "account_failures": {},
    "recent_conversations": []
}

# Riwayat task (storage memori, hapus setelah restart)
task_history = deque(maxlen=100)  # Maksimal 100 history
task_history_lock = Lock()


def get_beijing_time_str(ts: Optional[float] = None) -> str:
    tz = timezone(timedelta(hours=8))
    current = datetime.fromtimestamp(ts or time.time(), tz=tz)
    return current.strftime("%Y-%m-%d %H:%M:%S")


def save_task_to_history(task_type: str, task_data: dict) -> None:
    """Simpan riwayat task (hanya info ringkas)"""
    with task_history_lock:
        history_entry = _build_history_entry(task_type, task_data)
        entry_id = history_entry.get("id")
        if entry_id:
            for i in range(len(task_history) - 1, -1, -1):
                if task_history[i].get("id") == entry_id:
                    task_history.remove(task_history[i])
                    break
        task_history.append(history_entry)
        _persist_task_history()
        logger.info(f"[HISTORY] Saved {task_type} task to history: {history_entry['id']}")


def _build_history_entry(task_type: str, task_data: dict, is_live: bool = False) -> dict:
    total_value = task_data.get("count") if task_type == "register" else len(task_data.get("account_ids", []))
    return {
        "id": task_data.get("id", ""),
        "type": task_type,  # "register" or "login"
        "status": task_data.get("status", ""),
        "progress": task_data.get("progress", 0),
        "total": total_value,
        "success_count": task_data.get("success_count", 0),
        "fail_count": task_data.get("fail_count", 0),
        "created_at": task_data.get("created_at", time.time()),
        "finished_at": task_data.get("finished_at"),
        "is_live": is_live,
    }


def _persist_task_history() -> None:
    """Persist riwayat task ke database (mode database saja)."""
    if not storage.is_database_enabled():
        return
    try:
        if not task_history:
            storage.clear_task_history_sync()
            return
        storage.save_task_history_entry_sync(task_history[-1])
    except Exception as exc:
        logger.warning(f"[HISTORY] Persist task history failed: {exc}")


def _load_task_history() -> None:
    """Load riwayat task dari database (mode database saja)."""
    if not storage.is_database_enabled():
        return
    try:
        history = storage.load_task_history_sync(limit=100)
        if not isinstance(history, list):
            return
        with task_history_lock:
            task_history.clear()
            for entry in history:
                if isinstance(entry, dict):
                    task_history.append(entry)
    except Exception as exc:
        logger.warning(f"[HISTORY] Load task history failed: {exc}")


def build_recent_conversation_entry(
    request_id: str,
    model: Optional[str],
    message_count: Optional[int],
    start_ts: float,
    status: str,
    duration_s: Optional[float] = None,
    error_detail: Optional[str] = None,
) -> dict:
    start_time = get_beijing_time_str(start_ts)
    if model:
        start_content = f"{model}"
        if message_count:
            start_content = f"{model} | {message_count} pesan"
    else:
        start_content = "Memproses request"

    events = [{
        "time": start_time,
        "type": "start",
        "content": start_content,
    }]

    end_time = get_beijing_time_str(start_ts + duration_s) if duration_s is not None else get_beijing_time_str()

    if status == "success":
        if duration_s is not None:
            events.append({
                "time": end_time,
                "type": "complete",
                "status": "success",
            "content": f"Respons selesai | {duration_s:.2f}s",
            })
        else:
            events.append({
                "time": end_time,
                "type": "complete",
                "status": "success",
            "content": "Respons selesai",
            })
    elif status == "timeout":
        events.append({
            "time": end_time,
            "type": "complete",
            "status": "timeout",
            "content": "Request timeout",
        })
    else:
        detail = error_detail or "Request gagal"
        events.append({
            "time": end_time,
            "type": "complete",
            "status": "error",
            "content": detail[:120],
        })

    return {
        "request_id": request_id,
        "start_time": start_time,
        "start_ts": start_ts,
        "status": status,
        "events": events,
    }

class MemoryLogHandler(logging.Handler):
    """Custom log handler, tulis log ke buffer memori"""
    def emit(self, record):
        log_entry = self.format(record)
        # Konversi ke waktu Jakarta (UTC+7)
        beijing_tz = timezone(timedelta(hours=8))
        beijing_time = datetime.fromtimestamp(record.created, tz=beijing_tz)
        with log_lock:
            log_buffer.append({
                "time": beijing_time.strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "message": record.getMessage()
            })

# Konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gemini")

_load_task_history()

# ---------- Linux zombie process reaper ----------
# DrissionPage / Chromium may spawn subprocesses that exit without being waited on,
# which can accumulate as zombies (<defunct>) in long-running services.
try:
    from core.child_reaper import install_child_reaper

    install_child_reaper(log=lambda m: logger.warning(m))
except Exception:
    # Never fail startup due to optional process reaper.
    pass

# Tambahkan memory log handler
memory_handler = MemoryLogHandler()
memory_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(memory_handler)

# ---------- Manajemen Konfigurasi (Sistem Konfigurasi Terpusat)----------
# Semua konfigurasi diakses via config_manager, prioritas: ENV > YAML > Default
TIMEOUT_SECONDS = 600
API_KEY = config.basic.api_key
ADMIN_KEY = config.security.admin_key
_proxy_auth, _no_proxy_auth = parse_proxy_setting(config.basic.proxy_for_auth)
_proxy_chat, _no_proxy_chat = parse_proxy_setting(config.basic.proxy_for_chat)
PROXY_FOR_AUTH = _proxy_auth
PROXY_FOR_CHAT = _proxy_chat
_NO_PROXY = ",".join(filter(None, {_no_proxy_auth, _no_proxy_chat}))
if _NO_PROXY:
    os.environ["NO_PROXY"] = _NO_PROXY
BASE_URL = config.basic.base_url
SESSION_SECRET_KEY = config.security.session_secret_key
SESSION_EXPIRE_HOURS = config.session.expire_hours

# ---------- Konfigurasi Tampilan Publik ----------
LOGO_URL = config.public_display.logo_url
CHAT_URL = config.public_display.chat_url

# ---------- Konfigurasi Generasi Gambar ----------
IMAGE_GENERATION_ENABLED = config.image_generation.enabled
IMAGE_GENERATION_MODELS = config.image_generation.supported_models

def get_request_quota_type(model_name: str) -> str:
    """Kembalikan tipe kuota untuk request berdasarkan nama model."""
    if model_name in MODEL_TO_QUOTA_TYPE:
        return MODEL_TO_QUOTA_TYPE[model_name]
    if IMAGE_GENERATION_ENABLED and model_name in IMAGE_GENERATION_MODELS:
        return "images"
    return "text"

def get_required_quota_types(model_name: str) -> List[str]:
    """Semua request perlu kuota text; request gambar/video juga perlu kuota yang sesuai."""
    required = ["text"]
    request_quota = get_request_quota_type(model_name)
    if request_quota != "text":
        required.append(request_quota)
    return required

# ---------- Mapping Model Virtual ----------
VIRTUAL_MODELS = {
    "gemini-imagen": {"imageGenerationSpec": {}},
    "gemini-veo": {"videoGenerationSpec": {}},
}

def get_tools_spec(model_name: str) -> dict:
    """Kembalikan konfigurasi tool berdasarkan nama model"""
    # Model virtual
    if model_name in VIRTUAL_MODELS:
        return VIRTUAL_MODELS[model_name]
    
    # Model biasa
    tools_spec = {
        "webGroundingSpec": {},
        "toolRegistry": "default_tool_registry",
    }
    
    if IMAGE_GENERATION_ENABLED and model_name in IMAGE_GENERATION_MODELS:
        tools_spec["imageGenerationSpec"] = {}
    
    return tools_spec


# ---------- Konfigurasi Retry ----------
MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds

def build_retry_policy() -> RetryPolicy:
    return RetryPolicy(
        cooldowns=CooldownConfig(
            text=config.retry.text_rate_limit_cooldown_seconds,
            images=config.retry.images_rate_limit_cooldown_seconds,
            videos=config.retry.videos_rate_limit_cooldown_seconds,
        ),
    )

RETRY_POLICY = build_retry_policy()

# ---------- Konfigurasi Mapping Model ----------
MODEL_MAPPING = {
    "gemini-auto": None,
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
    "gemini-3-flash-preview": "gemini-3-flash-preview",
    "gemini-3-pro-preview": "gemini-3-pro-preview"
}

# ---------- HTTP Client ----------
# Client untuk operasi chat (dapatkan JWT, buat session, kirim pesan)
http_client = httpx.AsyncClient(
    proxy=(PROXY_FOR_CHAT or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

# Client untuk streaming chat responses
http_client_chat = httpx.AsyncClient(
    proxy=(PROXY_FOR_CHAT or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

# Client untuk operasi akun (registrasi/login/refresh)
http_client_auth = httpx.AsyncClient(
    proxy=(PROXY_FOR_AUTH or None),
    verify=False,
    http2=False,
    timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
    limits=httpx.Limits(
        max_keepalive_connections=100,
        max_connections=200
    )
)

# Print proxyKonfigurasi logging
logger.info(f"[PROXY] Account operations (register/login/refresh): {PROXY_FOR_AUTH if PROXY_FOR_AUTH else 'disabled'}")
logger.info(f"[PROXY] Chat operations (JWT/session/messages): {PROXY_FOR_CHAT if PROXY_FOR_CHAT else 'disabled'}")

# ---------- Fungsi Utility ----------
def get_base_url(request: Request) -> str:
    """Dapatkan base URL lengkap (prioritas ENV, atau auto-detect dari request)"""
    # Prioritas gunakan environment variable
    if BASE_URL:
        return BASE_URL.rstrip("/")

    # Auto-detect dari request (kompatibel dengan reverse proxy)
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    forwarded_host = request.headers.get("x-forwarded-host", request.headers.get("host"))

    return f"{forwarded_proto}://{forwarded_host}"



# ---------- Definisi Konstanta ----------
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# ---------- Dukungan Multi-Account ----------
# (AccountConfig, AccountManager, MultiAccountManager sudah dipindah ke core/account.py)

# ---------- Manajemen File Konfigurasi ----------
# (konfigurasiManajemenfungsisudah dipindah ke core/account.py)

# Inisialisasi multi-account manager
multi_account_mgr = load_multi_account_config(
    http_client,
    USER_AGENT,
    RETRY_POLICY,
    SESSION_CACHE_TTL_SECONDS,
    global_stats
)

# ---------- Service Auto-Registrasi/Refresh ----------
register_service = None
login_service = None

def _set_multi_account_mgr(new_mgr):
    global multi_account_mgr
    multi_account_mgr = new_mgr
    if register_service:
        register_service.multi_account_mgr = new_mgr
    if login_service:
        login_service.multi_account_mgr = new_mgr

def _get_global_stats():
    return global_stats

try:
    from core.register_service import RegisterService
    from core.login_service import LoginService
    register_service = RegisterService(
        multi_account_mgr,
        http_client_auth,
        USER_AGENT,
        RETRY_POLICY,
        SESSION_CACHE_TTL_SECONDS,
        _get_global_stats,
        _set_multi_account_mgr,
    )
    login_service = LoginService(
        multi_account_mgr,
        http_client_auth,
        USER_AGENT,
        RETRY_POLICY,
        SESSION_CACHE_TTL_SECONDS,
        _get_global_stats,
        _set_multi_account_mgr,
    )
except Exception as e:
    logger.warning("[SYSTEM] Service Auto-Registrasi/Refreshtidak tersedia: %s", e)
    register_service = None
    login_service = None

# Validasi environment variable yang diperlukan
if not ADMIN_KEY:
    logger.error("[SYSTEM] belum dikonfigurasi ADMIN_KEY Environment variable，Silakan set lalu restart")
    import sys
    sys.exit(1)

# Log startup
logger.info("[SYSTEM] APIendpoint: /v1/chat/completions")
logger.info("[SYSTEM] Admin API endpoints: /admin/*")
logger.info("[SYSTEM] Public endpoints: /public/log, /public/stats, /public/uptime")
logger.info(f"[SYSTEM] Sessionwaktu expired: {SESSION_EXPIRE_HOURS}jam")
logger.info("[SYSTEM] Inisialisasi sistem selesai")

# ---------- JWT Manajemen ----------
# (JWTManagersudah dipindah ke core/jwt.py)

# ---------- Session & File Manajemen ----------
# (Google APIfungsisudah dipindah ke core/google_api.py)

# ---------- Logika pemrosesan pesan ----------
# (pesanprosesfungsisudah dipindah ke core/message.py)

# ---------- fungsi proses media ----------
def process_image(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """Proses gambar：Return berdasarkan konfigurasi base64 atau URL"""
    output_format = config_manager.image_output_format

    if output_format == "base64":
        b64 = base64.b64encode(data).decode()
        logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] gambar{idx}sudah di-encode base64")
        return f"\n\n![yang dihasilkangambar](data:{mime};base64,{b64})\n\n"
    else:
        url = save_image_to_hf(data, chat_id, file_id, mime, base_url, IMAGE_DIR)
        logger.info(f"[IMAGE] [{account_id}] [req_{request_id}] gambar{idx}sudahSimpan: {url}")
        return f"\n\n![yang dihasilkangambar]({url})\n\n"

def process_video(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """prosesvideo：Return berdasarkan konfigurasiformat"""
    url = save_image_to_hf(data, chat_id, file_id, mime, base_url, VIDEO_DIR, "videos")
    logger.info(f"[VIDEO] [{account_id}] [req_{request_id}] video{idx}sudahSimpan: {url}")

    output_format = config_manager.video_output_format

    if output_format == "html":
        return f'\n\n<video controls width="100%" style="max-width: 640px;"><source src="{url}" type="{mime}">Browser Anda tidak mendukung pemutaran video</video>\n\n'
    elif output_format == "markdown":
        return f"\n\n![yang dihasilkanvideo]({url})\n\n"
    else:  # url
        return f"\n\n{url}\n\n"

def process_media(data: bytes, mime: str, chat_id: str, file_id: str, base_url: str, idx: int, request_id: str, account_id: str) -> str:
    """satumediaprosespintu masuk： MIME proses"""
    logger.info(f"[MEDIA] [{account_id}] [req_{request_id}] prosesmedia{idx}: MIME={mime}")
    if mime.startswith("video/"):
        return process_video(data, mime, chat_id, file_id, base_url, idx, request_id, account_id)
    else:
        return process_image(data, mime, chat_id, file_id, base_url, idx, request_id, account_id)

# ---------- Lifespan Event Handler ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handler untuk startup dan shutdown event"""
    global global_stats
    
    # STARTUP
    # Loading statistik
    global_stats = await load_stats()
    global_stats.setdefault("request_timestamps", [])
    global_stats.setdefault("model_request_timestamps", {})
    global_stats.setdefault("failure_timestamps", [])
    global_stats.setdefault("rate_limit_timestamps", [])
    global_stats.setdefault("recent_conversations", [])
    global_stats.setdefault("success_count", 0)
    global_stats.setdefault("failed_count", 0)
    global_stats.setdefault("account_conversations", {})
    global_stats.setdefault("account_failures", {})
    uptime_tracker.configure_storage(os.path.join(DATA_DIR, "uptime.json"))
    uptime_tracker.load_heartbeats()
    for account_id, account_mgr in multi_account_mgr.accounts.items():
        account_mgr.conversation_count = global_stats["account_conversations"].get(account_id, 0)
        account_mgr.failure_count = global_stats["account_failures"].get(account_id, 0)
    logger.info("[SYSTEM] Statistik akun berhasil dipulihkan")
    logger.info(f"[SYSTEM] Data statistik loaded: {global_stats['total_requests']} request, {global_stats['total_visitors']} visitor")

    # Background tasks
    asyncio.create_task(multi_account_mgr.start_background_cleanup())
    logger.info("[SYSTEM] Task pembersihan cache dimulai (interval: 5 menit)")

    asyncio.create_task(cleanup_database_task())
    logger.info("[SYSTEM] Task pembersihan database dimulai (harian, simpan 30 hari)")

    if os.environ.get("ACCOUNTS_CONFIG"):
        logger.info("[SYSTEM] Auto-refresh akun dilewati (menggunakan ACCOUNTS_CONFIG)")
    elif storage.is_database_enabled() and AUTO_REFRESH_ACCOUNTS_SECONDS > 0:
        asyncio.create_task(auto_refresh_accounts_task())
        logger.info(f"[SYSTEM] Task auto-refresh akun dimulai (interval: {AUTO_REFRESH_ACCOUNTS_SECONDS} detik)")
    elif storage.is_database_enabled():
        logger.info("[SYSTEM] Auto-refresh akun dinonaktifkan (config = 0)")

    if login_service:
        try:
            asyncio.create_task(login_service.start_polling())
            logger.info("[SYSTEM] Layanan polling refresh akun dimulai (default nonaktif, bisa diaktifkan di settings)")
        except Exception as e:
            logger.error(f"[SYSTEM] Gagal memulai login service: {e}")
    else:
        logger.info("[SYSTEM] Auto-login refresh tidak aktif atau dependensi tidak tersedia")

    if storage.is_database_enabled():
        asyncio.create_task(save_cooldown_states_task())
        logger.info("[SYSTEM] Task simpan cooldown dimulai (interval: 5 menit)")
    
    yield  # Aplikasi berjalan
    
    # SHUTDOWN
    if storage.is_database_enabled():
        try:
            success_count = await account.save_all_cooldown_states(multi_account_mgr)
            logger.info(f"[SYSTEM] Aplikasi ditutup, berhasil menyimpan {success_count}/{len(multi_account_mgr.accounts)} status cooldown akun")
        except Exception as e:
            logger.error(f"[SYSTEM] Gagal menyimpan cooldown saat shutdown: {e}")

# ---------- OpenAI kompatibel API ----------
app = FastAPI(title="Gemini-Business OpenAI Gateway", lifespan=lifespan)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
allow_all_origins = os.getenv("ALLOW_ALL_ORIGINS", "0") == "1"
if allow_all_origins and not frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif frontend_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Static files untuk web frontend dihapus (desktop-only mode)
# Images dan videos mount ada di bawah setelah direktori dibuat

@app.get("/admin/health")
async def health_check():
    """endpoint health check untuk Docker HEALTHCHECK"""
    return {"status": "ok"}

# ---------- Session middlewarekonfigurasi ----------
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    max_age=SESSION_EXPIRE_HOURS * 3600,  # konversi kedetik
    same_site="lax",
    https_only=False  # dev lokal boleh False, produksi disarankan True
)

# ---------- Uptime middleware pelacakan ----------
@app.middleware("http")
async def track_uptime_middleware(request: Request, call_next):
    """Uptime ：permintaanhasil。"""
    path = request.url.path
    if (
        path.startswith("/images/")
        or path.startswith("/public/")
        or path.startswith("/favicon")
        or path.endswith("/v1/chat/completions")
    ):
        return await call_next(request)

    start_time = time.time()

    try:
        response = await call_next(request)
        latency_ms = int((time.time() - start_time) * 1000)
        success = response.status_code < 400
        uptime_tracker.record_request("api_service", success, latency_ms, response.status_code)
        return response

    except Exception:
        uptime_tracker.record_request("api_service", False)
        raise


# ---------- inisialisasi layanan statis gambar dan video ----------
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGE_DIR), name="images")
app.mount("/videos", StaticFiles(directory=VIDEO_DIR), name="videos")
logger.info(f"[SYSTEM] gambarlayanan statis aktif: /images/ -> {IMAGE_DIR}")
logger.info(f"[SYSTEM] videolayanan statis aktif: /videos/ -> {VIDEO_DIR}")

# ---------- tugas background dimulai ----------

# variabel global：catatkalicekakunperbaruiwaktu（untukotomatisRefreshcek）
_last_known_accounts_version: float | None = None


async def auto_refresh_accounts_task():
    """tugas：berkalacekdatabasediakunperubahan，otomatisRefresh"""
    global multi_account_mgr, _last_known_accounts_version

    # Inisialisasi：catatakun saat iniperbaruiwaktu
    if storage.is_database_enabled() and not os.environ.get("ACCOUNTS_CONFIG"):
        _last_known_accounts_version = await asyncio.to_thread(
            storage.get_accounts_updated_at_sync
        )

    while True:
        try:
            # ambilkonfigurasiRefreshinterval（perbarui）
            refresh_interval = config_manager.auto_refresh_accounts_seconds
            if refresh_interval <= 0:
                # otomatisRefreshDisabled，satuwaktucekkonfigurasi
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(refresh_interval)

            # Environment variabletidak adaotomatisRefresh
            if os.environ.get("ACCOUNTS_CONFIG"):
                continue

            # cekdatabaseaktif
            if not storage.is_database_enabled():
                continue

            # ambildatabasediakunperbaruiwaktu
            db_version = await asyncio.to_thread(storage.get_accounts_updated_at_sync)
            if db_version is None:
                continue

            # perbaruiwaktuperubahan
            if _last_known_accounts_version != db_version:
                logger.info("[AUTO-REFRESH] cekakunperubahan，sedangotomatisRefresh...")

                # ulangLoadingakunkonfigurasi
                multi_account_mgr = _reload_accounts(
                    multi_account_mgr,
                    http_client,
                    USER_AGENT,
                    RETRY_POLICY,
                    SESSION_CACHE_TTL_SECONDS,
                    global_stats
                )

                _last_known_accounts_version = db_version
                logger.info(f"[AUTO-REFRESH] akunRefreshSelesai，akun saat inijumlah: {len(multi_account_mgr.accounts)}")

        except asyncio.CancelledError:
            logger.info("[AUTO-REFRESH] otomatisRefreshtugasStopped")
            break
        except Exception as e:
            logger.error(f"[AUTO-REFRESH] otomatisRefreshtugasError: {type(e).__name__}: {str(e)[:100]}")
            await asyncio.sleep(60)  # 60detikRetry


async def save_cooldown_states_task():
    """berkalaSimpanakuncooldownstatusdatabase"""
    while True:
        try:
            await asyncio.sleep(300)  # setiap5menitjalankan satukali
            success_count = await account.save_all_cooldown_states(multi_account_mgr)
            logger.debug(f"[COOLDOWN] berkalaSimpan: {success_count}/{len(multi_account_mgr.accounts)} akun")
        except Exception as e:
            logger.error(f"[COOLDOWN] berkalaGagal simpan: {e}")


async def cleanup_database_task():
    """bersihkandatabasekedaluwarsajumlah"""
    while True:
        try:
            await asyncio.sleep(24 * 3600)  # setiapharijalankan satukali
            deleted_count = await stats_db.cleanup_old_data(days=30)
            logger.info(f"[DATABASE] bersihkan {deleted_count} kedaluwarsajumlah（30hari）")
        except Exception as e:
            logger.error(f"[DATABASE] bersihkanjumlahGagal: {e}")

# ---------- loganonimfungsi ----------
def get_sanitized_logs(limit: int = 100) -> list:
    """ambilanonimlogdaftar，sesuai permintaanIDekstrakkuncievent"""
    with log_lock:
        logs = list(log_buffer)

    # sesuai permintaanID（format：[req_xxx]dan）
    request_logs = {}
    orphan_logs = []  # tidak adarequest_idlog（misalnya pilih akun）

    for log in logs:
        message = log["message"]
        req_match = re.search(r'\[req_([a-z0-9]+)\]', message)

        if req_match:
            request_id = req_match.group(1)
            if request_id not in request_logs:
                request_logs[request_id] = []
            request_logs[request_id].append(log)
        else:
            # tidak adarequest_idlog（misalnya pilih akun），
            orphan_logs.append(log)

    # akanorphan_logs（misalnya pilih akun）permintaan
    # ：akanorphanlogwaktupermintaan
    for orphan in orphan_logs:
        orphan_time = orphan["time"]
        # waktudiorphanpermintaan
        closest_request_id = None
        min_time_diff = None

        for request_id, req_logs in request_logs.items():
            if req_logs:
                first_log_time = req_logs[0]["time"]
                # orphandipermintaanatau
                if first_log_time >= orphan_time:
                    if min_time_diff is None or first_log_time < min_time_diff:
                        min_time_diff = first_log_time
                        closest_request_id = request_id

        # permintaan，akanorphanlogpermintaanlogdaftar
        if closest_request_id:
            request_logs[closest_request_id].insert(0, orphan)

    # setiappermintaanekstrakkuncievent
    sanitized = []
    for request_id, req_logs in request_logs.items():
        # kunciInfo
        model = None
        message_count = None
        retry_events = []
        final_status = "in_progress"
        duration = None
        start_time = req_logs[0]["time"]

        # permintaanlog
        for log in req_logs:
            message = log["message"]

            # ekstrakmodelnamadanpesanjumlah（mulai percakapan）
            if 'menerima permintaan:' in message and not model:
                model_match = re.search(r'menerima permintaan: ([^ |]+)', message)
                if model_match:
                    model = model_match.group(1)
                count_match = re.search(r'(\d+) pesan', message)
                if count_match:
                    message_count = int(count_match.group(1))

            # ekstrakRetryevent（Gagalcoba、peralihan akun、pilih akun）
            # ：ekstrak"sedangRetry"log，dan"Gagal (coba"
            if any(keyword in message for keyword in ['alih akun', 'pilih akun', 'Gagal (coba']):
                retry_events.append({
                    "time": log["time"],
                    "message": message
                })

            # ekstrakRespons selesai（ - BerhasildiError）
            if 'Respons selesai:' in message:
                time_match = re.search(r'Respons selesai: ([\d.]+)detik', message)
                if time_match:
                    duration = time_match.group(1) + 's'
                    final_status = "success"

            # ceknon-streamRespons selesai
            if 'non-streamRespons selesai' in message:
                final_status = "success"

            # cekGagalstatus（hanya saat nonsuccessdalam status）
            if final_status != "success" and (log['level'] == 'ERROR' or 'Gagal' in message):
                final_status = "error"

            # cekTimeout（hanya saat nonsuccessdalam status）
            if final_status != "success" and 'Timeout' in message:
                final_status = "timeout"

        # tidak adamodelInfonamun adaError，
        if not model and final_status == "in_progress":
            continue

        # bangunkuncieventdaftar
        events = []

        # 1. mulai percakapan
        if model:
            events.append({
                "time": start_time,
                "type": "start",
                "content": f"{model} | {message_count} pesan" if message_count else model
            })
        else:
            # tidak adamodelInfonamun adaError
            events.append({
                "time": start_time,
                "type": "start",
                "content": "Memproses request"
            })

        # 2. Retryevent
        failure_count = 0  # GagalRetryjumlah
        account_select_count = 0  # akunpilihjumlah

        for i, retry in enumerate(retry_events):
            msg = retry["message"]

            # Retryevent（）
            if 'Gagal (coba' in msg:
                # buat sesiGagal
                failure_count += 1
                events.append({
                    "time": retry["time"],
                    "type": "retry",
                    "content": f"layananError，sedangRetry（{failure_count}）"
                })
            elif 'pilih akun' in msg:
                # akunpilih/
                account_select_count += 1

                # ceksatulog"alih akun"，Skipsaat ini"pilih akun"（）
                next_is_switch = (i + 1 < len(retry_events) and 'alih akun' in retry_events[i + 1]["message"])

                if not next_is_switch:
                    if account_select_count == 1:
                        # pertamakalipilih：ditampilkan sebagai"pilih node layanan"
                        events.append({
                            "time": retry["time"],
                            "type": "select",
                            "content": "pilih node layanan"
                        })
                    else:
                        # kali：ditampilkan sebagai"alih node layanan"
                        events.append({
                            "time": retry["time"],
                            "type": "switch",
                            "content": "alih node layanan"
                        })
            elif 'alih akun' in msg:
                # runtimealih akun（ditampilkan sebagai"alih node layanan"）
                events.append({
                    "time": retry["time"],
                    "type": "switch",
                    "content": "alih node layanan"
                })

        # 3. Selesaievent
        if final_status == "success":
            if duration:
                events.append({
                    "time": req_logs[-1]["time"],
                    "type": "complete",
                    "status": "success",
                    "content": f"Respons selesai | {duration}"
                })
            else:
                events.append({
                    "time": req_logs[-1]["time"],
                    "type": "complete",
                    "status": "success",
                    "content": "Respons selesai"
                })
        elif final_status == "error":
            events.append({
                "time": req_logs[-1]["time"],
                "type": "complete",
                "status": "error",
                "content": "Request gagal"
            })
        elif final_status == "timeout":
            events.append({
                "time": req_logs[-1]["time"],
                "type": "complete",
                "status": "timeout",
                "content": "Request timeout"
            })

        sanitized.append({
            "request_id": request_id,
            "start_time": start_time,
            "status": final_status,
            "events": events
        })

    # waktubatasjumlah
    sanitized.sort(key=lambda x: x["start_time"], reverse=True)
    return sanitized[:limit]

class Message(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]

class ChatRequest(BaseModel):
    model: str = "gemini-auto"
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0

class ImageGenerationRequest(BaseModel):
    """OpenAI /v1/images/generations permintaanformat"""
    prompt: str
    model: str = "gemini-imagen"
    n: Optional[int] = 1
    size: Optional[str] = "1024x1024"
    response_format: Optional[str] = None  # "url" or "b64_json"，None sistemkonfigurasi
    quality: Optional[str] = "standard"  # "standard" or "hd"
    style: Optional[str] = "natural"  # "natural" or "vivid"

def create_chunk(id: str, created: int, model: str, delta: dict, finish_reason: Union[str, None]) -> str:
    chunk = {
        "id": id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "logprobs": None,  # OpenAI field standar
            "finish_reason": finish_reason
        }],
        "system_fingerprint": None  # OpenAI field standar（）
    }
    return json.dumps(chunk)
# ---------- Auth endpoints (API) ----------

@app.post("/login")
async def admin_login_post(request: Request, admin_key: str = Form(...)):
    """Admin login (API)"""
    if admin_key == ADMIN_KEY:
        login_user(request)
        logger.info("[AUTH] Admin login success")
        return {"success": True}
    logger.warning("[AUTH] Login failed - invalid key")
    raise HTTPException(401, "Invalid key")


@app.post("/logout")
@require_login(redirect_to_login=False)
async def admin_logout(request: Request):
    """Admin logout (API)"""
    logout_user(request)
    logger.info("[AUTH] Admin logout")
    return {"success": True}



@app.get("/admin/stats")
@require_login()
async def admin_stats(request: Request, time_range: str = "24h"):
    """
    Dapatkan data statistik

    Args:
        time_range: waktu "24h", "7d", "30d"
    """
    now = time.time()

    active_accounts = 0
    failed_accounts = 0
    rate_limited_accounts = 0
    idle_accounts = 0

    for account_manager in multi_account_mgr.accounts.values():
        config = account_manager.config
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()

        # akunstatus
        is_expired = config.is_expired()
        is_manual_disabled = config.disabled
        is_rate_limited = cooldown_seconds > 0 and cooldown_reason and "cooldown" in cooldown_reason
        is_failed = is_expired
        is_active = (not is_failed) and (not is_manual_disabled) and (not is_rate_limited)

        if is_rate_limited:
            rate_limited_accounts += 1
        elif is_failed:
            failed_accounts += 1
        elif is_active:
            active_accounts += 1
        else:
            idle_accounts += 1

    total_accounts = len(multi_account_mgr.accounts)

    # databaseDapatkan data statistik
    trend_data = await stats_db.get_stats_by_time_range(time_range)
    success_count, failed_count = await stats_db.get_total_counts()

    return {
        "total_accounts": total_accounts,
        "active_accounts": active_accounts,
        "failed_accounts": failed_accounts,
        "rate_limited_accounts": rate_limited_accounts,
        "idle_accounts": idle_accounts,
        "success_count": success_count,
        "failed_count": failed_count,
        "trend": trend_data
    }

@app.get("/admin/accounts")
@require_login()
async def admin_get_accounts(request: Request):
    """ambilakunstatusInfo"""
    accounts_info = []
    for account_id, account_manager in multi_account_mgr.accounts.items():
        config = account_manager.config
        remaining_hours = config.get_remaining_hours()
        status, status_color, remaining_display = format_account_expiration(remaining_hours)
        cooldown_seconds, cooldown_reason = account_manager.get_cooldown_info()
        quota_status = account_manager.get_quota_status()

        accounts_info.append({
            "id": config.account_id,
            "status": status,
            "expires_at": config.expires_at or "",
            "remaining_hours": remaining_hours,
            "remaining_display": remaining_display,
            "is_available": account_manager.is_available,
            "failure_count": account_manager.failure_count,
            "disabled": config.disabled,
            "cooldown_seconds": cooldown_seconds,
            "cooldown_reason": cooldown_reason,
            "conversation_count": account_manager.conversation_count,
            "session_usage_count": account_manager.session_usage_count,
            "quota_status": quota_status  # kuotastatus
        })

    return {"total": len(accounts_info), "accounts": accounts_info}

@app.get("/admin/accounts-config")
@require_login()
async def admin_get_config(request: Request):
    """ambilakunkonfigurasi"""
    try:
        accounts_data = load_accounts_from_source()
        return {"accounts": accounts_data}
    except Exception as e:
        logger.error(f"[CONFIG] ambilkonfigurasiGagal: {str(e)}")
        raise HTTPException(500, f"ambilGagal: {str(e)}")

@app.put("/admin/accounts-config")
@require_login()
async def admin_update_config(request: Request, accounts_data: list = Body(...)):
    """perbaruiakunkonfigurasi"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_accounts_config(
            accounts_data, multi_account_mgr, http_client, USER_AGENT,
            RETRY_POLICY,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": "konfigurasisudahperbarui", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] perbaruikonfigurasiGagal: {str(e)}")
        raise HTTPException(500, f"perbaruiGagal: {str(e)}")

@app.post("/admin/register/start")
@require_login()
async def admin_start_register(request: Request, count: Optional[int] = Body(default=None), domain: Optional[str] = Body(default=None), mail_provider: Optional[str] = Body(default=None)):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = await register_service.start_register(count=count, domain=domain, mail_provider=mail_provider)
    return task.to_dict()


@app.post("/admin/register/cancel/{task_id}")
@require_login()
async def admin_cancel_register_task(request: Request, task_id: str, payload: dict = Body(default=None)):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    payload = payload or {}
    reason = payload.get("reason") or "cancelled"
    task = await register_service.cancel_task(task_id, reason=reason)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/register/task/{task_id}")
@require_login()
async def admin_get_register_task(request: Request, task_id: str):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = register_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/register/current")
@require_login()
async def admin_get_current_register_task(request: Request):
    if not register_service:
        raise HTTPException(503, "register service unavailable")
    task = register_service.get_current_task()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.post("/admin/login/start")
@require_login()
async def admin_start_login(request: Request, account_ids: List[str] = Body(...)):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = await login_service.start_login(account_ids)
    return task.to_dict()


@app.post("/admin/login/cancel/{task_id}")
@require_login()
async def admin_cancel_login_task(request: Request, task_id: str, payload: dict = Body(default=None)):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    payload = payload or {}
    reason = payload.get("reason") or "cancelled"
    task = await login_service.cancel_task(task_id, reason=reason)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/login/task/{task_id}")
@require_login()
async def admin_get_login_task(request: Request, task_id: str):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = login_service.get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task.to_dict()

@app.get("/admin/login/current")
@require_login()
async def admin_get_current_login_task(request: Request):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = login_service.get_current_task()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.post("/admin/login/check")
@require_login()
async def admin_check_login_refresh(request: Request):
    if not login_service:
        raise HTTPException(503, "login service unavailable")
    task = await login_service.check_and_refresh()
    if not task:
        return {"status": "idle"}
    return task.to_dict()

@app.delete("/admin/accounts/{account_id}")
@require_login()
async def admin_delete_account(request: Request, account_id: str):
    """Hapusakun tunggal"""
    global multi_account_mgr
    try:
        multi_account_mgr = _delete_account(
            account_id, multi_account_mgr, http_client, USER_AGENT,
            RETRY_POLICY,
            SESSION_CACHE_TTL_SECONDS, global_stats
        )
        return {"status": "success", "message": f"akun {account_id} sudahHapus", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] Hapus akunGagal: {str(e)}")
        raise HTTPException(500, f"HapusGagal: {str(e)}")

@app.put("/admin/accounts/bulk-delete")
@require_login()
async def admin_bulk_delete_accounts(request: Request, account_ids: list[str]):
    """Hapus akun，singlekalimaks50"""
    global multi_account_mgr

    # jumlahbatasverifikasi
    if len(account_ids) > 50:
        raise HTTPException(400, f"singlekalimaksHapus50akun，saat inipermintaan {len(account_ids)} ")
    if not account_ids:
        raise HTTPException(400, "akunIDdaftar")

    try:
        multi_account_mgr, success_count, errors = _bulk_delete_accounts(
            account_ids,
            multi_account_mgr,
            http_client,
            USER_AGENT,
            RETRY_POLICY,
            SESSION_CACHE_TTL_SECONDS,
            global_stats
        )
        return {"status": "success", "success_count": success_count, "errors": errors}
    except Exception as e:
        logger.error(f"[CONFIG] Hapus akunGagal: {str(e)}")
        raise HTTPException(500, f"HapusGagal: {str(e)}")

@app.put("/admin/accounts/{account_id}/disable")
@require_login()
async def admin_disable_account(request: Request, account_id: str):
    """nonaktifakun"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_account_disabled_status(
            account_id, True, multi_account_mgr
        )

        # Simpansaat inistatusdatabase，tugas
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            await account.save_account_cooldown_state(account_id, account_mgr)

        return {"status": "success", "message": f"akun {account_id} Disabled", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] nonaktifakunGagal: {str(e)}")
        raise HTTPException(500, f"nonaktifGagal: {str(e)}")

@app.put("/admin/accounts/{account_id}/enable")
@require_login()
async def admin_enable_account(request: Request, account_id: str):
    """aktifakun（resetcooldownstatus）"""
    global multi_account_mgr
    try:
        multi_account_mgr = _update_account_disabled_status(
            account_id, False, multi_account_mgr
        )

        # resetruntimecooldownstatus（pulihkanCooldownakun）
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            account_mgr.quota_cooldowns = {}
            logger.info(f"[CONFIG] akun {account_id} cooldownstatussudahreset")

            # Simpancooldownstatusdatabase，tugas
            await account.save_account_cooldown_state(account_id, account_mgr)

        return {"status": "success", "message": f"akun {account_id} sudahaktif", "account_count": len(multi_account_mgr.accounts)}
    except Exception as e:
        logger.error(f"[CONFIG] aktifakunGagal: {str(e)}")
        raise HTTPException(500, f"aktifGagal: {str(e)}")

@app.put("/admin/accounts/bulk-enable")
@require_login()
async def admin_bulk_enable_accounts(request: Request, account_ids: list[str]):
    """Enable batchakun，singlekalimaks50"""
    global multi_account_mgr
    success_count, errors = _bulk_update_account_disabled_status(
        account_ids, False, multi_account_mgr
    )
    # resetruntimeErrorstatus
    for account_id in account_ids:
        if account_id in multi_account_mgr.accounts:
            account_mgr = multi_account_mgr.accounts[account_id]
            account_mgr.quota_cooldowns = {}
    return {"status": "success", "success_count": success_count, "errors": errors}

@app.put("/admin/accounts/bulk-disable")
@require_login()
async def admin_bulk_disable_accounts(request: Request, account_ids: list[str]):
    """Disable batchakun，singlekalimaks50"""
    global multi_account_mgr
    success_count, errors = _bulk_update_account_disabled_status(
        account_ids, True, multi_account_mgr
    )
    return {"status": "success", "success_count": success_count, "errors": errors}

# ---------- Auth endpoints (API) ----------
@app.get("/admin/settings")
@require_login()
async def admin_get_settings(request: Request):
    """Dapatkan pengaturan sistem"""
    return {
        "basic": {
            "api_key": config.basic.api_key,
            "base_url": config.basic.base_url,
            "proxy_for_auth": config.basic.proxy_for_auth,
            "proxy_for_chat": config.basic.proxy_for_chat,
            "browser_engine": config.basic.browser_engine,
            "browser_headless": config.basic.browser_headless,
            "refresh_window_hours": config.basic.refresh_window_hours,
            "register_default_count": config.basic.register_default_count,
        },
        "image_generation": {
            "enabled": config.image_generation.enabled,
            "supported_models": config.image_generation.supported_models,
            "output_format": config.image_generation.output_format
        },
        "video_generation": {
            "output_format": config.video_generation.output_format
        },
        "retry": {
            "max_account_switch_tries": config.retry.max_account_switch_tries,
            "text_rate_limit_cooldown_seconds": config.retry.text_rate_limit_cooldown_seconds,
            "images_rate_limit_cooldown_seconds": config.retry.images_rate_limit_cooldown_seconds,
            "videos_rate_limit_cooldown_seconds": config.retry.videos_rate_limit_cooldown_seconds,
            "session_cache_ttl_seconds": config.retry.session_cache_ttl_seconds,
            "auto_refresh_accounts_seconds": config.retry.auto_refresh_accounts_seconds,
            "scheduled_refresh_enabled": config.retry.scheduled_refresh_enabled,
            "scheduled_refresh_interval_minutes": config.retry.scheduled_refresh_interval_minutes
        },
        "public_display": {
            "logo_url": config.public_display.logo_url,
            "chat_url": config.public_display.chat_url
        },
        "session": {
            "expire_hours": config.session.expire_hours
        }
    }

@app.put("/admin/settings")
@require_login()
async def admin_update_settings(request: Request, new_settings: dict = Body(...)):
    """Update pengaturan sistem"""
    global API_KEY, PROXY_FOR_AUTH, PROXY_FOR_CHAT, BASE_URL, LOGO_URL, CHAT_URL
    global IMAGE_GENERATION_ENABLED, IMAGE_GENERATION_MODELS
    global MAX_ACCOUNT_SWITCH_TRIES
    global RETRY_POLICY
    global SESSION_CACHE_TTL_SECONDS, AUTO_REFRESH_ACCOUNTS_SECONDS
    global SESSION_EXPIRE_HOURS, multi_account_mgr, http_client, http_client_chat, http_client_auth

    try:
        basic = dict(new_settings.get("basic") or {})
        basic.setdefault("browser_engine", config.basic.browser_engine)
        basic.setdefault("browser_headless", config.basic.browser_headless)
        basic.setdefault("refresh_window_hours", config.basic.refresh_window_hours)
        basic.setdefault("register_default_count", config.basic.register_default_count)
        new_settings["basic"] = basic

        image_generation = dict(new_settings.get("image_generation") or {})
        output_format = str(image_generation.get("output_format") or config_manager.image_output_format).lower()
        if output_format not in ("base64", "url"):
            output_format = "base64"
        image_generation["output_format"] = output_format
        new_settings["image_generation"] = image_generation

        video_generation = dict(new_settings.get("video_generation") or {})
        video_output_format = str(video_generation.get("output_format") or config_manager.video_output_format).lower()
        if video_output_format not in ("html", "url", "markdown"):
            video_output_format = "html"
        video_generation["output_format"] = video_output_format
        new_settings["video_generation"] = video_generation

        retry = dict(new_settings.get("retry") or {})
        retry.setdefault("auto_refresh_accounts_seconds", config.retry.auto_refresh_accounts_seconds)
        retry.setdefault("scheduled_refresh_enabled", config.retry.scheduled_refresh_enabled)
        retry.setdefault("scheduled_refresh_interval_minutes", config.retry.scheduled_refresh_interval_minutes)
        retry.setdefault("text_rate_limit_cooldown_seconds", config.retry.text_rate_limit_cooldown_seconds)
        retry.setdefault("images_rate_limit_cooldown_seconds", config.retry.images_rate_limit_cooldown_seconds)
        retry.setdefault("videos_rate_limit_cooldown_seconds", config.retry.videos_rate_limit_cooldown_seconds)
        new_settings["retry"] = retry

        # Simpankonfigurasiuntuk
        old_proxy_for_auth = PROXY_FOR_AUTH
        old_proxy_for_chat = PROXY_FOR_CHAT
        old_retry_config = {
            "text_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.text,
            "images_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.images,
            "videos_rate_limit_cooldown_seconds": RETRY_POLICY.cooldowns.videos,
            "session_cache_ttl_seconds": SESSION_CACHE_TTL_SECONDS
        }

        # Simpan YAML
        config_manager.save_yaml(new_settings)

        # perbaruikonfigurasi
        config_manager.reload()

        # perbaruivariabel global（）
        API_KEY = config.basic.api_key
        _proxy_auth, _no_proxy_auth = parse_proxy_setting(config.basic.proxy_for_auth)
        _proxy_chat, _no_proxy_chat = parse_proxy_setting(config.basic.proxy_for_chat)
        PROXY_FOR_AUTH = _proxy_auth
        PROXY_FOR_CHAT = _proxy_chat
        _NO_PROXY = ",".join(filter(None, {_no_proxy_auth, _no_proxy_chat}))
        if _NO_PROXY:
            os.environ["NO_PROXY"] = _NO_PROXY
        BASE_URL = config.basic.base_url
        LOGO_URL = config.public_display.logo_url
        CHAT_URL = config.public_display.chat_url
        IMAGE_GENERATION_ENABLED = config.image_generation.enabled
        IMAGE_GENERATION_MODELS = config.image_generation.supported_models
        MAX_ACCOUNT_SWITCH_TRIES = config.retry.max_account_switch_tries
        RETRY_POLICY = build_retry_policy()
        SESSION_CACHE_TTL_SECONDS = config.retry.session_cache_ttl_seconds
        AUTO_REFRESH_ACCOUNTS_SECONDS = config.retry.auto_refresh_accounts_seconds
        SESSION_EXPIRE_HOURS = config.session.expire_hours

        # cek HTTP Client（perubahan）
        if old_proxy_for_auth != PROXY_FOR_AUTH or old_proxy_for_chat != PROXY_FOR_CHAT:
            logger.info(f"[CONFIG] Proxy configuration changed, rebuilding HTTP clients")
            await http_client.aclose()
            await http_client_chat.aclose()
            await http_client_auth.aclose()

            # ulang
            http_client = httpx.AsyncClient(
                proxy=(PROXY_FOR_CHAT or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # ulang
            http_client_chat = httpx.AsyncClient(
                proxy=(PROXY_FOR_CHAT or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # ulangakun
            http_client_auth = httpx.AsyncClient(
                proxy=(PROXY_FOR_AUTH or None),
                verify=False,
                http2=False,
                timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=100,
                    max_connections=200
                )
            )

            # Konfigurasi proxy
            logger.info(f"[PROXY] Account operations (register/login/refresh): {PROXY_FOR_AUTH if PROXY_FOR_AUTH else 'disabled'}")
            logger.info(f"[PROXY] Chat operations (JWT/session/messages): {PROXY_FOR_CHAT if PROXY_FOR_CHAT else 'disabled'}")

            # perbaruiakun http_client （）
            multi_account_mgr.update_http_client(http_client)

            # perbarui/loginlayanan http_client （akun）
            if register_service:
                register_service.http_client = http_client_auth
            if login_service:
                login_service.http_client = http_client_auth

        # cekUpdate akunManajemenkonfigurasi（Retryperubahan）
        retry_changed = (
            old_retry_config["text_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.text or
            old_retry_config["images_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.images or
            old_retry_config["videos_rate_limit_cooldown_seconds"] != RETRY_POLICY.cooldowns.videos or
            old_retry_config["session_cache_ttl_seconds"] != SESSION_CACHE_TTL_SECONDS
        )

        if retry_changed:
            logger.info(f"[CONFIG] Retrysudahperubahan，Update akunManajemenkonfigurasi")
            # perbaruiakunManajemenkonfigurasi
            multi_account_mgr.cache_ttl = SESSION_CACHE_TTL_SECONDS
            for account_id, account_mgr in multi_account_mgr.accounts.items():
                account_mgr.apply_retry_policy(RETRY_POLICY)
            if register_service:
                register_service.retry_policy = RETRY_POLICY
            if login_service:
                login_service.retry_policy = RETRY_POLICY

        logger.info(f"[CONFIG] sistemPengaturan sudah diupdate")
        return {"status": "success", "message": "sudahSimpan！"}
    except Exception as e:
        logger.error(f"[CONFIG] perbaruiGagal: {str(e)}")
        raise HTTPException(500, f"perbaruiGagal: {str(e)}")

@app.get("/admin/log")
@require_login()
async def admin_get_logs(
    request: Request,
    limit: int = 300,
    level: str = None,
    search: str = None,
    start_time: str = None,
    end_time: str = None
):
    with log_lock:
        logs = list(log_buffer)

    stats_by_level = {}
    error_logs = []
    chat_count = 0
    for log in logs:
        level_name = log.get("level", "INFO")
        stats_by_level[level_name] = stats_by_level.get(level_name, 0) + 1
        if level_name in ["ERROR", "CRITICAL"]:
            error_logs.append(log)
        if "menerima permintaan" in log.get("message", ""):
            chat_count += 1

    if level:
        level = level.upper()
        logs = [log for log in logs if log["level"] == level]
    if search:
        logs = [log for log in logs if search.lower() in log["message"].lower()]
    if start_time:
        logs = [log for log in logs if log["time"] >= start_time]
    if end_time:
        logs = [log for log in logs if log["time"] <= end_time]

    limit = min(limit, log_buffer.maxlen)
    filtered_logs = logs[-limit:]

    return {
        "total": len(filtered_logs),
        "limit": limit,
        "filters": {"level": level, "search": search, "start_time": start_time, "end_time": end_time},
        "logs": filtered_logs,
        "stats": {
            "memory": {"total": len(log_buffer), "by_level": stats_by_level, "capacity": log_buffer.maxlen},
            "errors": {"count": len(error_logs), "recent": error_logs[-10:]},
            "chat_count": chat_count
        }
    }

@app.delete("/admin/log")
@require_login()
async def admin_clear_logs(request: Request, confirm: str = None):
    if confirm != "yes":
        raise HTTPException(400, " confirm=yes jumlahkonfirmasi operasi kosongkan")
    with log_lock:
        cleared_count = len(log_buffer)
        log_buffer.clear()
    logger.info("[LOG] Log sudah dihapus")
    return {"status": "success", "message": "sudahlog", "cleared_count": cleared_count}

# ---------- Generator Email Domain Management ----------
@app.get("/admin/domains")
@require_login()
async def admin_get_domains(request: Request, active_only: bool = False):
    """Get list generator.email domains"""
    from core.storage import get_generator_domains
    try:
        domains = await get_generator_domains(active_only=active_only)
        
        # Get all domains with status
        all_domains = await get_generator_domains(active_only=False)
        active_domains = await get_generator_domains(active_only=True)
        
        domain_list = []
        for domain in all_domains:
            domain_list.append({
                "domain": domain,
                "is_active": domain in active_domains
            })
        
        return {
            "status": "success",
            "domains": domain_list,
            "total": len(domain_list),
            "active_count": len(active_domains)
        }
    except Exception as e:
        logger.error(f"[ADMIN] Get domains failed: {e}")
        raise HTTPException(500, f"Get domains failed: {str(e)}")

@app.post("/admin/domains")
@require_login()
async def admin_add_domain(request: Request):
    """Add new generator.email domain"""
    from core.storage import add_generator_domain
    try:
        body = await request.json()
        domain = body.get("domain", "").strip().lower()
        
        if not domain:
            raise HTTPException(400, "Domain required")
        
        # Basic validation
        if not domain or "." not in domain:
            raise HTTPException(400, "Invalid domain format")
        
        success = await add_generator_domain(domain)
        
        if success:
            logger.info(f"[ADMIN] Domain added: {domain}")
            return {"status": "success", "message": f"Domain {domain} berhasil ditambahkan"}
        else:
            return {"status": "error", "message": "Domain sudah ada atau gagal ditambahkan"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ADMIN] Add domain failed: {e}")
        raise HTTPException(500, f"Add domain failed: {str(e)}")

@app.delete("/admin/domains/{domain}")
@require_login()
async def admin_remove_domain(request: Request, domain: str):
    """Remove generator.email domain"""
    from core.storage import remove_generator_domain
    try:
        success = await remove_generator_domain(domain)
        
        if success:
            logger.info(f"[ADMIN] Domain removed: {domain}")
            return {"status": "success", "message": f"Domain {domain} berhasil dihapus"}
        else:
            return {"status": "error", "message": "Domain tidak ditemukan atau gagal dihapus"}
            
    except Exception as e:
        logger.error(f"[ADMIN] Remove domain failed: {e}")
        raise HTTPException(500, f"Remove domain failed: {str(e)}")

@app.patch("/admin/domains/{domain}/toggle")
@require_login()
async def admin_toggle_domain(request: Request, domain: str):
    """Toggle domain active/inactive"""
    from core.storage import toggle_generator_domain
    try:
        body = await request.json()
        is_active = body.get("is_active", True)
        
        success = await toggle_generator_domain(domain, is_active)
        
        if success:
            status_text = "aktif" if is_active else "nonaktif"
            logger.info(f"[ADMIN] Domain toggled: {domain} -> {status_text}")
            return {"status": "success", "message": f"Domain {domain} sekarang {status_text}"}
        else:
            return {"status": "error", "message": "Toggle domain gagal"}
            
    except Exception as e:
        logger.error(f"[ADMIN] Toggle domain failed: {e}")
        raise HTTPException(500, f"Toggle domain failed: {str(e)}")

@app.get("/admin/task-history")
@require_login()
async def admin_get_task_history(request: Request, limit: int = 100):
    """Dapatkan riwayat taskcatat"""
    _load_task_history()
    with task_history_lock:
        history = list(task_history)

    live_entries = []
    try:
        if register_service:
            current_register = register_service.get_current_task()
            if current_register and current_register.status in ("running", "pending"):
                live_entries.append(_build_history_entry("register", current_register.to_dict(), is_live=True))
        if login_service:
            current_login = login_service.get_current_task()
            if current_login and current_login.status in ("running", "pending"):
                live_entries.append(_build_history_entry("login", current_login.to_dict(), is_live=True))
    except Exception as exc:
        logger.warning(f"[HISTORY] build live entries failed: {exc}")

    merged = {}
    for entry in live_entries + history:
        entry_id = entry.get("id") or str(uuid.uuid4())
        if entry_id not in merged:
            merged[entry_id] = entry

    # waktu
    history = list(merged.values())
    history.sort(key=lambda x: x.get("created_at", 0), reverse=True)

    # bataskembalikanjumlah
    limit = min(limit, 100)
    return {
        "total": len(history),
        "limit": limit,
        "history": history[:limit]
    }

@app.delete("/admin/task-history")
@require_login()
async def admin_clear_task_history(request: Request, confirm: str = None):
    """tugasriwayatcatat"""
    if confirm != "yes":
        raise HTTPException(400, " confirm=yes jumlahkonfirmasi operasi kosongkan")
    with task_history_lock:
        cleared_count = len(task_history)
        task_history.clear()
        _persist_task_history()
    logger.info("[HISTORY] tugasriwayatsudah")
    return {"status": "success", "message": "sudahtugasriwayat", "cleared_count": cleared_count}

# ---------- Gallery endpoints ----------

@app.get("/admin/gallery")
@require_login()
async def admin_get_gallery(request: Request, media_type: str = "all", limit: int = 100):
    """ambilgambardanvideomediafiledaftar"""
    try:
        result = {"images": [], "videos": []}
        
        # ambilgambar
        if media_type in ("all", "images"):
            if os.path.exists(IMAGE_DIR):
                image_files = []
                for filename in os.listdir(IMAGE_DIR):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                        file_path = os.path.join(IMAGE_DIR, filename)
                        stat = os.stat(file_path)
                        image_files.append({
                            "filename": filename,
                            "url": f"/images/{filename}",
                            "size": stat.st_size,
                            "created_at": stat.st_ctime,
                            "modified_at": stat.st_mtime
                        })
                # urutkan berdasarkan waktu modifikasi menurun
                image_files.sort(key=lambda x: x["modified_at"], reverse=True)
                result["images"] = image_files[:limit]
        
        # ambilvideo
        if media_type in ("all", "videos"):
            if os.path.exists(VIDEO_DIR):
                video_files = []
                for filename in os.listdir(VIDEO_DIR):
                    if filename.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
                        file_path = os.path.join(VIDEO_DIR, filename)
                        stat = os.stat(file_path)
                        video_files.append({
                            "filename": filename,
                            "url": f"/videos/{filename}",
                            "size": stat.st_size,
                            "created_at": stat.st_ctime,
                            "modified_at": stat.st_mtime
                        })
                # urutkan berdasarkan waktu modifikasi menurun
                video_files.sort(key=lambda x: x["modified_at"], reverse=True)
                result["videos"] = video_files[:limit]
        
        return {
            "status": "success",
            "data": result,
            "total": {
                "images": len(result["images"]),
                "videos": len(result["videos"])
            }
        }
    except Exception as e:
        logger.error(f"[GALLERY] ambildaftar mediaGagal: {e}")
        raise HTTPException(500, f"ambildaftar mediaGagal: {str(e)}")

@app.delete("/admin/gallery/{media_type}/{filename}")
@require_login()
async def admin_delete_media(request: Request, media_type: str, filename: str):
    """Hapusmediafile"""
    try:
        if media_type == "images":
            file_path = os.path.join(IMAGE_DIR, filename)
        elif media_type == "videos":
            file_path = os.path.join(VIDEO_DIR, filename)
        else:
            raise HTTPException(400, "media_type  images atau videos")
        
        # cek：pastikanfile
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(400, "file")
        
        if not os.path.exists(file_path):
            raise HTTPException(404, "File tidak ada")
        
        os.remove(file_path)
        logger.info(f"[GALLERY] sudahHapus {media_type}/{filename}")
        
        return {"status": "success", "message": f"sudahHapusfile: {filename}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GALLERY] HapusfileGagal: {e}")
        raise HTTPException(500, f"HapusfileGagal: {str(e)}")

# ---------- Auth endpoints (API) ----------

@app.get("/v1/models")
async def list_models(authorization: str = Header(None)):
    data = []
    now = int(time.time())
    for m in MODEL_MAPPING.keys():
        data.append({"id": m, "object": "model", "created": now, "owned_by": "google", "permission": []})
    data.append({"id": "gemini-imagen", "object": "model", "created": now, "owned_by": "google", "permission": []})
    data.append({"id": "gemini-veo", "object": "model", "created": now, "owned_by": "google", "permission": []})
    return {"object": "list", "data": data}

@app.get("/v1/models/{model_id}")
async def get_model(model_id: str, authorization: str = Header(None)):
    return {"id": model_id, "object": "model"}

# ---------- Auth endpoints (API) ----------

@app.post("/v1/chat/completions")
async def chat(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    # API Key verifikasi
    verify_api_key(API_KEY, authorization)
    # ... (chatlogika)
    return await chat_impl(req, request, authorization)

# chatfungsi
async def chat_impl(
    req: ChatRequest,
    request: Request,
    authorization: Optional[str]
):
    # buat permintaanID（，untuklog）
    request_id = str(uuid.uuid4())[:6]

    start_ts = time.time()
    request.state.first_response_time = None
    message_count = len(req.messages)

    monitor_recorded = False
    account_manager: Optional[AccountManager] = None

    async def finalize_result(
        status: str,
        status_code: Optional[int] = None,
        error_detail: Optional[str] = None
    ) -> None:
        nonlocal monitor_recorded
        if monitor_recorded:
            return
        monitor_recorded = True
        duration_s = time.time() - start_ts
        latency_ms = None
        first_response_time = getattr(request.state, "first_response_time", None)
        if first_response_time:
            latency_ms = int((first_response_time - start_ts) * 1000)
        else:
            latency_ms = int(duration_s * 1000)

        uptime_tracker.record_request("api_service", status == "success", latency_ms, status_code)

        entry = build_recent_conversation_entry(
            request_id=request_id,
            model=req.model if req else None,
            message_count=message_count,
            start_ts=start_ts,
            status=status,
            duration_s=duration_s if status == "success" else None,
            error_detail=error_detail,
        )

        async with stats_lock:
            global_stats.setdefault("failure_timestamps", [])
            global_stats.setdefault("rate_limit_timestamps", [])
            global_stats.setdefault("recent_conversations", [])
            global_stats.setdefault("success_count", 0)
            global_stats.setdefault("failed_count", 0)
            global_stats.setdefault("account_conversations", {})
            global_stats.setdefault("account_failures", {})
            global_stats.setdefault("response_times", deque(maxlen=10000))

            # catatresponwaktu（catatBerhasilpermintaan）
            if status == "success" and latency_ms is not None:
                # catatwaktu respon pertamadanSelesaiwaktu，model
                ttfb_ms = int((first_response_time - start_ts) * 1000) if first_response_time else latency_ms
                total_ms = int((time.time() - start_ts) * 1000)
                model_name = req.model if req else "unknown"

                global_stats["response_times"].append({
                    "timestamp": time.time(),
                    "ttfb_ms": ttfb_ms,  # waktu respon pertama
                    "total_ms": total_ms,  # Selesaiwaktu
                    "model": model_name  # modelnama
                })

                # database
                asyncio.create_task(stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=ttfb_ms,
                    total_ms=total_ms,
                    status=status,
                    status_code=status_code
                ))
            elif status != "success":
                # Gagalpermintaancatatdatabase
                model_name = req.model if req else "unknown"
                asyncio.create_task(stats_db.insert_request_log(
                    timestamp=time.time(),
                    model=model_name,
                    ttfb_ms=None,
                    total_ms=None,
                    status=status,
                    status_code=status_code
                ))

            if status != "success":
                global_stats["failed_count"] += 1
                global_stats["failure_timestamps"].append(time.time())
                if status_code == 429:
                    global_stats["rate_limit_timestamps"].append(time.time())
                failure_account_id = None
                if account_manager:
                    account_manager.failure_count += 1
                    failure_account_id = account_manager.config.account_id
                    global_stats["account_failures"][failure_account_id] = account_manager.failure_count
                else:
                    failure_account_id = getattr(request.state, "last_account_id", None)
                    if failure_account_id and failure_account_id in multi_account_mgr.accounts:
                        account_mgr = multi_account_mgr.accounts[failure_account_id]
                        account_mgr.failure_count += 1
                        global_stats["account_failures"][failure_account_id] = account_mgr.failure_count
                    elif failure_account_id:
                        global_stats["account_failures"][failure_account_id] = (
                            global_stats["account_failures"].get(failure_account_id, 0) + 1
                        )
            else:
                global_stats["success_count"] += 1
                if account_manager:
                    global_stats["account_conversations"][account_manager.config.account_id] = account_manager.conversation_count
            global_stats["recent_conversations"].append(entry)
            global_stats["recent_conversations"] = global_stats["recent_conversations"][-60:]
            await save_stats(global_stats)

    def classify_error_status(status_code: Optional[int], error: Exception) -> str:
        if status_code == 504:
            return "timeout"
        if isinstance(error, (asyncio.TimeoutError, httpx.TimeoutException)):
            return "timeout"
        return "error"


    # ambilIP（untuksesi）
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    # catatpermintaanstatistik
    async with stats_lock:
        timestamp = time.time()
        global_stats["total_requests"] += 1
        global_stats["request_timestamps"].append(timestamp)
        global_stats.setdefault("model_request_timestamps", {})
        global_stats["model_request_timestamps"].setdefault(req.model, []).append(timestamp)
        await save_stats(global_stats)

    # 2. model

    if req.model not in MODEL_MAPPING and req.model not in VIRTUAL_MODELS:
        logger.error(f"[CHAT] [req_{request_id}] model: {req.model}")
        all_models = list(MODEL_MAPPING.keys()) + list(VIRTUAL_MODELS.keys())
        await finalize_result("error", 404, f"HTTP 404: Model '{req.model}' not found")
        raise HTTPException(
            status_code=404,
            detail=f"Model '{req.model}' not found. Available models: {all_models}"
        )

    # SimpanmodelInfo request.state（untuk Uptime ）
    request.state.model = req.model

    required_quota_types = get_required_quota_types(req.model)

    # 3. sesi，ambilSession（satupermintaan）
    conv_key = get_conversation_key([m.model_dump() for m in req.messages], client_ip)
    session_lock = await multi_account_mgr.acquire_session_lock(conv_key)

    # 4. dicekcachedanprosesSession（satupermintaan）
    async with session_lock:
        cached_session = multi_account_mgr.global_session_cache.get(conv_key)

        if cached_session:
            # sudahakun
            account_id = cached_session["account_id"]
            try:
                account_manager = await multi_account_mgr.get_account(account_id, request_id, required_quota_types)
                google_session = cached_session["session_id"]
                is_new_conversation = False
                request.state.last_account_id = account_manager.config.account_id
                logger.info(f"[CHAT] [{account_id}] [req_{request_id}] Lanjutkansesi: {google_session[-12:]}")
            except HTTPException as e:
                logger.warning(
                    f"[CHAT] [req_{request_id}] cachesesiakuntidak tersedia，akun: {account_id} ({str(e.detail)})"
                )
                multi_account_mgr.global_session_cache.pop(conv_key, None)
                cached_session = None

        if not cached_session:
            # ：cobabuat sesi（Erroralih akun）
            available_accounts = multi_account_mgr.get_available_accounts(required_quota_types)
            max_retries = min(MAX_ACCOUNT_SWITCH_TRIES, len(available_accounts))
            last_error = None

            for retry_idx in range(max_retries):
                try:
                    account_manager = await multi_account_mgr.get_account(None, request_id, required_quota_types)
                    google_session = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    # akun
                    await multi_account_mgr.set_session_cache(
                        conv_key,
                        account_manager.config.account_id,
                        google_session
                    )
                    is_new_conversation = True
                    request.state.last_account_id = account_manager.config.account_id
                    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] sesiakun")
                    # catat status pool akun（akunTersedia）
                    uptime_tracker.record_request("account_pool", True)
                    break
                except Exception as e:
                    last_error = e
                    error_type = type(e).__name__
                    # ambilakunID
                    account_id = account_manager.config.account_id if 'account_manager' in locals() and account_manager else 'unknown'
                    logger.error(f"[CHAT] [req_{request_id}] akun {account_id} buat sesiGagal (coba {retry_idx + 1}/{max_retries}) - {error_type}: {str(e)}")
                    # catat status pool akun（akun tunggalGagal）
                    status_code = e.status_code if isinstance(e, HTTPException) else None
                    uptime_tracker.record_request("account_pool", False, status_code=status_code)

                    # prosesError（cooldown）
                    if 'account_manager' in locals() and account_manager:
                        quota_type = get_request_quota_type(req.model)
                        if isinstance(e, HTTPException):
                            account_manager.handle_http_error(status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id, quota_type)
                        else:
                            account_manager.handle_non_http_error("buat sesi", request_id, quota_type)

                    if retry_idx == max_retries - 1:
                        logger.error(f"[CHAT] [req_{request_id}] akuntidak tersedia")
                        status = classify_error_status(503, last_error if isinstance(last_error, Exception) else Exception("account_pool_unavailable"))
                        await finalize_result(status, 503, f"All accounts unavailable: {str(last_error)[:100]}")
                        raise HTTPException(503, f"All accounts unavailable: {str(last_error)[:100]}")
                    # Lanjutkancobasatuakun

    # pastikan account_manager sudahBerhasilambil
    if account_manager is None:
        logger.error(f"[CHAT] [req_{request_id}] tidak adaTersediaakun")
        await finalize_result("error", 503, "No available accounts")
        raise HTTPException(503, "No available accounts")

    # ekstrakisi pesan penggunauntuklog
    if req.messages:
        last_content = req.messages[-1].content
        if isinstance(last_content, str):
            # pesan，batasdi500karakter
            if len(last_content) > 500:
                preview = last_content[:500] + "...(terpotong)"
            else:
                preview = last_content
        else:
            preview = f"[: {len(last_content)}]"
    else:
        preview = "[pesan]"

    # catatpermintaanInfo
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] menerima permintaan: {req.model} | {len(req.messages)} pesan | stream={req.stream}")

    # singlecatatisi pesan pengguna（）
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] pesan: {preview}")

    # 3. uraipermintaankonten
    try:
        last_text, current_images = await parse_last_message(req.messages, http_client, request_id)
    except HTTPException as e:
        status = classify_error_status(e.status_code, e)
        await finalize_result(status, e.status_code, f"HTTP {e.status_code}: {e.detail}")
        raise
    except Exception as e:
        status = classify_error_status(None, e)
        await finalize_result(status, 500, f"{type(e).__name__}: {str(e)[:200]}")
        raise

    # 4. konten teks
    if is_new_conversation:
        # satu
        text_to_send = last_text
        is_retry_mode = True
    else:
        # Lanjutkansaat inipesan
        text_to_send = last_text
        is_retry_mode = False
        # perbaruitimestamp
        await multi_account_mgr.update_session_time(conv_key)

    chat_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    #  (gambarunggahdanRetrylogika)
    async def response_wrapper():
        nonlocal account_manager  #  account_manager

        # singleRetry：Erroralih akun
        available_accounts = multi_account_mgr.get_available_accounts(required_quota_types)
        max_retries = min(MAX_ACCOUNT_SWITCH_TRIES, len(available_accounts))

        current_text = text_to_send
        current_retry_mode = is_retry_mode
        current_file_ids = []

        for retry_idx in range(max_retries):
            try:
                # ambilatau Session
                cached = multi_account_mgr.global_session_cache.get(conv_key)
                if not cached:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] cachesudahbersihkan，Session")
                    new_sess = await create_google_session(account_manager, http_client, USER_AGENT, request_id)
                    await multi_account_mgr.set_session_cache(
                        conv_key,
                        account_manager.config.account_id,
                        new_sess
                    )
                    current_session = new_sess
                    current_retry_mode = True
                    current_file_ids = []
                else:
                    current_session = cached["session_id"]

                # unggahgambar（）
                if current_images and not current_file_ids:
                    for img in current_images:
                        fid = await upload_context_file(current_session, img["mime"], img["data"], account_manager, http_client, USER_AGENT, request_id)
                        current_file_ids.append(fid)

                # （Retry）
                if current_retry_mode:
                    current_text = build_full_context_text(req.messages)

                # 
                async for chunk in stream_chat_generator(
                    current_session,
                    current_text,
                    current_file_ids,
                    req.model,
                    chat_id,
                    created_time,
                    account_manager,
                    req.stream,
                    request_id,
                    request
                ):
                    yield chunk

                if getattr(request.state, "first_response_time", None) is None:
                    # responRetrylogika
                    raise HTTPException(status_code=502, detail="Empty response from upstream")

                # permintaanBerhasil（conversation_count sudahdistatistik）
                uptime_tracker.record_request("account_pool", True)
                await finalize_result("success", 200, None)
                break

            except (httpx.HTTPError, ssl.SSLError, HTTPException) as e:
                # ekstrakErrorInfo
                is_http_exception = isinstance(e, HTTPException)
                status_code = e.status_code if is_http_exception else None
                error_detail = (
                    f"HTTP {e.status_code}: {e.detail}"
                    if is_http_exception
                    else f"{type(e).__name__}: {str(e)[:200]}"
                )

                # catat status pool akun（Request gagal）
                uptime_tracker.record_request("account_pool", False, status_code=status_code)

                # permintaan quota_type
                quota_type = get_request_quota_type(req.model)

                # satuErrorprosespintu masuk
                if is_http_exception:
                    account_manager.handle_http_error(status_code, str(e.detail) if hasattr(e, 'detail') else "", request_id, quota_type)
                else:
                    account_manager.handle_non_http_error("haripermintaan", request_id, quota_type)

                # cekLanjutkanRetry
                if retry_idx < max_retries - 1:
                    logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] alih akunRetry ({retry_idx + 1}/{max_retries})")

                    # cobaakun
                    try:
                        new_account = await multi_account_mgr.get_account(None, request_id, required_quota_types)
                        logger.info(f"[CHAT] [req_{request_id}] alih akun: {account_manager.config.account_id} -> {new_account.config.account_id}")

                        #  Session
                        new_sess = await create_google_session(new_account, http_client, USER_AGENT, request_id)

                        # perbaruicacheakun
                        await multi_account_mgr.set_session_cache(
                            conv_key,
                            new_account.config.account_id,
                            new_sess
                        )

                        # Update akunManajemen
                        account_manager = new_account
                        request.state.last_account_id = account_manager.config.account_id

                        # Retry（）
                        current_retry_mode = True
                        current_file_ids = []  #  ID，ulangunggah Session

                    except Exception as create_err:
                        error_type = type(create_err).__name__
                        logger.error(f"[CHAT] [req_{request_id}] peralihan akunGagal ({error_type}): {str(create_err)}")
                        # catat status pool akun（peralihan akunGagal）
                        status_code = create_err.status_code if isinstance(create_err, HTTPException) else None
                        uptime_tracker.record_request("account_pool", False, status_code=status_code)

                        status = classify_error_status(status_code, create_err)
                        await finalize_result(status, status_code, f"Account Failover Failed: {str(create_err)[:200]}")
                        if req.stream: yield f"data: {json.dumps({'error': {'message': 'Account Failover Failed'}})}\n\n"
                        return
                else:
                    # sudahmencapai maksimumRetrykalijumlah
                    logger.error(f"[CHAT] [req_{request_id}] sudahmencapai maksimumRetrykalijumlah ({max_retries})，Request gagal")
                    status = classify_error_status(status_code, e)
                    await finalize_result(status, status_code, error_detail)
                    if req.stream: yield f"data: {json.dumps({'error': {'message': f'Max retries ({max_retries}) exceeded: {error_detail}'}})}\n\n"
                    return

    if req.stream:
        return StreamingResponse(response_wrapper(), media_type="text/event-stream")
    
    full_content = ""
    full_reasoning = ""
    async for chunk_str in response_wrapper():
        if chunk_str.startswith("data: [DONE]"): break
        if chunk_str.startswith("data: "):
            try:
                data = json.loads(chunk_str[6:])
                delta = data["choices"][0]["delta"]
                if "content" in delta:
                    full_content += delta["content"]
                if "reasoning_content" in delta:
                    full_reasoning += delta["reasoning_content"]
            except json.JSONDecodeError as e:
                logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] JSONuraiGagal: {str(e)}")
            except (KeyError, IndexError) as e:
                logger.error(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] responformatError ({type(e).__name__}): {str(e)}")

    # bangunresponpesan
    message = {"role": "assistant", "content": full_content}
    if full_reasoning:
        message["reasoning_content"] = full_reasoning

    # non-streampermintaanSelesailog
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] non-streamRespons selesai")

    # catatresponkonten（batas500karakter）
    response_preview = full_content[:500] + "...(terpotong)" if len(full_content) > 500 else full_content
    logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] AIrespon: {response_preview}")

    return {
        "id": chat_id,
        "object": "chat.completion",
        "created": created_time,
        "model": req.model,
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    }

# ---------- gambar API (OpenAI ) ----------
@app.post("/v1/images/generations")
async def generate_images(
    req: ImageGenerationRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """OpenAI gambar

    akan /v1/images/generations permintaankonversi keformatproses，
    akanrespon OpenAI gambarformat
    """
    # API Key verifikasi
    verify_api_key(API_KEY, authorization)

    # buat permintaanID
    request_id = str(uuid.uuid4())[:6]

    # konversi ke ChatRequest format
    chat_req = ChatRequest(
        model=req.model,
        messages=[
            Message(role="user", content=req.prompt)
        ],
        stream=False  # gambar
    )

    logger.info(f"[IMAGE-GEN] [req_{request_id}] diterimagambarbuat permintaan: model={req.model}, prompt={req.prompt[:100]}")

    try:
        #  chat_impl ambilrespon
        chat_response = await chat_impl(chat_req, request, authorization)

        # respondiekstrakgambar
        message_content = chat_response["choices"][0]["message"]["content"]

        # urai markdown digambar
        import re
        b64_pattern = r'!\[.*?\]\(data:([^;]+);base64,([^\)]+)\)'
        b64_matches = re.findall(b64_pattern, message_content)
        url_pattern = r'!\[.*?\]\((https?://[^\)]+)\)'
        url_matches = re.findall(url_pattern, message_content)

        # responformat：sistemkonfigurasi
        system_format = config_manager.image_output_format
        response_format = "b64_json" if system_format == "base64" else "url"

        logger.info(f"[IMAGE-GEN] [req_{request_id}] sistemkonfigurasi: {system_format} -> {response_format}")

        # bangun OpenAI formatrespon
        created_time = int(time.time())
        data_list = []

        if response_format == "b64_json":
            # kembalikan base64 format
            for mime, b64_data in b64_matches[:req.n]:
                data_list.append({"b64_json": b64_data, "revised_prompt": req.prompt})

            # tidak ada base64 namun ada URL，unduh
            if not data_list and url_matches:
                for url in url_matches[:req.n]:
                    try:
                        resp = await http_client.get(url)
                        if resp.status_code == 200:
                            b64_data = base64.b64encode(resp.content).decode()
                            data_list.append({"b64_json": b64_data, "revised_prompt": req.prompt})
                    except Exception as e:
                        logger.error(f"[IMAGE-GEN] [req_{request_id}] unduhgambarGagal: {url}, {str(e)}")
        else:
            # kembalikan URL format
            for url in url_matches[:req.n]:
                data_list.append({"url": url, "revised_prompt": req.prompt})

            # tidak ada URL namun ada base64，Simpan URL
            if not data_list and b64_matches:
                base_url = get_base_url(request)
                chat_id = f"img-{uuid.uuid4()}"
                for idx, (mime, b64_data) in enumerate(b64_matches[:req.n], 1):
                    try:
                        img_data = base64.b64decode(b64_data)
                        file_id = f"gen-{uuid.uuid4()}"
                        url = save_image_to_hf(img_data, chat_id, file_id, mime, base_url, IMAGE_DIR)
                        data_list.append({"url": url, "revised_prompt": req.prompt})
                    except Exception as e:
                        logger.error(f"[IMAGE-GEN] [req_{request_id}] SimpangambarGagal: {str(e)}")

        logger.info(f"[IMAGE-GEN] [req_{request_id}] gambarSelesai: {len(data_list)}")

        return {"created": created_time, "data": data_list}

    except Exception as e:
        logger.error(f"[IMAGE-GEN] [req_{request_id}] Gagal generate gambar: {type(e).__name__}: {str(e)}")
        raise

# ---------- gambarprosesfungsi ----------
def parse_images_from_response(data_list: list) -> tuple[list, str]:
    """APIrespondiuraigambarfile
    kembalikan: (file_ids_list, session_name)
    file_ids_list: [{"fileId": str, "mimeType": str}, ...]
    """
    file_ids = []
    session_name = ""
    seen_file_ids = set()  # untukhapus duplikat

    for data in data_list:
        sar = data.get("streamAssistResponse")
        if not sar:
            continue

        # ambilsessionInfo（）
        session_info = sar.get("sessionInfo", {})
        if session_info.get("session"):
            session_name = session_info["session"]

        answer = sar.get("answer") or {}
        replies = answer.get("replies") or []

        for reply in replies:
            gc = reply.get("groundedContent", {})
            content = gc.get("content", {})

            # cekfilefield（gambaryang dihasilkankunci）
            file_info = content.get("file")
            if file_info and file_info.get("fileId"):
                file_id = file_info["fileId"]
                # hapus duplikat：satu fileId prosessatukali
                if file_id in seen_file_ids:
                    continue
                seen_file_ids.add(file_id)

                mime_type = file_info.get("mimeType", "image/png")
                logger.debug(f"[PARSE] uraifile: fileId={file_id}, mimeType={mime_type}")
                file_ids.append({
                    "fileId": file_id,
                    "mimeType": mime_type
                })

    return file_ids, session_name


async def stream_chat_generator(session: str, text_content: str, file_ids: List[str], model_name: str, chat_id: str, created_time: int, account_manager: AccountManager, is_stream: bool = True, request_id: str = "", request: Request = None):
    start_time = time.time()
    full_content = ""
    first_response_time = None

    # catatAPIkonten
    text_preview = text_content[:500] + "...(terpotong)" if len(text_content) > 500 else text_content
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] konten: {text_preview}")
    if file_ids:
        logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] file: {len(file_ids)}")

    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, USER_AGENT)


    tools_spec = get_tools_spec(model_name)

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "streamAssistRequest": {
            "session": session,
            "query": {"parts": [{"text": text_content}]},
            "filter": "",
            "fileIds": file_ids, # file ID
            "answerGenerationMode": "NORMAL",
            "toolsSpec": tools_spec,
            "languageCode": "zh-CN",
            "userMetadata": {"timeZone": "Asia/Shanghai"},
            "assistSkippingMode": "REQUEST_ASSIST"
        }
    }

    target_model_id = MODEL_MAPPING.get(model_name)
    if target_model_id:
        body["streamAssistRequest"]["assistGenerationConfig"] = {
            "modelId": target_model_id
        }

    if is_stream:
        chunk = create_chunk(chat_id, created_time, model_name, {"role": "assistant"}, None)
        yield f"data: {chunk}\n\n"

    # permintaan
    json_objects = []  # responobjekuntukgambarurai
    file_ids_info = None  # SimpangambarInfo

    async with http_client.stream(
        "POST",
        "https://biz-discoveryengine.googleapis.com/v1alpha/locations/global/widgetStreamAssist",
        headers=headers,
        json=body,
    ) as r:
        if r.status_code != 200:
            error_text = await r.aread()
            uptime_tracker.record_request(model_name, False, status_code=r.status_code)
            raise HTTPException(status_code=r.status_code, detail=f"Upstream Error {error_text.decode()}")

        # uraiproses JSON jumlah
        try:
            response_count = 0
            async for json_obj in parse_json_array_stream_async(r.aiter_lines()):
                response_count += 1
                json_objects.append(json_obj)  # respon

                # catatresponstruktur（untukDebugrespon）
                logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] diterimarespon#{response_count}: {json.dumps(json_obj, ensure_ascii=False)[:1000]}")

                # cekErroratauInfo
                if "error" in json_obj:
                    logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] kembalikanError: {json.dumps(json_obj.get('error'), ensure_ascii=False)}")

                stream_response = json_obj.get("streamAssistResponse", {})
                answer = stream_response.get("answer", {})

                # cek
                answer_state = answer.get("state", "")
                if answer_state == "SKIPPED":
                    skip_reasons = answer.get("assistSkippedReasons", [])
                    policy_result = answer.get("customerPolicyEnforcementResult", {})

                    if "CUSTOMER_POLICY_VIOLATION" in skip_reasons:
                        # ekstrakInfo（untuklog）
                        policy_results = policy_result.get("policyResults", [])
                        violation_detail = ""

                        for policy in policy_results:
                            armor_result = policy.get("modelArmorEnforcementResult", {})
                            if armor_result:
                                violation_detail = armor_result.get("modelArmorViolation", "")
                                if violation_detail:
                                    break

                        logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] konten: {violation_detail or 'CUSTOMER_POLICY_VIOLATION'}")

                        # kembalikanErrorInfo
                        error_text = "\n⚠️ \n\n Google ， Gemini tidak ada。\n\n。\n"

                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time

                        full_content += error_text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                        yield f"data: {chunk}\n\n"
                        continue
                    elif skip_reasons:
                        # prosesSkipalasan
                        reason_text = ", ".join(skip_reasons)
                        logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] responSkip: {reason_text}")

                        error_text = f"\n⚠️ ，tidak adarespon。\n\nalasan：{reason_text}\n\nRetryatauManajemen。\n"

                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time

                        full_content += error_text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": error_text}, None)
                        yield f"data: {chunk}\n\n"
                        continue

                replies = answer.get("replies", [])

                # catatrepliesjumlah
                if not replies:
                    logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] respon#{response_count}tidak adareplies，answerstruktur: {json.dumps(answer, ensure_ascii=False)[:500]}")
                else:
                    logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] respon#{response_count}{len(replies)}replies")

                # ekstrakkonten teks
                for idx, reply in enumerate(replies):
                    content_obj = reply.get("groundedContent", {}).get("content", {})
                    text = content_obj.get("text", "")

                    if not text:
                        # catattidak adatext
                        logger.debug(f"[API] [{account_manager.config.account_id}] [req_{request_id}] Reply#{idx}tidak adatext，content_objstruktur: {json.dumps(content_obj, ensure_ascii=False)[:300]}")
                        continue

                    # danNormalkonten
                    if content_obj.get("thought"):
                        #  reasoning_content field（ OpenAI o1）
                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time
                        chunk = create_chunk(chat_id, created_time, model_name, {"reasoning_content": text}, None)
                        yield f"data: {chunk}\n\n"
                    else:
                        if first_response_time is None:
                            first_response_time = time.time()
                            if request is not None:
                                request.state.first_response_time = first_response_time
                            # pertamakaliresponstatistikBerhasilkalijumlah
                            account_manager.conversation_count += 1
                        # Normalkonten content field
                        full_content += text
                        chunk = create_chunk(chat_id, created_time, model_name, {"content": text}, None)
                        yield f"data: {chunk}\n\n"

            # ekstrakgambarInfo（di async with ）
            if json_objects:
                file_ids, session_name = parse_images_from_response(json_objects)
                if file_ids and session_name:
                    file_ids_info = (file_ids, session_name)
                    logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] cek{len(file_ids)}gambar")

            # catatproses
            logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] prosesSelesai: diterima{response_count}responobjek, konten{len(full_content)}karakter")
            if response_count > 0 and len(full_content) == 0:
                logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] ⚠️ responWarning: diterima{response_count}respontidak adakonten teks，atauError")
                # pertamaresponobjekstrukturuntukDebug
                if json_objects:
                    logger.warning(f"[API] [{account_manager.config.account_id}] [req_{request_id}] pertamaresponstruktur: {json.dumps(json_objects[0], ensure_ascii=False)}")


        except ValueError as e:
            uptime_tracker.record_request(model_name, False)
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] JSONuraiGagal: {str(e)}")
        except Exception as e:
            error_type = type(e).__name__
            uptime_tracker.record_request(model_name, False)
            logger.error(f"[API] [{account_manager.config.account_id}] [req_{request_id}] prosesError ({error_type}): {str(e)}")
            raise

    # di async with Proses gambarunduh（）
    if file_ids_info:
        file_ids, session_name = file_ids_info
        try:
            base_url = get_base_url(request) if request else ""
            file_metadata = await get_session_file_metadata(account_manager, session_name, http_client, USER_AGENT, request_id)

            # unduhgambar
            download_tasks = []
            for file_info in file_ids:
                fid = file_info["fileId"]
                mime = file_info["mimeType"]
                meta = file_metadata.get(fid, {})
                #  metadata di MIME 
                mime = meta.get("mimeType", mime)
                correct_session = meta.get("session") or session_name
                task = download_image_with_jwt(account_manager, correct_session, fid, http_client, USER_AGENT, request_id)
                download_tasks.append((fid, mime, task))

            results = await asyncio.gather(*[task for _, _, task in download_tasks], return_exceptions=True)

            # prosesunduhhasil
            success_count = 0
            for idx, ((fid, mime, _), result) in enumerate(zip(download_tasks, results), 1):
                if isinstance(result, Exception):
                    logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] gambar{idx}Gagal download: {type(result).__name__}: {str(result)[:100]}")
                    # turunkanproses：kembalikanErrorGagal
                    error_msg = f"\n\n⚠️ gambar {idx} Gagal download\n\n"
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"
                    continue

                try:
                    markdown = process_media(result, mime, chat_id, fid, base_url, idx, request_id, account_manager.config.account_id)
                    success_count += 1
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": markdown}, None)
                    yield f"data: {chunk}\n\n"
                except Exception as save_error:
                    logger.error(f"[MEDIA] [{account_manager.config.account_id}] [req_{request_id}] media{idx}prosesGagal: {str(save_error)[:100]}")
                    error_msg = f"\n\n⚠️ media {idx} prosesGagal\n\n"
                    if first_response_time is None:
                        first_response_time = time.time()
                        if request is not None:
                            request.state.first_response_time = first_response_time
                    chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
                    yield f"data: {chunk}\n\n"

            logger.info(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] gambarprosesSelesai: {success_count}/{len(file_ids)} Berhasil")

        except Exception as e:
            logger.error(f"[IMAGE] [{account_manager.config.account_id}] [req_{request_id}] gambarprosesGagal: {type(e).__name__}: {str(e)[:100]}")
            # turunkanproses：gambarprosesGagal
            error_msg = f"\n\n⚠️ gambarprosesGagal: {type(e).__name__}\n\n"
            if first_response_time is None:
                first_response_time = time.time()
                if request is not None:
                    request.state.first_response_time = first_response_time
            chunk = create_chunk(chat_id, created_time, model_name, {"content": error_msg}, None)
            yield f"data: {chunk}\n\n"

    if full_content:
        response_preview = full_content[:500] + "...(terpotong)" if len(full_content) > 500 else full_content
        logger.info(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] AIrespon: {response_preview}")
    else:
        logger.warning(f"[CHAT] [{account_manager.config.account_id}] [req_{request_id}] ⚠️ respon，ceklog")


    if first_response_time:
        latency_ms = int((first_response_time - start_time) * 1000)
        uptime_tracker.record_request(model_name, True, latency_ms)
    else:
        uptime_tracker.record_request(model_name, True)

    total_time = time.time() - start_time
    logger.info(f"[API] [{account_manager.config.account_id}] [req_{request_id}] Respons selesai: {total_time:.2f}detik")
    
    if is_stream:
        final_chunk = create_chunk(chat_id, created_time, model_name, {}, "stop")
        yield f"data: {final_chunk}\n\n"
        yield "data: [DONE]\n\n"

# ---------- publikendpoint（Tidak perlu autentikasi） ----------
@app.get("/public/uptime")
async def get_public_uptime(days: int = 90):
    """ambil Uptime jumlah（JSONformat）"""
    if days < 1 or days > 90:
        days = 90
    return await uptime_tracker.get_uptime_summary(days)


@app.get("/public/stats")
async def get_public_stats():
    """ambilpublikstatistikInfo"""
    async with stats_lock:
        # bersihkan1jamsebelumpermintaantimestamp
        current_time = time.time()
        recent_requests = [
            ts for ts in global_stats["request_timestamps"]
            if current_time - ts < 3600
        ]

        # setiapmenitpermintaanjumlah
        recent_minute = [
            ts for ts in recent_requests
            if current_time - ts < 60
        ]
        requests_per_minute = len(recent_minute)

        # status
        if requests_per_minute < 10:
            load_status = "low"
            load_color = "#10b981"  # 
        elif requests_per_minute < 30:
            load_status = "medium"
            load_color = "#f59e0b"  # 
        else:
            load_status = "high"
            load_color = "#ef4444"  # 

        return {
            "total_visitors": global_stats["total_visitors"],
            "total_requests": global_stats["total_requests"],
            "requests_per_minute": requests_per_minute,
            "load_status": load_status,
            "load_color": load_color
        }

@app.get("/public/display")
async def get_public_display():
    """ambilpublikInfo"""
    return {
        "logo_url": LOGO_URL,
        "chat_url": CHAT_URL
    }

@app.get("/public/log")
async def get_public_logs(request: Request, limit: int = 100):
    try:
        # IPaksesstatistik（24jamhapus duplikat）
        client_ip = request.client.host
        current_time = time.time()

        async with stats_lock:
            # bersihkan24jamsebelumIPcatat
            if "visitor_ips" not in global_stats:
                global_stats["visitor_ips"] = {}
            global_stats["visitor_ips"] = {
                ip: timestamp for ip, timestamp in global_stats["visitor_ips"].items()
                if current_time - timestamp <= 86400
            }

            # catatakses（24jamsatuIPjumlahsatukali）
            if client_ip not in global_stats["visitor_ips"]:
                global_stats["visitor_ips"][client_ip] = current_time
                global_stats["total_visitors"] = global_stats.get("total_visitors", 0) + 1

            global_stats.setdefault("recent_conversations", [])
            await save_stats(global_stats)

            stored_logs = list(global_stats.get("recent_conversations", []))

        sanitized_logs = get_sanitized_logs(limit=min(limit, 1000))

        log_map = {log.get("request_id"): log for log in sanitized_logs}
        for log in stored_logs:
            request_id = log.get("request_id")
            if request_id and request_id not in log_map:
                log_map[request_id] = log

        def get_log_ts(item: dict) -> float:
            if "start_ts" in item:
                return float(item["start_ts"])
            try:
                return datetime.strptime(item.get("start_time", ""), "%Y-%m-%d %H:%M:%S").timestamp()
            except Exception:
                return 0.0

        merged_logs = sorted(log_map.values(), key=get_log_ts, reverse=True)[:min(limit, 1000)]
        output_logs = []
        for log in merged_logs:
            if "start_ts" in log:
                log = dict(log)
                log.pop("start_ts", None)
            output_logs.append(log)

        return {
            "total": len(output_logs),
            "logs": output_logs
        }
    except Exception as e:
        logger.error(f"[LOG] ambilpubliklogGagal: {e}")
        return {"total": 0, "logs": [], "error": str(e)}
    except Exception as e:
        logger.error(f"[LOG] ambilpubliklogGagal: {e}")
        return {"total": 0, "logs": [], "error": str(e)}

# ---------- global 404 proses（di） ----------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """global 404 proses"""
    return JSONResponse(
        status_code=404,
        content={"detail": "Not Found"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)
