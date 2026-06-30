"""
脚本说明：这个脚本放提示词和模板相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from apps.template.template import get_base_template


def get_dynamic_template():
    """
    是什么：get_dynamic_template 是一个可以复用的小步骤，负责提示词和模板相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把提示词和模板需要的数据找出来，整理成后面好用的样子。
    """
    template = get_base_template()
    return template['template']['dynamic_sql']
