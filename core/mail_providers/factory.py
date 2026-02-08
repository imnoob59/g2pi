"""
Factory untuk membuat mail client
Hanya support Generator.Email - domain dari database
"""
from typing import Callable, Optional

from core.generator_email_client import GeneratorEmailClient
from core.storage import get_generator_domains_sync, add_generator_domain_sync


def create_temp_mail_client(
    provider: str = "generatoremail",
    *,
    proxy: Optional[str] = None,
    log_cb: Optional[Callable[[str, str], None]] = None,
):
    """
    Membuat klien email sementara - Generator.Email only
    Domains diambil dari database, bukan hardcode
    """
    # Ambil domains dari database
    domains = get_generator_domains_sync(active_only=True)
    
    # Jika database kosong, auto-init dengan default domains
    if not domains:
        default_domains = ["yakali.me", "ydah.me", "ohgitu.me"]
        for domain in default_domains:
            add_generator_domain_sync(domain)
        domains = default_domains
    
    return GeneratorEmailClient(
        domains=domains,
        proxy=proxy or "",
        log_callback=log_cb,
    )
