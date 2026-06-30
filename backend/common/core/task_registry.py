_registered = False


def register_builtin_tasks() -> None:
    """
    是什么：register_builtin_tasks 是 backend/common/core/task_registry.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 register_builtin_tasks 的语义处理核心配置和基础设施相关逻辑，并把结果返回或写入状态。
    """
    global _registered
    if _registered:
        return

    from apps.datasource import tasks as datasource_tasks  # noqa: F401
    from apps.knowledge_base import tasks as knowledge_base_tasks  # noqa: F401
    from apps.system import tasks as system_tasks  # noqa: F401

    _registered = True
