"""
脚本说明：这个脚本放后端业务相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
# 作者：Junjun
# 日期：2025/12/11
# i18n.py
import json
from pathlib import Path
from typing import Dict

i18n_list = ["en", "zh"]

# 占位符前缀（翻译键前缀）
PLACEHOLDER_PREFIX = "PLACEHOLDER_"

# 默认语言
DEFAULT_LANG = "en"

LOCALES_DIR = Path(__file__).parent / "locales"
_translations_cache: Dict[str, Dict[str, str]] = {}


def load_translation(lang: str) -> Dict[str, str]:
    """
    是什么：load_translation 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务需要的数据找出来，整理成后面好用的样子。
    """
    if lang in _translations_cache:
        return _translations_cache[lang]

    file_path = LOCALES_DIR / f"{lang}.json"
    if not file_path.exists():
        if lang == DEFAULT_LANG:
            raise FileNotFoundError(f"Default language file not found: {file_path}")
        # If the non-default language is missing, fall back to the default language
        return load_translation(DEFAULT_LANG)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Translation file {file_path} must be a JSON object")
            _translations_cache[lang] = data
            return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_path}: {e}")


# 分组标签
tags_metadata = [
    {
        "name": "Data Q&A",
        "description": f"{PLACEHOLDER_PREFIX}data_qa"
    },
    {
        "name": "Datasource",
        "description": f"{PLACEHOLDER_PREFIX}ds_api"
    },
    {"name": "Dashboard",
     "description": f"{PLACEHOLDER_PREFIX}db_api"
     },
    {
        "name": "system_user",
        "description": f"{PLACEHOLDER_PREFIX}system_user_api"
    },
    {
        "name": "system_model",
        "description": f"{PLACEHOLDER_PREFIX}system_model_api"
    },
    {
        "name": "system_assistant",
        "description": f"{PLACEHOLDER_PREFIX}system_assistant_api"
    },
    {
        "name": "system_embedded",
        "description": f"{PLACEHOLDER_PREFIX}system_embedded_api"
    },
    {
        "name": "system_authentication",
        "description": f"{PLACEHOLDER_PREFIX}system_authentication_api"
    },
    {"name": "Table Relation",
     "description": f"{PLACEHOLDER_PREFIX}tr_api"
     },
    {
        "name": "Data Permission",
        "description": f"{PLACEHOLDER_PREFIX}per_api"
    },
    {
        "name": "CustomPrompt",
        "description": f"{PLACEHOLDER_PREFIX}custom_prompt_api"
    },
    {
        "name": "mcp",
        "description": f"{PLACEHOLDER_PREFIX}mcp_api"
    },
    {
        "name": "recommended problem",
        "description": f"{PLACEHOLDER_PREFIX}recommended_problem_api"
    },
    {
        "name": "Audit",
        "description": f"{PLACEHOLDER_PREFIX}audit_api"
    },
    {
        "name": "System_variable",
        "description": f"{PLACEHOLDER_PREFIX}variable_api"
    }
]


def get_translation(lang: str) -> Dict[str, str]:
    """
    是什么：get_translation 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务需要的数据找出来，整理成后面好用的样子。
    """
    return load_translation(lang)
