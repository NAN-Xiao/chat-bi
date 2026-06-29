_registered = False


def register_builtin_tasks() -> None:
    global _registered
    if _registered:
        return

    from apps.datasource import tasks as datasource_tasks  # noqa: F401
    from apps.knowledge_base import tasks as knowledge_base_tasks  # noqa: F401
    from apps.system import tasks as system_tasks  # noqa: F401

    _registered = True
