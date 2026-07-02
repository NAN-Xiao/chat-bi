"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from sqlmodel import BigInteger, SQLModel, Field
from typing import Optional

from common.utils.snowflake import snowflake

class SnowflakeBase(SQLModel):
    """
    类说明：SnowflakeBase 用来描述后端基础能力的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    id: Optional[int] = Field(
        default_factory=snowflake.generate_id,
        primary_key=True,
        sa_type=BigInteger(),
        index=True,
        nullable=False
    )
    
    class Config:
        """
        类说明：Config 放后端基础能力的配置项，让后续流程能按同一套规则运行。
        """
        json_encoders = {
            int: lambda v: str(v) if isinstance(v, int) and v > (2**53 - 1) else v
        }
