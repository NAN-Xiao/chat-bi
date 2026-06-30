"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
_registered = False


def register_builtin_tasks() -> None:
    """
    是什么：register_builtin_tasks 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    global _registered
    if _registered:
        return

    from apps.datasource import tasks as datasource_tasks  # noqa: F401
    from apps.knowledge_base import tasks as knowledge_base_tasks  # noqa: F401
    from apps.system import tasks as system_tasks  # noqa: F401

    _registered = True
