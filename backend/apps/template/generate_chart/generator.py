from apps.template.template import get_base_template


def get_chart_template():
    """
    是什么：get_chart_template 是 backend/apps/template/generate_chart/generator.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询模板生成相关数据，整理后返回给调用方。
    """
    template = get_base_template()
    return template['template']['chart']
