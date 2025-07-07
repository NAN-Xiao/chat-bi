from pathlib import Path
import json
from typing import Dict, Optional
from fastapi import Request

class I18n:
    def __init__(self, locale_dir: str = "locales"):
        self.locale_dir = Path(locale_dir)
        self.translations: Dict[str, Dict[str, str]] = {}
        self.load_translations()

    def load_translations(self):
       
        if not self.locale_dir.exists():
            self.locale_dir.mkdir()
            return

        for lang_file in self.locale_dir.glob("*.json"):
            with open(lang_file, 'r', encoding='utf-8') as f:
                self.translations[lang_file.stem.lower()] = json.load(f)

    def get_language(self, request: Request) -> str:
        accept_language = request.headers.get('accept-language', 'en')
        primary_lang = accept_language.split(',')[0].lower()
        
        return primary_lang if primary_lang in self.translations else 'zh-cn'

    def __call__(self, request: Request) -> 'I18nHelper':
        return I18nHelper(self, request)

class I18nHelper:
    def __init__(self, i18n: I18n, request: Request):
        self.i18n = i18n
        self.request = request
        self.lang = i18n.get_language(request)

    def __call__(self, key: str, **kwargs) -> str:
        lang_data = self.i18n.translations.get(self.lang, {})
        text = lang_data.get(key, key)  # 找不到则返回原key
        
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text