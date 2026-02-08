"""
SessionModul
SessionLogin
"""
import secrets
from functools import wraps
from typing import Optional
from fastapi import HTTPException, Request, Response
from fastapi.responses import RedirectResponse


def generate_session_secret() -> str:
    """GeneratesessionKey"""
    return secrets.token_hex(32)


def is_logged_in(request: Request) -> bool:
    """CekUserYaTidaksudahLogin"""
    return request.session.get("authenticated", False)


def login_user(request: Request):
    """UsersudahLoginStatus"""
    request.session["authenticated"] = True


def logout_user(request: Request):
    """UserLoginStatus"""
    request.session.clear()


def require_login(redirect_to_login: bool = True):
    """
    UserLogin

    Args:
        redirect_to_login: belumLoginYaTidakLogin（DefaultTrue）
                          FalseReturn404Error
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request, **kwargs):
            if not is_logged_in(request):
                if redirect_to_login:
                    accept_header = (request.headers.get("accept") or "").lower()
                    wants_html = "text/html" in accept_header or request.url.path.endswith("/html")

                    if wants_html:
                        #  URL bisa PATH_PREFIX
                        # Path
                        path = request.url.path

                        #  main  PATH_PREFIX Kosong
                        import main
                        prefix = main.PATH_PREFIX

                        if prefix:
                            login_url = f"/{prefix}/login"
                        else:
                            login_url = "/login"

                        return RedirectResponse(url=login_url, status_code=302)

                raise HTTPException(401, "Unauthorized")

            return await func(*args, request=request, **kwargs)
        return wrapper
    return decorator
