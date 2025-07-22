import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import orjson
from jwt.exceptions import InvalidTokenError

from common.core import security
from common.core.config import settings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def generate_password_reset_token(email: str) -> str:
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None


def deepcopy_ignore_extra(src, dest):
    import copy
    for attr in vars(src):
        if hasattr(dest, attr):
            src_value = getattr(src, attr)
            dest_value = copy.deepcopy(src_value)  # deep copy
            setattr(dest, attr, dest_value)
    return dest


def extract_nested_json(text):
    stack = []
    start_index = -1
    results = []

    for i, char in enumerate(text):
        if char in '{[':
            if not stack:  # 记录起始位置
                start_index = i
            stack.append(char)
        elif char in '}]':
            if stack and ((char == '}' and stack[-1] == '{') or (char == ']' and stack[-1] == '[')):
                stack.pop()
                if not stack:  # 栈空时截取完整JSON
                    json_str = text[start_index:i + 1]
                    try:
                        orjson.loads(json_str)  # 验证有效性
                        results.append(json_str)
                    except:
                        pass
            else:
                stack = []  # 括号不匹配则重置
    if len(results) > 0 and results[0]:
        return results[0]
    return None

def string_to_numeric_hash(text: str, bits: Optional[int] = 64) -> int:
    hash_bytes = hashlib.sha256(text.encode()).digest()
    return int.from_bytes(hash_bytes[:bits//8], byteorder='big')
