"""PesanModul

PesanParse、EkstrakdanGenerate
"""
import asyncio
import base64
import hashlib
import logging
import re
from typing import List, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from main import Message

logger = logging.getLogger(__name__)


def get_conversation_key(messages: List[dict], client_identifier: str = "") -> str:
    """
    Generate（3Pesan+Client，）

    ：
    1. 3PesanGenerate（1）
    2. Client（IPataurequest_id）tidakUser
    3. Session（UserPesanSession）

    Args:
        messages: PesanList
        client_identifier: Client（IPataurequest_id），tidakUser
    """
    if not messages:
        return f"{client_identifier}:empty" if client_identifier else "empty"

    # Ekstrak3PesanInfo（+Konten）
    message_fingerprints = []
    for msg in messages[:3]:  # 3
        role = msg.get("role", "")
        content = msg.get("content", "")

        # KontenFormat（Stringatau）
        if isinstance(content, list):
            # Pesan：Ekstrak
            text = extract_text_from_content(content)
        else:
            text = str(content)

        # ：Kosong，
        text = text.strip().lower()

        # danKonten
        message_fingerprints.append(f"{role}:{text}")

    # 3Pesan+ClientGenerate
    conversation_prefix = "|".join(message_fingerprints)
    if client_identifier:
        conversation_prefix = f"{client_identifier}|{conversation_prefix}"

    return hashlib.md5(conversation_prefix.encode()).hexdigest()


def extract_text_from_content(content) -> str:
    """
    Pesan content EkstrakKonten
    StringdanFormat
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # Pesan：Ekstrak
        return "".join([x.get("text", "") for x in content if x.get("type") == "text"])
    else:
        return str(content)


async def parse_last_message(messages: List['Message'], http_client: httpx.AsyncClient, request_id: str = ""):
    """ParsePesan，danFile（、PDF、，base64 dan URL）"""
    if not messages:
        return "", []

    last_msg = messages[-1]
    content = last_msg.content

    text_content = ""
    images = [] # List of {"mime": str, "data": str_base64} - Variabel，AdaFile
    image_urls = []  #  URL - Variabel，AdaFile

    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                text_content += part.get("text", "")
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                # Parse Data URI: data:mime/type;base64,xxxxxx (Ada MIME Tipe)
                match = re.match(r"data:([^;]+);base64,(.+)", url)
                if match:
                    images.append({"mime": match.group(1), "data": match.group(2)})
                elif url.startswith(("http://", "https://")):
                    image_urls.append(url)
                else:
                    logger.warning(f"[FILE] [req_{request_id}] tidakFileFormat: {url[:30]}...")

    # Ada URL File（、PDF、）
    if image_urls:
        async def download_url(url: str):
            try:
                resp = await http_client.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 404:
                    logger.warning(f"[FILE] [req_{request_id}] URLFilesudah(404)，sudah: {url[:50]}...")
                    return None
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
                # Tipe，AdaFileTipe
                b64 = base64.b64encode(resp.content).decode()
                logger.info(f"[FILE] [req_{request_id}] URLFileBerhasil: {url[:50]}... ({len(resp.content)} bytes, {content_type})")
                return {"mime": content_type, "data": b64}
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code if e.response else "unknown"
                logger.warning(f"[FILE] [req_{request_id}] URLFileGagal({status_code}): {url[:50]}... - {e}")
                return None
            except Exception as e:
                logger.warning(f"[FILE] [req_{request_id}] URLFileGagal: {url[:50]}... - {e}")
                return None

        results = await asyncio.gather(*[download_url(u) for u in image_urls], return_exceptions=True)
        safe_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[FILE] [req_{request_id}] URLFile: {type(result).__name__}: {str(result)[:120]}")
                continue
            safe_results.append(result)
        images.extend([r for r in safe_results if r])

    return text_content, images


def build_full_context_text(messages: List['Message']) -> str:
    """，Saat"""
    prompt = ""
    for msg in messages:
        role = "User" if msg.role in ["user", "system"] else "Assistant"
        content_str = extract_text_from_content(msg.content)

        # Pesan
        if isinstance(msg.content, list):
            image_count = sum(1 for part in msg.content if part.get("type") == "image_url")
            if image_count > 0:
                content_str += "[]" * image_count

        prompt += f"{role}: {content_str}\n\n"
    return prompt
