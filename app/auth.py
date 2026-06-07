"""JWT authentication for the management endpoints.

OAuth2 password flow: POST /token with the configured API user/password returns
a short-lived HS256 JWT; protected endpoints require it as a Bearer token.
/health and the HMAC-authenticated /webhook/github are intentionally exempt.
"""

from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import get_settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=True)


def authenticate(username: str, password: str) -> bool:
    settings = get_settings()
    if not settings.api_password:
        return False
    user_ok = hmac.compare_digest(username or "", settings.api_user)
    pass_ok = hmac.compare_digest(password or "", settings.api_password)
    return user_ok and pass_ok


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def require_auth(token: str = Depends(oauth2_scheme)) -> str:
    """FastAPI dependency: validate the Bearer JWT, return the subject."""
    settings = get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not settings.jwt_secret:
        raise HTTPException(status_code=503, detail="Auth not configured")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise credentials_error
    subject = payload.get("sub")
    if not subject:
        raise credentials_error
    return subject
