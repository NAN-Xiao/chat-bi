"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
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
    """
    类说明：WhitelistChecker 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, paths: List[str] = None):
        """
        是什么：WhitelistChecker.__init__ 是 WhitelistChecker 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：创建 WhitelistChecker 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.whitelist = paths or wlist
        self._compiled_patterns: List[Pattern] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """
        是什么：WhitelistChecker._compile_patterns 是 WhitelistChecker 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 WhitelistChecker 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：WhitelistChecker.is_whitelisted 是 WhitelistChecker 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 WhitelistChecker 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
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
        是什么：WhitelistChecker.add_path 是 WhitelistChecker 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 WhitelistChecker 对象的代码，需要完成这个动作时会调用它。
        做了什么：创建或保存通用工具需要的东西，让后续流程能继续往下走。
        """
        if path not in self.whitelist:
            self.whitelist.append(path)
            if "*" in path:
                self._compile_patterns()

whiteUtils = WhitelistChecker()
