_registered = False


def register_builtin_tasks() -> None:
    global _registered
    if _registered:
        return

    from apps.data_training import tasks as data_training_tasks  # noqa: F401
    from apps.datasource import tasks as datasource_tasks  # noqa: F401
    from apps.system import tasks as system_tasks  # noqa: F401
    from apps.terminology import tasks as terminology_tasks  # noqa: F401

    _registered = True
