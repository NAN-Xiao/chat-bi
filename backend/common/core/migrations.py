from pathlib import Path

from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    """
    是什么：run_migrations 是 backend/common/core/migrations.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行核心配置和基础设施主流程，协调下游服务并处理结果或异常。
    """
    backend_dir = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(alembic_cfg, "head")
