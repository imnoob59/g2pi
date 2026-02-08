import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core.mail_providers import create_temp_mail_client
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC

logger = logging.getLogger("gemini.register")


@dataclass
class RegisterTask(BaseTask):
    """DaftarDataClass"""
    count: int = 0
    domain: Optional[str] = None
    mail_provider: Optional[str] = None

    def to_dict(self) -> dict:
        """Konversi"""
        base_dict = super().to_dict()
        base_dict["count"] = self.count
        base_dict["domain"] = self.domain
        base_dict["mail_provider"] = self.mail_provider
        return base_dict


class RegisterService(BaseTaskService[RegisterTask]):
    """DaftarServiceClass"""

    def __init__(
        self,
        multi_account_mgr,
        http_client,
        user_agent: str,
        retry_policy,
        session_cache_ttl_seconds: int,
        global_stats_provider: Callable[[], dict],
        set_multi_account_mgr: Optional[Callable[[Any], None]] = None,
    ) -> None:
        super().__init__(
            multi_account_mgr,
            http_client,
            user_agent,
            retry_policy,
            session_cache_ttl_seconds,
            global_stats_provider,
            set_multi_account_mgr,
            log_prefix="REGISTER",
        )

    def _get_running_task(self) -> Optional[RegisterTask]:
        """AmbilatauTunggu"""
        for task in self._tasks.values():
            if isinstance(task, RegisterTask) and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return task
        return None

    async def start_register(self, count: Optional[int] = None, domain: Optional[str] = None, mail_provider: Optional[str] = None) -> RegisterTask:
        """
        Register akun baru - menggunakan Generator.Email
        """
        async with self._lock:
            if os.environ.get("ACCOUNTS_CONFIG"):
                raise ValueError("sudahSet ACCOUNTS_CONFIG Variabel，Daftarsudah")

            # Default: generator.email
            mail_provider_value = "generatoremail"
            domain_value = None  # Domain diambil dari database

            register_count = count or config.basic.register_default_count
            register_count = max(1, int(register_count))

            # CekYaTidakAda
            running_task = self._get_running_task()

            if running_task:
                # Ada
                running_task.count += register_count
                self._append_log(
                    running_task,
                    "info",
                    f"📝  {register_count} AkunAda (: {running_task.count})"
                )
                return running_task

            # Buat
            task = RegisterTask(id=str(uuid.uuid4()), count=register_count, domain=domain_value, mail_provider=mail_provider_value)
            self._tasks[task.id] = task
            self._append_log(task, "info", f"📝 BuatDaftar (: {register_count}, Email: Generator.Email)")

            # 
            self._current_task_id = task.id
            asyncio.create_task(self._run_task_directly(task))
            return task

            # 
            self._current_task_id = task.id
            asyncio.create_task(self._run_task_directly(task))
            return task

    async def _run_task_directly(self, task: RegisterTask) -> None:
        """"""
        try:
            await self._run_one_task(task)
        finally:
            # Selesai
            async with self._lock:
                if self._current_task_id == task.id:
                    self._current_task_id = None

    def _execute_task(self, task: RegisterTask):
        return self._run_register_async(task, task.domain, task.mail_provider)

    async def _run_register_async(self, task: RegisterTask, domain: Optional[str], mail_provider: Optional[str]) -> None:
        """Daftar（）。"""
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 Daftarsudah ( {task.count} )")

        for idx in range(task.count):
            if task.cancel_requested:
                self._append_log(task, "warning", f"register task cancelled: {task.cancel_reason or 'cancelled'}")
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return

            try:
                self._append_log(task, "info", f"📊 : {idx + 1}/{task.count}")
                result = await loop.run_in_executor(self._executor, self._register_one, domain, mail_provider, task)
            except TaskCancelledError:
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                email = result.get('email', 'belum')
                self._append_log(task, "info", f"✅ DaftarBerhasil: {email}")
            else:
                task.fail_count += 1
                error = result.get('error', 'belumError')
                self._append_log(task, "error", f"❌ DaftarGagal: {error}")

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._current_task_id = None
        self._append_log(task, "info", f"🏁 DaftarSelesai (Berhasil: {task.success_count}, Gagal: {task.fail_count}, : {task.count})")

    def _register_one(self, domain: Optional[str], mail_provider: Optional[str], task: RegisterTask) -> dict:
        """DaftarAkun"""
        log_cb = lambda level, message: self._append_log(task, level, message)

        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", "🆕 MulaiDaftarAkun")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # Generator.Email only
        log_cb("info", f"📧  1/3: DaftarEmail (Generator.Email)...")

        client = create_temp_mail_client(
            provider="generatoremail",
            log_cb=log_cb,
        )

        if not client.register_account():
            log_cb("error", f"❌ Generator.Email EmailDaftarGagal")
            return {"success": False, "error": "EmailDaftarGagal"}

        log_cb("info", f"✅ EmailDaftarBerhasil: {client.email}")

        # Konfigurasi
        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless

        log_cb("info", f"🌐  2/3:  (={browser_engine}, Tidak ada={headless})...")

        if browser_engine == "dp":
            # DrissionPage ：AdadanTidak ada
            automation = GeminiAutomation(
                user_agent=self.user_agent,
                proxy=config.basic.proxy_for_auth,
                headless=headless,
                log_callback=log_cb,
            )
        else:
            # undetected-chromedriver
            automation = GeminiAutomationUC(
                user_agent=self.user_agent,
                proxy=config.basic.proxy_for_auth,
                headless=headless,
                log_callback=log_cb,
            )
        # 
        self._add_cancel_hook(task.id, lambda: getattr(automation, "stop", lambda: None)())

        try:
            log_cb("info", "🔐  3/3:  Gemini Login...")
            result = automation.login_and_extract(client.email, client)
        except Exception as exc:
            log_cb("error", f"❌ Login: {exc}")
            return {"success": False, "error": str(exc)}

        if not result.get("success"):
            error = result.get("error", "Gagal")
            log_cb("error", f"❌ LoginGagal: {error}")
            return {"success": False, "error": error}

        log_cb("info", "✅ Gemini LoginBerhasil，SimpanKonfigurasi...")

        config_data = result["config"]
        config_data["mail_provider"] = "generatoremail"
        config_data["mail_address"] = client.email
        config_data["mail_password"] = ""
        config_data["mail_base_url"] = "https://generator.email"
        config_data["mail_domain"] = getattr(client, "domain", "")

        accounts_data = load_accounts_from_source()
        updated = False
        for acc in accounts_data:
            if acc.get("id") == config_data["id"]:
                acc.update(config_data)
                updated = True
                break
        if not updated:
            accounts_data.append(config_data)

        self._apply_accounts_update(accounts_data)

        log_cb("info", "✅ KonfigurasisudahSimpanDatabase")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log_cb("info", f"🎉 AkunDaftarSelesai: {client.email}")
        log_cb("info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return {"success": True, "email": client.email, "config": config_data}
