import re
from typing import Optional


def extract_verification_code(text: str) -> Optional[str]:
    """EkstrakVerifikasi"""
    if not text:
        return None

    # 1: （）
    context_pattern = r"(?:Verifikasi|code|verification|passcode|pin).*?[:：]\s*([A-Za-z0-9]{4,8})\b"
    match = re.search(context_pattern, text, re.IGNORECASE)
    if match:
        candidate = match.group(1)
        #  CSS 
        if not re.match(r"^\d+(?:px|pt|em|rem|vh|vw|%)$", candidate, re.IGNORECASE):
            return candidate

    # 2: 6Angka（，）
    match = re.search(r"[A-Z0-9]{6}", text)
    if match:
        return match.group(0)

    # 3: 6Angka（）
    digits = re.findall(r"\b\d{6}\b", text)
    if digits:
        return digits[0]

    return None
