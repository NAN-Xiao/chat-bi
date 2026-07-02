"""
脚本说明：这个脚本定义后端业务用到的数据表或数据对象，便于代码和数据库对齐。
"""
from sqlmodel import Field

from common.core.models import SnowflakeBase


class term_model(SnowflakeBase, table=True):
    """
    类说明：term_model 表示后端业务里的一类数据，通常用来和数据库表或业务对象对应。
    """
    __tablename__ = "terms"
    term: str = Field(max_length=255)
    definition: str = Field(max_length=255)
    domain: str = Field(max_length=255)
    create_time: int = Field(default=0)
