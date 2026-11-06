"""Password hashing (argon2 via pwdlib) and JWT access tokens (PyJWT)."""

from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.domain.errors import AuthenticationFailed

_hasher = PasswordHash.recommended()
_ALGO = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def create_access_token(user_id: int, role: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=s.jwt_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=_ALGO)


def decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGO])
        return int(payload["sub"])
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationFailed("Your session has expired. Please sign in again.") from e
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise AuthenticationFailed("Please sign in to continue.") from e
