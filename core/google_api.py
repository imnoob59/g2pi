"""Google APIModul

Google Gemini Business APIAda
"""
import asyncio
import json
import logging
import os
import time
import uuid
from typing import TYPE_CHECKING, List

import httpx
from fastapi import HTTPException

if TYPE_CHECKING:
    from main import AccountManager

logger = logging.getLogger(__name__)

# Google API URL
GEMINI_API_BASE = "https://biz-discoveryengine.googleapis.com/v1alpha"


def get_common_headers(jwt: str, user_agent: str) -> dict:
    """Generate"""
    return {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "authorization": f"Bearer {jwt}",
        "content-type": "application/json",
        "origin": "https://business.gemini.google",
        "referer": "https://business.gemini.google/",
        "user-agent": user_agent,
        "x-server-timeout": "1800",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }


async def make_request_with_jwt_retry(
    account_mgr: "AccountManager",
    method: str,
    url: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
    **kwargs
) -> httpx.Response:
    """HTTP，JWTRetry

    Args:
        account_mgr: AccountManagerInstance
        method: HTTPMethod (GET/POST)
        url: URL
        http_client: httpxClient
        user_agent: User-AgentString
        request_id: ID（Log）
        **kwargs: httpxParameter（json, headers）

    Returns:
        httpx.ResponseObjek
    """
    jwt = await account_mgr.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)

    # Userheaders（JikaAda）
    extra_headers = kwargs.pop("headers", None)
    if extra_headers:
        headers.update(extra_headers)

    # 
    if method.upper() == "GET":
        resp = await http_client.get(url, headers=headers, **kwargs)
    elif method.upper() == "POST":
        resp = await http_client.post(url, headers=headers, **kwargs)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    # Jika401，JWTRetry
    if resp.status_code == 401:
        jwt = await account_mgr.get_jwt(request_id)
        headers = get_common_headers(jwt, user_agent)
        if extra_headers:
            headers.update(extra_headers)

        if method.upper() == "GET":
            resp = await http_client.get(url, headers=headers, **kwargs)
        elif method.upper() == "POST":
            resp = await http_client.post(url, headers=headers, **kwargs)

    return resp


async def create_google_session(
    account_manager: "AccountManager",
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = ""
) -> str:
    """BuatGoogle Session"""
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)
    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "createSessionRequest": {
            "session": {"name": "", "displayName": ""}
        }
    }

    req_tag = f"[req_{request_id}] " if request_id else ""
    r = await http_client.post(
        f"{GEMINI_API_BASE}/locations/global/widgetCreateSession",
        headers=headers,
        json=body,
    )
    if r.status_code != 200:
        logger.error(f"[SESSION] [{account_manager.config.account_id}] {req_tag}Session BuatGagal: {r.status_code}")
        raise HTTPException(r.status_code, "createSession failed")
    sess_name = r.json()["session"]["name"]
    logger.info(f"[SESSION] [{account_manager.config.account_id}] {req_tag}BuatBerhasil: {sess_name[-12:]}")
    return sess_name


async def upload_context_file(
    session_name: str,
    mime_type: str,
    base64_content: str,
    account_manager: "AccountManager",
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = ""
) -> str:
    """File Session，Return fileId"""
    jwt = await account_manager.get_jwt(request_id)
    headers = get_common_headers(jwt, user_agent)

    # GenerateFile
    ext = mime_type.split('/')[-1] if '/' in mime_type else "bin"
    file_name = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"

    body = {
        "configId": account_manager.config.config_id,
        "additionalParams": {"token": "-"},
        "addContextFileRequest": {
            "name": session_name,
            "fileName": file_name,
            "mimeType": mime_type,
            "fileContents": base64_content
        }
    }

    r = await http_client.post(
        f"{GEMINI_API_BASE}/locations/global/widgetAddContextFile",
        headers=headers,
        json=body,
    )

    req_tag = f"[req_{request_id}] " if request_id else ""
    if r.status_code != 200:
        logger.error(f"[FILE] [{account_manager.config.account_id}] {req_tag}FileGagal: {r.status_code}")
        error_text = r.text
        if r.status_code == 400:
            try:
                payload = json.loads(r.text or "{}")
                message = payload.get("error", {}).get("message", "")
            except Exception:
                message = ""
            if "Unsupported file type" in message:
                mime_type = message.split("Unsupported file type:", 1)[-1].strip()
                hint = f"tidakFileTipe: {mime_type}。Konversi PDF、atau。"
                raise HTTPException(400, hint)
        raise HTTPException(r.status_code, f"Upload failed: {error_text}")

    data = r.json()
    file_id = data.get("addContextFileResponse", {}).get("fileId")
    logger.info(f"[FILE] [{account_manager.config.account_id}] {req_tag}FileBerhasil: {mime_type}")
    return file_id


