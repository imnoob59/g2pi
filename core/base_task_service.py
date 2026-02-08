"""
Kelas layanan task dasar
Menyediakan manajemen task umum, pencatatan log dan fungsi update akun
"""
import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Deque, Dict, Generic, List, Optional, TypeVar
from collections import deque

from core.account import RetryPolicy, update_accounts_config

logger = logging.getLogger("gemini.base_task")


class TaskCancelledError(Exception):
    """Digunakan untuk interrupt eksekusi task dengan cepat di thread/callback."""


class TaskStatus(str, Enum):
    """Enum status task"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BaseTask:
    """Kelas data task dasar"""
    id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    logs: List[Dict[str, str]] = field(default_factory=list)
    cancel_requested: bool = False
    cancel_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Konversi ke dictionary"""
        return {
            "id": self.id,
            "status": self.status.value,
            "progress": self.progress,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "results": self.results,
            "error": self.error,
            "logs": self.logs,
            "cancel_requested": self.cancel_requested,
            "cancel_reason": self.cancel_reason,
        }


T = TypeVar('T', bound=BaseTask)


class BaseTaskService(Generic[T]):
    """
    Kelas layanan task dasar
    Menyediakan manajemen task umum, pencatatan log dan fungsi update akun
    """

    def __init__(
        self,
        multi_account_mgr,
        http_client,
        user_agent: str,
        retry_policy: RetryPolicy,
        session_cache_ttl_seconds: int,
        global_stats_provider: Callable[[], dict],
        set_multi_account_mgr: Optional[Callable[[Any], None]] = None,
        log_prefix: str = "TASK",
    ) -> None:
        """
        Inisialisasi layanan task dasar

        Args:
            multi_account_mgr: Manager multi-akun
            http_client: HTTP client
            user_agent: User agent
            retry_policy: Kebijakan retry
            session_cache_ttl_seconds: TTL cache sesi dalam detik
            global_stats_provider: Provider statistik global
            set_multi_account_mgr: Callback untuk set manager multi-akun
            log_prefix: Prefix log
        """
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._tasks: Dict[str, T] = {}
        self._current_task_id: Optional[str] = None
        self._last_task_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._log_lock = threading.Lock()
        self._log_prefix = log_prefix
        self._pending_task_ids: Deque[str] = deque()
        self._worker_task: Optional[asyncio.Task] = None
        self._current_asyncio_task: Optional[asyncio.Task] = None
        self._cancel_hooks: Dict[str, List[Callable[[], None]]] = {}
        self._cancel_hooks_lock = threading.Lock()

        self.multi_account_mgr = multi_account_mgr
        self.http_client = http_client
        self.user_agent = user_agent
        self.retry_policy = retry_policy
        self.session_cache_ttl_seconds = session_cache_ttl_seconds
        self.global_stats_provider = global_stats_provider
        self.set_multi_account_mgr = set_multi_account_mgr

    def get_task(self, task_id: str) -> Optional[T]:
        """Ambil task tertentu"""
        return self._tasks.get(task_id)

    def get_current_task(self) -> Optional[T]:
        """Ambil task saat ini"""
        if self._current_task_id:
            current = self._tasks.get(self._current_task_id)
            if current:
                return current
        # Jika tidak ada task berjalan, return task pending paling awal di queue (untuk tampilan“menunggu”）
        for task_id in list(self._pending_task_ids):
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                return task
        return None

    def get_pending_task_ids(self) -> List[str]:
        """Return daftar ID task yang menunggu eksekusi (untuk debugging/tampilan)."""
        return list(self._pending_task_ids)

    async def cancel_task(self, task_id: str, reason: str = "cancelled") -> Optional[T]:
        """Request membatalkan task (mendukung pending/running)."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            if task.status == TaskStatus.PENDING:
                # Hapus dari queue dan langsung tandai dibatalkan
                try:
                    self._pending_task_ids.remove(task_id)
                except ValueError:
                    pass
                task.cancel_requested = True
                task.cancel_reason = reason
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                self._append_log(task, "warning", f"task cancelled while pending: {reason}")
                self._save_task_history_best_effort(task)
                self._last_task_id = task.id
                return task

            if task.status == TaskStatus.RUNNING:
                task.cancel_requested = True
                task.cancel_reason = reason
                self._append_log(task, "warning", f"cancel requested: {reason}")
                # （）
                self._fire_cancel_hooks(task_id)
                #  await（ run_in_executor ）
                if self._current_asyncio_task and not self._current_asyncio_task.done():
                    self._current_asyncio_task.cancel()
                return task

            return task

    async def _enqueue_task(self, task: T) -> None:
        """ worker。"""
        self._pending_task_ids.append(task.id)
        if not self._worker_task or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_worker())

    async def _run_worker(self) -> None:
        """（ executor +  worker）。"""
        while True:
            async with self._lock:
                next_task: Optional[T] = None
                # /pendingID
                while self._pending_task_ids:
                    task_id = self._pending_task_ids[0]
                    task = self._tasks.get(task_id)
                    if not task or task.status != TaskStatus.PENDING:
                        self._pending_task_ids.popleft()
                        continue
                    next_task = task
                    self._pending_task_ids.popleft()
                    self._current_task_id = task.id
                    break

            if not next_task:
                break

            await self._run_one_task(next_task)

            async with self._lock:
                if self._current_task_id == next_task.id:
                    self._current_task_id = None

    async def _run_one_task(self, task: T) -> None:
        """，//。"""
        if task.status != TaskStatus.PENDING:
            return
        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            return

        task.status = TaskStatus.RUNNING
        self._append_log(task, "info", "task started")
        try:
            coro = self._execute_task(task)
            self._current_asyncio_task = asyncio.create_task(coro)
            await self._current_asyncio_task
        except asyncio.CancelledError:
            # （）
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            self._append_log(task, "warning", f"task cancelled: {task.cancel_reason or 'cancelled'}")
        except TaskCancelledError:
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            task.finished_at = time.time()
            self._append_log(task, "warning", f"task cancelled: {task.cancel_reason or 'cancelled'}")
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)
            task.finished_at = time.time()
            self._append_log(task, "error", f"task error: {type(exc).__name__}: {str(exc)[:200]}")
        finally:
            self._current_asyncio_task = None
            self._clear_cancel_hooks(task.id)
            if task.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED) and task.finished_at:
                self._save_task_history_best_effort(task)
                self._last_task_id = task.id

    def _add_cancel_hook(self, task_id: str, hook: Callable[[], None]) -> None:
        """（）。"""
        with self._cancel_hooks_lock:
            self._cancel_hooks.setdefault(task_id, []).append(hook)

    def _fire_cancel_hooks(self, task_id: str) -> None:
        """（）。"""
        with self._cancel_hooks_lock:
            hooks = list(self._cancel_hooks.get(task_id) or [])
        for hook in hooks:
            try:
                hook()
            except Exception as exc:
                logger.warning("[%s] cancel hook error: %s", self._log_prefix, str(exc)[:120])

    def _clear_cancel_hooks(self, task_id: str) -> None:
        with self._cancel_hooks_lock:
            self._cancel_hooks.pop(task_id, None)

    # ---  ---
    def _execute_task(self, task: T) -> Awaitable[None]:
        """：（ progress/success/fail/finished_at ）。"""
        raise NotImplementedError

    def _append_log(self, task: T, level: str, message: str) -> None:
        """
        Tambah log

        Args:
            task: 
            level:  (info, warning, error)
            message: 
        """
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "level": level,
            "message": message,
        }
        with self._log_lock:
            task.logs.append(entry)
            if len(task.logs) > 200:
                task.logs = task.logs[-200:]

        log_message = f"[{self._log_prefix}] {message}"
        if level == "warning":
            logger.warning(log_message)
        elif level == "error":
            logger.error(log_message)
        else:
            logger.info(log_message)

        # ：， log_callback 
        # “/”
        if task.cancel_requested:
            safe_messages = (
                "cancel requested:",
                "task cancelled",
                "task cancelled while pending",
                "login task cancelled:",
                "register task cancelled:",
            )
            if not any(message.startswith(x) for x in safe_messages):
                raise TaskCancelledError(task.cancel_reason or "cancelled")

    def _save_task_history_best_effort(self, task: T) -> None:
        try:
            from main import save_task_to_history
            task_type = "login" if self._log_prefix == "REFRESH" else "register"
            save_task_to_history(task_type, task.to_dict())
        except Exception:
            pass

    def _apply_accounts_update(self, accounts_data: list) -> None:
        """
        

        Args:
            accounts_data: 
        """
        global_stats = self.global_stats_provider() or {}
        new_mgr = update_accounts_config(
            accounts_data,
            self.multi_account_mgr,
            self.http_client,
            self.user_agent,
            self.retry_policy,
            self.session_cache_ttl_seconds,
            global_stats,
        )
        self.multi_account_mgr = new_mgr
        if self.set_multi_account_mgr:
            self.set_multi_account_mgr(new_mgr)
