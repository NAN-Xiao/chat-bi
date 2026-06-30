"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
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
    """
    是什么：create_access_token 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存后端基础能力需要的东西，让后续流程能继续往下走。
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    # to_encode = {"exp": expire, "account": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    是什么：verify_password 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    是什么：get_password_hash 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力需要的数据找出来，整理成后面好用的样子。
    """
    return pwd_context.hash(password)


def hash_password(password: str) -> str:
    """
    是什么：hash_password 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return get_password_hash(password)


def md5pwd(password: str) -> str:
    """
    是什么：md5pwd 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    m = hashlib.md5()
    m.update(password.encode("utf-8"))
    return m.hexdigest()


def is_md5_password_hash(value: str | None) -> bool:
    """
    是什么：is_md5_password_hash 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return bool(value and _MD5_HEX_RE.fullmatch(value))


def verify_md5pwd(plain_password: str, md5_password: str) -> bool:
    """
    是什么：verify_md5pwd 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    return md5pwd(plain_password) == md5_password


def verify_stored_password(plain_password: str, stored_password: str) -> tuple[bool, bool]:
    """
    是什么：verify_stored_password 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查后端基础能力里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if is_md5_password_hash(stored_password):
        return verify_md5pwd(plain_password, stored_password), True
    try:
        return pwd_context.verify(plain_password, stored_password), pwd_context.needs_update(stored_password)
    except (UnknownHashError, ValueError):
        return False, False


def default_pwd() -> str:
    """
    是什么：default_pwd 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return settings.DEFAULT_PWD


def default_password_hash() -> str:
    """
    是什么：default_password_hash 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return hash_password(default_pwd())


def default_md5_pwd() -> str:
    """
    是什么：default_md5_pwd 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    pwd = default_pwd()
    return md5pwd(pwd)