async def get_session_file_metadata(
    account_mgr: "AccountManager",
    session_name: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = ""
) -> dict:
    """AmbilsessionFileData，sessionPath"""
    body = {
        "configId": account_mgr.config.config_id,
        "additionalParams": {"token": "-"},
        "listSessionFileMetadataRequest": {
            "name": session_name,
            "filter": "file_origin_type = AI_GENERATED"
        }
    }

    resp = await make_request_with_jwt_retry(
        account_mgr,
        "POST",
        f"{GEMINI_API_BASE}/locations/global/widgetListSessionFileMetadata",
        http_client,
        user_agent,
        request_id,
        json=body
    )

    if resp.status_code != 200:
        logger.warning(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] AmbilFileDataGagal: {resp.status_code}")
        return {}

    data = resp.json()
    result = {}
    file_metadata_list = data.get("listSessionFileMetadataResponse", {}).get("fileMetadata", [])

    for fm in file_metadata_list:
        fid = fm.get("fileId")
        if fid:
            result[fid] = fm

    return result


def build_image_download_url(session_name: str, file_id: str) -> str:
    """URL"""
    return f"{GEMINI_API_BASE}/{session_name}:downloadFile?fileId={file_id}&alt=media"


async def download_image_with_jwt(
    account_mgr: "AccountManager",
    session_name: str,
    file_id: str,
    http_client: httpx.AsyncClient,
    user_agent: str,
    request_id: str = "",
    max_retries: int = 3
) -> bytes:
    """
    JWT（TimeoutdanRetry）

    Args:
        account_mgr: Akun
        session_name: Session
        file_id: FileID
        http_client: httpxClient
        user_agent: User-AgentString
        request_id: ID
        max_retries: Retry（Default3）

    Returns:
        Data

    Raises:
        HTTPException: Gagal
        asyncio.TimeoutError: Timeout
    """
    url = build_image_download_url(session_name, file_id)
    logger.info(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Mulai: {file_id[:8]}...")

    for attempt in range(max_retries):
        try:
            # 3Timeout（180）-  wait_for  Python 3.10
            resp = await asyncio.wait_for(
                make_request_with_jwt_retry(
                    account_mgr,
                    "GET",
                    url,
                    http_client,
                    user_agent,
                    request_id,
                    follow_redirects=True
                ),
                timeout=180
            )

            resp.raise_for_status()
            logger.info(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Berhasil: {file_id[:8]}... ({len(resp.content)} bytes)")
            return resp.content

        except asyncio.TimeoutError:
            logger.warning(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Timeout ( {attempt + 1}/{max_retries}): {file_id[:8]}...")
            if attempt == max_retries - 1:
                raise HTTPException(504, f"Image download timeout after {max_retries} attempts")
            await asyncio.sleep(2 ** attempt)  # ：2s, 4s, 8s

        except httpx.HTTPError as e:
            logger.warning(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] Gagal ( {attempt + 1}/{max_retries}): {type(e).__name__}")
            if attempt == max_retries - 1:
                raise HTTPException(500, f"Image download failed: {str(e)[:100]}")
            await asyncio.sleep(2 ** attempt)  # 

        except Exception as e:
            logger.error(f"[IMAGE] [{account_mgr.config.account_id}] [req_{request_id}] : {type(e).__name__}: {str(e)[:100]}")
            raise

    # tidak
    raise HTTPException(500, "Image download failed unexpectedly")


def save_image_to_hf(image_data: bytes, chat_id: str, file_id: str, mime_type: str, base_url: str, image_dir: str, url_path: str = "images") -> str:
    """Simpan,ReturnURL"""
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov"
    }
    ext = ext_map.get(mime_type, ".png")

    filename = f"{chat_id}_{file_id}{ext}"
    save_path = os.path.join(image_dir, filename)

    # DirektorisudahBuat,Tidak adaBuat
    with open(save_path, "wb") as f:
        f.write(image_data)

    return f"{base_url}/{url_path}/{filename}"
