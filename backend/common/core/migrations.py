"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    """
    是什么：run_migrations 是一个可以复用的小步骤，负责后端基础能力相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端基础能力的主要流程跑起来，一步步调用需要的处理。
    """
    backend_dir = Path(__file__).resolve().parents[2]
    # Keep migration execution independent from the Windows locale.  Alembic
    # 1.17+ reads ini files with ``encoding="locale"`` before env.py can
    # replace the database URL, while this repository's config is UTF-8.
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(alembic_cfg, "head")
