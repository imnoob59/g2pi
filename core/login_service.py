import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from core.account import load_accounts_from_source
from core.base_task_service import BaseTask, BaseTaskService, TaskCancelledError, TaskStatus
from core.config import config
from core.mail_providers import create_temp_mail_client
from core.gemini_automation import GeminiAutomation
from core.gemini_automation_uc import GeminiAutomationUC

logger = logging.getLogger("gemini.login")

# Konstanta
CONFIG_CHECK_INTERVAL_SECONDS = 60  # KonfigurasiCek（）


@dataclass
class LoginTask(BaseTask):
    """LoginDataClass"""
    account_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Konversi"""
        base_dict = super().to_dict()
        base_dict["account_ids"] = self.account_ids
        return base_dict


class LoginService(BaseTaskService[LoginTask]):
    """LoginServiceClass - """

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
            log_prefix="REFRESH",
        )
        self._is_polling = False

    def _get_running_task(self) -> Optional[LoginTask]:
        """AmbilatauTunggu"""
        for task in self._tasks.values():
            if isinstance(task, LoginTask) and task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return task
        return None

    async def start_login(self, account_ids: List[str]) -> LoginTask:
        """
        Login - 
        - JikaAda，Akun（）
        - JikaAda，Buat
        """
        async with self._lock:
            if not account_ids:
                raise ValueError("AkunListtidakKosong")

            # CekYaTidakAda
            running_task = self._get_running_task()

            if running_task:
                # AkunAda（）
                new_accounts = [aid for aid in account_ids if aid not in running_task.account_ids]

                if new_accounts:
                    running_task.account_ids.extend(new_accounts)
                    self._append_log(
                        running_task,
                        "info",
                        f"📝  {len(new_accounts)} AkunAda (: {len(running_task.account_ids)})"
                    )
                else:
                    self._append_log(running_task, "info", "📝 AdaAkunsudahSaat")

                return running_task

            # Buat
            task = LoginTask(id=str(uuid.uuid4()), account_ids=list(account_ids))
            self._tasks[task.id] = task
            self._append_log(task, "info", f"📝 Buat (: {len(task.account_ids)})")

            # 
            self._current_task_id = task.id
            asyncio.create_task(self._run_task_directly(task))
            return task

    async def _run_task_directly(self, task: LoginTask) -> None:
        """"""
        try:
            await self._run_one_task(task)
        finally:
            # Selesai
            async with self._lock:
                if self._current_task_id == task.id:
                    self._current_task_id = None

    def _execute_task(self, task: LoginTask):
        return self._run_login_async(task)

    async def _run_login_async(self, task: LoginTask) -> None:
        """Login（）。"""
        loop = asyncio.get_running_loop()
        self._append_log(task, "info", f"🚀 sudah ( {len(task.account_ids)} )")

        for idx, account_id in enumerate(task.account_ids, 1):
            # CekYaTidak
            if task.cancel_requested:
                self._append_log(task, "warning", f"login task cancelled: {task.cancel_reason or 'cancelled'}")
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return

            try:
                self._append_log(task, "info", f"📊 : {idx}/{len(task.account_ids)}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🔄 Mulai: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                result = await loop.run_in_executor(self._executor, self._refresh_one, account_id, task)
            except TaskCancelledError:
                # sudah，Akhir
                task.status = TaskStatus.CANCELLED
                task.finished_at = time.time()
                return
            except Exception as exc:
                result = {"success": False, "email": account_id, "error": str(exc)}
            task.progress += 1
            task.results.append(result)

            if result.get("success"):
                task.success_count += 1
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "info", f"🎉 Berhasil: {account_id}")
                self._append_log(task, "info", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                task.fail_count += 1
                error = result.get('error', 'belumError')
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self._append_log(task, "error", f"❌ Gagal: {account_id}")
                self._append_log(task, "error", f"❌ Gagal: {error}")
                self._append_log(task, "error", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if task.cancel_requested:
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.SUCCESS if task.fail_count == 0 else TaskStatus.FAILED
        task.finished_at = time.time()
        self._append_log(task, "info", f"login task finished ({task.success_count}/{len(task.account_ids)})")
        self._current_task_id = None
        self._append_log(task, "info", f"🏁 Selesai (Berhasil: {task.success_count}, Gagal: {task.fail_count}, : {len(task.account_ids)})")

    def _refresh_one(self, account_id: str, task: LoginTask) -> dict:
        """Akun"""
        accounts = load_accounts_from_source()
        account = next((acc for acc in accounts if acc.get("id") == account_id), None)
        if not account:
            return {"success": False, "email": account_id, "error": "tidak"}

        if account.get("disabled"):
            return {"success": False, "email": account_id, "error": "sudah"}

        # AmbilEmail
        mail_provider = (account.get("mail_provider") or "generatoremail").lower()

        # AmbilEmailKonfigurasi
        mail_password = account.get("mail_password", "")

        def log_cb(level, message):
            self._append_log(task, level, f"[{account_id}] {message}")

        log_cb("info", f"📧 Email: {mail_provider}")

        # BuatEmailClient
        mail_address = account.get("mail_address") or account_id

        # AkunKonfigurasiParameter
        account_config = {}
        if account.get("mail_base_url"):
            account_config["base_url"] = account["mail_base_url"]
        if account.get("mail_api_key"):
            account_config["api_key"] = account["mail_api_key"]
        if account.get("mail_jwt_token"):
            account_config["jwt_token"] = account["mail_jwt_token"]
        if account.get("mail_verify_ssl") is not None:
            account_config["verify_ssl"] = account["mail_verify_ssl"]
        if account.get("mail_domain"):
            account_config["domain"] = account["mail_domain"]

        # BuatClient（Parameter，Konfigurasi）
        client = create_temp_mail_client(
            mail_provider,
            log_cb=log_cb,
            **account_config
        )
        client.set_credentials(mail_address, mail_password)

        # Konfigurasi
        browser_engine = (config.basic.browser_engine or "dp").lower()
        headless = config.basic.browser_headless

        log_cb("info", f"🌐  (={browser_engine}, Tidak ada={headless})...")

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
            log_cb("info", "🔐  Gemini Login...")
            result = automation.login_and_extract(account_id, client)
        except Exception as exc:
            log_cb("error", f"❌ Login: {exc}")
            return {"success": False, "email": account_id, "error": str(exc)}
        if not result.get("success"):
            error = result.get("error", "Gagal")
            log_cb("error", f"❌ LoginGagal: {error}")
            return {"success": False, "email": account_id, "error": error}

        log_cb("info", "✅ Gemini LoginBerhasil，SimpanKonfigurasi...")

        # UpdateAkunKonfigurasi
        config_data = result["config"]
        config_data["mail_provider"] = mail_provider
        config_data["mail_password"] = mail_password
        config_data["disabled"] = account.get("disabled", False)

        for acc in accounts:
            if acc.get("id") == account_id:
                acc.update(config_data)
                break

        self._apply_accounts_update(accounts)

        # AkunAdaStatus（Loginbisa）
        if account_id in self.multi_account_mgr.accounts:
            account_mgr = self.multi_account_mgr.accounts[account_id]
            account_mgr.quota_cooldowns.clear()  # 
            account_mgr.is_available = True  # bisaStatus
            log_cb("info", "✅ sudahAkunStatus")

        log_cb("info", "✅ KonfigurasisudahSimpanDatabase")
        return {"success": True, "email": account_id, "config": config_data}


    def _get_expiring_accounts(self) -> List[str]:
        """AmbilAkunList"""
        accounts = load_accounts_from_source()
        expiring = []
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)

        for account in accounts:
            account_id = account.get("id")
            if not account_id:
                continue

            if account.get("disabled"):
                continue
            mail_provider = (account.get("mail_provider") or "generatoremail").lower()
            mail_password = account.get("mail_password") or account.get("email_password")
            
            # Generator.email (browser-based, no credentials required)
            if mail_provider != "generatoremail":
                continue
            expires_at = account.get("expires_at")
            if not expires_at:
                continue

            try:
                expire_time = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                expire_time = expire_time.replace(tzinfo=beijing_tz)
                remaining = (expire_time - now).total_seconds() / 3600
            except Exception:
                continue

            if remaining <= config.basic.refresh_window_hours:
                expiring.append(account_id)

        return expiring

    async def check_and_refresh(self) -> Optional[LoginTask]:
        if os.environ.get("ACCOUNTS_CONFIG"):
            logger.info("[LOGIN] ACCOUNTS_CONFIG set, skipping refresh")
            return None
        expiring_accounts = self._get_expiring_accounts()
        if not expiring_accounts:
            logger.debug("[LOGIN] no accounts need refresh")
            return None

        try:
            return await self.start_login(expiring_accounts)
        except Exception as exc:
            logger.warning("[LOGIN] refresh enqueue failed: %s", exc)
            return None

    async def start_polling(self) -> None:
        if self._is_polling:
            logger.warning("[LOGIN] polling already running")
            return

        self._is_polling = True
        logger.info("[LOGIN] refresh polling started")
        try:
            while self._is_polling:
                # CekKonfigurasiYaTidak
                if not config.retry.scheduled_refresh_enabled:
                    logger.debug("[LOGIN] scheduled refresh disabled, skipping check")
                    await asyncio.sleep(CONFIG_CHECK_INTERVAL_SECONDS)
                    continue

                # Cek
                await self.check_and_refresh()

                # KonfigurasiWaktu
                interval_seconds = config.retry.scheduled_refresh_interval_minutes * 60
                logger.debug(f"[LOGIN] next check in {config.retry.scheduled_refresh_interval_minutes} minutes")
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("[LOGIN] polling stopped")
        except Exception as exc:
            logger.error("[LOGIN] polling error: %s", exc)
        finally:
            self._is_polling = False

    def stop_polling(self) -> None:
        self._is_polling = False
        logger.info("[LOGIN] stopping polling")
