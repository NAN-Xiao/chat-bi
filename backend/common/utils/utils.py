"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import base64
import errno
import hashlib
import inspect
import json
import logging
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from urllib.parse import urlparse

from fastapi import Request
from common.core.config import settings
from typing import Optional

import jwt
import orjson
from jwt.exceptions import InvalidTokenError

from common.core import security


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    类说明：SafeRotatingFileHandler 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """

    def doRollover(self):
        """
        是什么：SafeRotatingFileHandler.doRollover 是 SafeRotatingFileHandler 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 SafeRotatingFileHandler 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        try:
            super().doRollover()
        except OSError as exc:
            is_windows_file_lock = (
                getattr(exc, "winerror", None) == 32
                and exc.errno in {errno.EACCES, errno.EPERM}
            )
            if not is_windows_file_lock:
                raise
            if self.stream is None and not self.delay:
                self.stream = self._open()


def generate_password_reset_token(email: str) -> str:
    """
    是什么：generate_password_reset_token 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成通用工具的结果，比如答案、SQL、图表或建议。
    """
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
    """
    是什么：verify_password_reset_token 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查通用工具里的数据、权限或配置是否合法，不对就及时拦住。
    """
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None


def deepcopy_ignore_extra(src, dest):
    """
    是什么：deepcopy_ignore_extra 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    import copy
    for attr in vars(src):
        if hasattr(dest, attr):
            src_value = getattr(src, attr)
            dest_value = copy.deepcopy(src_value)  # 深拷贝
            setattr(dest, attr, dest_value)
    return dest


def extract_nested_json(text):
    """
    是什么：extract_nested_json 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
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
    """
    是什么：string_to_numeric_hash 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    hash_bytes = hashlib.sha256(text.encode()).digest()
    hash_num = int.from_bytes(hash_bytes, byteorder='big')
    max_bigint = 2**63 - 1
    return hash_num % max_bigint


def setup_logging():
    # 确保日志目录存在
    """
    是什么：setup_logging 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具相关的信息改成最新状态，并保存这些变化。
    """
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_format = str(settings.LOG_FORMAT or "").strip()
    if log_format.lower() == "json":
        # 当环境配置使用 "json" 时，回退到安全的纯文本格式化器。
        log_format = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

    # 避免重复初始化时累加处理器
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers.clear()

    # 日志格式
    formatter = logging.Formatter(log_format)

    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.LOG_LEVEL)
    console_handler.setFormatter(formatter)

    # 文件日志处理器
    file_handlers = {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warn': logging.WARNING,
        'error': logging.ERROR
    }

    # 主日志记录器
    root_logger.setLevel(logging.DEBUG)  # 设置最低级别

    # 添加控制台处理器
    root_logger.addHandler(console_handler)

    # 为每个级别创建文件处理器
    for level_name, level in file_handlers.items():
        file_path = log_dir / f"{level_name}.log"
        handler = SafeRotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        handler.setLevel(level)
        handler.setFormatter(formatter)

        # 添加过滤器只处理特定级别日志
        if level_name == 'debug':
            handler.addFilter(lambda record: record.levelno == logging.DEBUG)
        elif level_name == 'info':
            handler.addFilter(lambda record: record.levelno == logging.INFO)
        elif level_name == 'warn':
            handler.addFilter(lambda record: record.levelno == logging.WARNING)
        elif level_name == 'error':
            handler.addFilter(lambda record: record.levelno >= logging.ERROR)

        root_logger.addHandler(handler)

    # SQL 日志特殊处理
    if settings.LOG_LEVEL == "DEBUG" and settings.SQL_DEBUG:
        sql_logger = logging.getLogger('sqlalchemy.engine')
        sql_logger.setLevel(logging.DEBUG)

        sql_handler = SafeRotatingFileHandler(
            log_dir / "sql.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=2,
            encoding='utf-8'
        )
        sql_handler.setFormatter(formatter)
        sql_logger.addHandler(sql_handler)

setup_logging()


class CallerLogger(logging.Logger):
    """
    类说明：CallerLogger 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, logger: logging.Logger):
        """
        是什么：CallerLogger.__init__ 是 CallerLogger 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：创建 CallerLogger 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.logger = logger
        super().__init__(logger.name, logger.level)

    def _log(self, level, msg, args, exc_info=None, extra=None, stacklevel=3):
        """
        是什么：CallerLogger._log 是 CallerLogger 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 CallerLogger 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        if self.logger.isEnabledFor(level):
            self.logger._log(level, msg, args, exc_info=exc_info, extra=extra, stacklevel=stacklevel)

