# 文件：alembic/env.py
import sys
from os.path import abspath, dirname

sys.path.insert(0, dirname(dirname(abspath(__file__))))

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

# 这是 Alembic 配置对象，提供
# 对当前 .ini 配置文件中各项值的访问能力。
config = context.config

# 解析 Python 日志配置文件。
# 这一行用于初始化日志记录器。

# 在这里添加模型的 MetaData 对象
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None

# from apps.system.models.user import SQLModel  # noqa
# from apps.settings.models.setting_models import SQLModel
#from apps.chat.models.chat_model import SQLModel
from apps.chat.models.custom_prompt_model import SQLModel  # noqa
from apps.analysis_assistant.models import SQLModel  # noqa
from apps.knowledge_base.models import SQLModel  # noqa
from apps.system.models.tenant import SQLModel  # noqa
# from apps.dashboard.models.dashboard_model import SQLModel
from common.core.config import settings # noqa
#from apps.datasource.models.datasource import SQLModel
from apps.system.models.system_model import SQLModel

target_metadata = SQLModel.metadata

# env.py 所需的其他配置值
# 可以通过以下方式获取：
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """
    是什么：get_url 是 backend/alembic/env.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询数据库迁移相关数据，整理后返回给调用方。
    """
    return str(settings.SQLALCHEMY_DATABASE_URI)


def run_migrations_offline():
    """
    是什么：run_migrations_offline 是 backend/alembic/env.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行数据库迁移主流程，协调下游服务并处理结果或异常。
    """
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """
    是什么：run_migrations_online 是 backend/alembic/env.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行数据库迁移主流程，协调下游服务并处理结果或异常。
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
