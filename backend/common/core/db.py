from sqlmodel import Session, create_engine, SQLModel

from common.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI), pool_size=20, max_overflow=30, pool_recycle=3600,
                       pool_pre_ping=True)


def get_session():
    with Session(engine) as session:
        yield session


def init_db():
    SQLModel.metadata.create_all(engine)
