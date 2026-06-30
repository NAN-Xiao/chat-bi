from typing import Union

from apps.db.constant import DB
from apps.template.template import get_base_template, get_sql_template as get_base_sql_template


def get_sql_template():
    """
    是什么：get_sql_template 是 backend/apps/template/generate_sql/generator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询模板生成相关数据，整理后返回给调用方。
    """
    template = get_base_template()
    return template['template']['sql']


def get_sql_example_template(db_type: Union[str, DB]):
    """
    是什么：get_sql_example_template 是 backend/apps/template/generate_sql/generator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询模板生成相关数据，整理后返回给调用方。
    """
    template = get_base_sql_template(db_type)
    return template['template']