class AppLogUtil:

    """
    类说明：AppLogUtil 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    @staticmethod
    def _get_logger() -> logging.Logger:
        """
        是什么：AppLogUtil._get_logger 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
        """
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back.f_back
            module_name = caller_frame.f_globals.get('__name__', '__main__')
            return CallerLogger(logging.getLogger(module_name))
        finally:
            del frame


    @staticmethod
    def debug(msg: str, *args, **kwargs):
        """
        是什么：AppLogUtil.debug 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.DEBUG):
            logger._log(logging.DEBUG, msg, args, **kwargs)

    @staticmethod
    def info(msg: str, *args, **kwargs):
        """
        是什么：AppLogUtil.info 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.INFO):
            logger._log(logging.INFO, msg, args, **kwargs)

    @staticmethod
    def warning(msg: str, *args, **kwargs):
        """
        是什么：AppLogUtil.warning 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.WARNING):
            logger._log(logging.WARNING, msg, args, **kwargs)

    @staticmethod
    def error(msg: str, *args, exc_info: Optional[bool] = None, **kwargs):
        """
        是什么：AppLogUtil.error 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.ERROR):
            logger._log(
                logging.ERROR,
                msg,
                args,
                exc_info=exc_info if exc_info is not None else True,
                **kwargs
            )

    @staticmethod
    def exception(msg: str, *args, **kwargs):
        """
        是什么：AppLogUtil.exception 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.ERROR):
            logger._log(logging.ERROR, msg, args, exc_info=True, **kwargs)

    @staticmethod
    def critical(msg: str, *args, **kwargs):
        """
        是什么：AppLogUtil.critical 是 AppLogUtil 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        logger = AppLogUtil._get_logger()
        if logger.isEnabledFor(logging.CRITICAL):
            logger._log(logging.CRITICAL, msg, args, **kwargs)

def prepare_for_orjson(data):
    """
    是什么：prepare_for_orjson 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not data:
        return data
    if isinstance(data, bytes):
        return base64.b64encode(data).decode('utf-8')
    elif isinstance(data, dict):
        return {k: prepare_for_orjson(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [prepare_for_orjson(item) for item in data]
    else:
        return data


def prepare_model_arg(origin_arg: str):
    """
    是什么：prepare_model_arg 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not isinstance(origin_arg, str):
        return origin_arg
    if not origin_arg.strip()[0] in {'{', '['}:
        return origin_arg
    try:
        return json.loads(origin_arg)
    except:
        return origin_arg

def get_origin_from_referer(request: Request):
    """
    是什么：get_origin_from_referer 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
    """
    referer = request.headers.get("referer")
    if not referer:
        return None

    try:
        parsed = urlparse(referer)
        if not parsed.scheme or not parsed.hostname:
            return None
        port = parsed.port
        if port:
            if (parsed.scheme == "http" and port != 80) or \
               (parsed.scheme == "https" and port != 443):
                return f"{parsed.scheme}://{parsed.hostname}:{port}"

        return f"{parsed.scheme}://{parsed.hostname}"
    except Exception as e:
        AppLogUtil.error(f"解析 Referer 出错: {e}")
        return referer

def origin_match_domain(origin: str, domain: str) -> bool:
    """
    是什么：origin_match_domain 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if not origin or not domain:
        return False
    origin_normalized = origin.rstrip('/')

    for d in re.split(r'[,;]', domain):
        if d.strip().rstrip('/') == origin_normalized:
            return True

    return False

def get_domain_list(domain: str) -> list[str]:
    """
    是什么：get_domain_list 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
    """
    domains = []
    if not domain:
        return domains
    for d in re.split(r'[,;]', domain):
        d_clean = d.strip().rstrip('/')
        if d_clean:
            domains.append(d_clean)
    return domains


def equals_ignore_case(str1: str, *args: str) -> bool:
    """
    是什么：equals_ignore_case 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if str1 is None:
        return None in args
    for arg in args:
        if arg is None:
            continue
        if str1.casefold() == arg.casefold():
            return True
    return False
