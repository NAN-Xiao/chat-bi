import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from common.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_MD5_HEX_RE = re.compile(r"^[a-fA-F0-9]{32}$")


ALGORITHM = "HS256"


def create_access_token(data: dict | Any, expires_delta: timedelta) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    # to_encode = {"exp": expire, "account": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def hash_password(password: str) -> str:
    return get_password_hash(password)


def md5pwd(password: str) -> str:
    m = hashlib.md5()
    m.update(password.encode("utf-8"))
    return m.hexdigest()


def is_md5_password_hash(value: str | None) -> bool:
    return bool(value and _MD5_HEX_RE.fullmatch(value))


def verify_md5pwd(plain_password: str, md5_password: str) -> bool:
    return md5pwd(plain_password) == md5_password


def verify_stored_password(plain_password: str, stored_password: str) -> tuple[bool, bool]:
    """Verify current and legacy password hashes.

    Returns (valid, needs_rehash). MD5 is accepted only for legacy migration.
    """
    if is_md5_password_hash(stored_password):
        return verify_md5pwd(plain_password, stored_password), True
    try:
        return pwd_context.verify(plain_password, stored_password), pwd_context.needs_update(stored_password)
    except (UnknownHashError, ValueError):
        return False, False


def default_pwd() -> str:
    return settings.DEFAULT_PWD


def default_password_hash() -> str:
    return hash_password(default_pwd())


def default_md5_pwd() -> str:
    pwd = default_pwd()
    return md5pwd(pwd)
