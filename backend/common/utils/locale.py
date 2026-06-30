"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import json
from pathlib import Path
from typing import Dict, Any

from fastapi import Request


class I18n:
    """
    类说明：I18n 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, locale_dir: str = "locales"):
        """
        是什么：I18n.__init__ 是 I18n 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：创建 I18n 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.locale_dir = Path(locale_dir)
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.load_translations()

    def load_translations(self):
        """
        是什么：I18n.load_translations 是 I18n 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 I18n 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
        """
        if not self.locale_dir.exists():
            self.locale_dir.mkdir()
            return

        for lang_file in self.locale_dir.glob("*.json"):
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations[lang_file.stem.lower()] = json.load(f)

    def get_language(self, request: Request = None, lang: str = None) -> str:
        """
        是什么：I18n.get_language 是 I18n 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 I18n 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
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
        是什么：I18n.__call__ 是 I18n 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：让这个对象能配合 Python 的特殊用法工作。
        """
        return I18nHelper(self, request, lang)


class I18nHelper:
    """
    类说明：I18nHelper 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, i18n: I18n, request: Request = None, lang: str = None):
        """
        是什么：I18nHelper.__init__ 是 I18nHelper 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：创建 I18nHelper 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.i18n = i18n
        self.request = request
        self.lang = i18n.get_language(request, lang)

    def _get_nested_translation(self, data: Dict[str, Any], key_path: str) -> str:
        """
        是什么：I18nHelper._get_nested_translation 是 I18nHelper 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：拿到 I18nHelper 对象的代码，需要完成这个动作时会调用它。
        做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
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
        是什么：I18nHelper.__call__ 是 I18nHelper 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：Python 在需要这个特殊行为时会自动调用它。
        做了什么：让这个对象能配合 Python 的特殊用法工作。
        """
        lang_data = self.i18n.translations.get(self.lang, {})
        text = self._get_nested_translation(lang_data, arg_key)

        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text
