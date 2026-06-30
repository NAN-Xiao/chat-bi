from sqlmodel import Session, create_engine, SQLModel

from common.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI),
                       pool_size=settings.PG_POOL_SIZE,
                       max_overflow=settings.PG_MAX_OVERFLOW,
                       pool_recycle=settings.PG_POOL_RECYCLE,
                       pool_pre_ping=settings.PG_POOL_PRE_PING)


def get_session():
    """
    是什么：get_session 是 backend/common/core/db.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询核心配置和基础设施相关数据，整理后返回给调用方。
    """
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def init_db():
    """
    是什么：init_db 是 backend/common/core/db.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装核心配置和基础设施相关对象和数据，并返回或写入对应状态。
    """
    SQLModel.metadata.create_all(engine)
