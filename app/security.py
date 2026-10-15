import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


bearer = HTTPBearer(auto_error=False)
SECRET_KEY = os.getenv("HACKMATE_SECRET_KEY")
_EPHEMERAL_SECRET = secrets.token_bytes(32)


def _secret():
    if SECRET_KEY:
        return SECRET_KEY.encode()
    return _EPHEMERAL_SECRET


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{base64.urlsafe_b64encode(salt).decode()}:{base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        salt_text, digest_text = encoded.split(":", 1)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": user_id, "exp": int(time.time()) + 60 * 60 * 24}).encode()
    ).decode().rstrip("=")
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(status_code=401, detail="Authentication required")
    if not credentials:
        raise unauthorized
    try:
        payload, signature = credentials.credentials.split(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise unauthorized
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if data["exp"] < time.time():
            raise unauthorized
        user = db.get(User, int(data["sub"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise unauthorized from None
    if user is None:
        raise unauthorized
    return user


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return current_user(credentials, db)
