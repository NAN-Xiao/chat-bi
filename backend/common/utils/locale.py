import json
from pathlib import Path
from typing import Dict, Any

from fastapi import Request


class I18n:
    def __init__(self, locale_dir: str = "locales"):
        """
        是什么：I18n.__init__ 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由创建 I18n 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.locale_dir = Path(locale_dir)
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.load_translations()

    def load_translations(self):
        """
        是什么：I18n.load_translations 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由持有 I18n 实例的业务代码、框架回调或测试代码调用。
        做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
        """
        if not self.locale_dir.exists():
            self.locale_dir.mkdir()
            return

        for lang_file in self.locale_dir.glob("*.json"):
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations[lang_file.stem.lower()] = json.load(f)

    def get_language(self, request: Request = None, lang: str = None) -> str:
        """
        是什么：I18n.get_language 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由持有 I18n 实例的业务代码、框架回调或测试代码调用。
        做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
        """
        primary_lang: str | None = None
        if lang is not None:
            primary_lang = lang.lower()
        elif request is not None:
            accept_language = request.headers.get('accept-language', 'en')
            primary_lang = accept_language.split(',')[0].lower()

        return primary_lang if primary_lang in self.translations else 'zh-cn'

    def __call__(self, request: Request = None, lang: str = None) -> 'I18nHelper':
        """
        是什么：I18n.__call__ 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：实现 Python 协议方法，使对象可以参与对应的语言级操作。
        """
        return I18nHelper(self, request, lang)


class I18nHelper:
    def __init__(self, i18n: I18n, request: Request = None, lang: str = None):
        """
        是什么：I18nHelper.__init__ 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由创建 I18nHelper 实例的代码在实例化时调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.i18n = i18n
        self.request = request
        self.lang = i18n.get_language(request, lang)

    def _get_nested_translation(self, data: Dict[str, Any], key_path: str) -> str:
        """
        是什么：I18nHelper._get_nested_translation 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由持有 I18nHelper 实例的业务代码、框架回调或测试代码调用。
        做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
        """
        keys = key_path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return key_path  # 如果找不到，返回原键

        return current if isinstance(current, str) else key_path

    def __call__(self, arg_key: str, **kwargs) -> str:
        """
        是什么：I18nHelper.__call__ 是 backend/common/utils/locale.py 中的同步方法。
        谁调用：由 Python 运行时、框架协议或相关内置操作按需调用。
        做了什么：实现 Python 协议方法，使对象可以参与对应的语言级操作。
        """
        lang_data = self.i18n.translations.get(self.lang, {})
        text = self._get_nested_translation(lang_data, arg_key)

        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text
