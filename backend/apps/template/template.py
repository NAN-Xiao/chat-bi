"""
脚本说明：这个脚本放提示词和模板相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import yaml
from pathlib import Path
from functools import cache
from typing import Union

from apps.db.constant import DB

# 基础路径配置
PROJECT_ROOT = Path(__file__).parent.parent.parent
TEMPLATES_DIR = PROJECT_ROOT / 'templates'
BASE_TEMPLATE_PATH = TEMPLATES_DIR / 'template.yaml'
SQL_TEMPLATES_DIR = TEMPLATES_DIR / 'sql_examples'


@cache
def _load_template_file(file_path: Path):
    """
    是什么：_load_template_file 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板需要的数据找出来，整理成后面好用的样子。
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Template file not found at {file_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML file {file_path}: {e}")


def get_base_template():
    """
    是什么：get_base_template 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板需要的数据找出来，整理成后面好用的样子。
    """
    return _load_template_file(BASE_TEMPLATE_PATH)


def get_sql_template(db_type: Union[str, DB]):
    # 处理输入参数
    """
    是什么：get_sql_template 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板需要的数据找出来，整理成后面好用的样子。
    """
    if isinstance(db_type, str):
        # 如果是字符串，查找对应的枚举值，找不到则使用默认的 DB.pg
        db_enum = DB.get_db(db_type, default_if_none=True)
    elif isinstance(db_type, DB):
        db_enum = db_type
    else:
        db_enum = DB.pg

    # 使用 template_name 作为文件名
    template_path = SQL_TEMPLATES_DIR / f"{db_enum.template_name}.yaml"

    return _load_template_file(template_path)


def get_all_sql_templates():
    """
    是什么：get_all_sql_templates 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板需要的数据找出来，整理成后面好用的样子。
    """
    templates = {}
    for db in DB:
        try:
            templates[db.type] = get_sql_template(db)
        except FileNotFoundError:
            # 如果某个数据库的模板文件不存在，跳过
            continue
    return templates


def reload_all_templates():
    """
    是什么：reload_all_templates 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _load_template_file.cache_clear()


