"""
Modul autentikasi API
Menyediakan fungsi verifikasi API Key (untuk endpoint API)
Endpoint manajemen menggunakan autentikasi Session (lihat core/session_auth.py)
"""
from typing import Optional
from fastapi import HTTPException


def verify_api_key(api_key_value: str, authorization: Optional[str] = None) -> bool:
    """
    Verifikasi API Key (mendukung banyak key, dipisahkan dengan koma)

    Args:
        api_key_value: Nilai API Key yang dikonfigurasi (jika kosong skip verifikasi, banyak key dipisahkan koma)
        authorization: Nilai di Authorization Header

    Returns:
        Return True jika verifikasi berhasil, jika tidak lempar HTTPException

    Format yang didukung:
    1. Bearer YOUR_API_KEY
    2. YOUR_API_KEY

    Contoh konfigurasi multi-key:
    API_KEY=key1,key2,key3
    """
    # Jika API_KEY tidak dikonfigurasi, skip verifikasi
    if not api_key_value:
        return True

    # Cek Authorization header
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # Ekstrak token (mendukung format Bearer)
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    # Parse banyak key (dipisahkan koma)
    valid_keys = [key.strip() for key in api_key_value.split(",") if key.strip()]

    if token not in valid_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    return True
