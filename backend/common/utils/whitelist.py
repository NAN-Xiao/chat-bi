# 文件：app/utils/whitelist.py
import re
from typing import List, Pattern
from common.core.config import settings
from common.utils.utils import AppLogUtil
wlist = [
    "/",
    "/health",
    "/ready",
    "/docs",
    "/login/*",
    "*.ico",
    "*.html",
    "*.js",
    "*.css",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.svg",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.otf",
    "*.css.map",
    "/mcp*",
    "/system/config/key",
    "/images/*",
    "/sse",
    "/system/appearance/ui",
    "/system/appearance/picture/*",
    "/system/assistant/validator*",
    "/system/assistant/info/*",
    "/system/assistant/app/*",
    "/system/assistant/picture/*",
    "/system/parameter/login"
]

class WhitelistChecker:
    def __init__(self, paths: List[str] = None):
        """
        是什么：WhitelistChecker.__init__ 是 backend/common/utils/whitelist.py 中的同步方法。
        谁调用：由创建 WhitelistChecker 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.whitelist = paths or wlist
        self._compiled_patterns: List[Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """
        是什么：WhitelistChecker._compile_patterns 是 backend/common/utils/whitelist.py 中的同步方法。
        谁调用：由持有 WhitelistChecker 实例的业务代码、框架回调或测试代码调用。
        做了什么：围绕 _compile_patterns 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        for pattern in self.whitelist:
            if "*" in pattern:
                regex_pattern = (
                    pattern.replace(".", r"\.")
                    .replace("*", ".*")
                )
                if not pattern.startswith("/"):
                    regex_pattern = f"^{regex_pattern}$"
                else:
                    regex_pattern = f"^{regex_pattern}$"
                try:
                    self._compiled_patterns.append(re.compile(regex_pattern))
                except re.error:
                    AppLogUtil.error(f"Invalid regex pattern: {regex_pattern}")

    def is_whitelisted(self, path: str) -> bool:
        """
        是什么：WhitelistChecker.is_whitelisted 是 backend/common/utils/whitelist.py 中的同步方法。
        谁调用：由持有 WhitelistChecker 实例的业务代码、框架回调或测试代码调用。
        做了什么：围绕 is_whitelisted 的语义处理通用工具相关逻辑，并把结果返回或写入状态。
        """
        prefix = settings.API_V1_STR
        if path.startswith(prefix):
            path = path[len(prefix):]

        context_prefix = settings.CONTEXT_PATH
        if context_prefix and path.startswith(context_prefix):
            path = path[len(context_prefix):]

        if not path:
            path = '/'
        if path in self.whitelist:
            return True

        path = path.rstrip('/')
        return any(
            pattern.match(path) is not None
            for pattern in self._compiled_patterns
        )

    def add_path(self, path: str) -> None:

        """
        是什么：WhitelistChecker.add_path 是 backend/common/utils/whitelist.py 中的同步方法。
        谁调用：由持有 WhitelistChecker 实例的业务代码、框架回调或测试代码调用。
        做了什么：创建、初始化或组装通用工具相关对象和数据，并返回或写入对应状态。
        """
        if path not in self.whitelist:
            self.whitelist.append(path)
            if "*" in path:
                self._compile_patterns()

whiteUtils = WhitelistChecker()
