import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials


security = HTTPBasic(auto_error=False)


def _admin_password() -> str:
    return os.getenv("HAMVOX_ADMIN_PASSWORD", "").strip()


def _admin_username() -> str:
    return os.getenv("HAMVOX_ADMIN_USERNAME", "admin").strip() or "admin"


def _public_protection_enabled() -> bool:
    return os.getenv("HAMVOX_PROTECT_PUBLIC", "false").strip().lower() == "true"


def _challenge() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Basic"},
    )


def _authorize(credentials: HTTPBasicCredentials | None) -> None:
    password = _admin_password()
    if not password:
        return
    if credentials is None:
        _challenge()

    expected_username = _admin_username().encode("utf-8")
    expected_password = password.encode("utf-8")
    provided_username = credentials.username.encode("utf-8")
    provided_password = credentials.password.encode("utf-8")

    username_ok = secrets.compare_digest(provided_username, expected_username)
    password_ok = secrets.compare_digest(provided_password, expected_password)
    if username_ok and password_ok:
        return

    _challenge()


def require_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> None:
    _authorize(credentials)


def require_public_if_enabled(
    credentials: HTTPBasicCredentials = Depends(security),
) -> None:
    if not _public_protection_enabled():
        return
    _authorize(credentials)
