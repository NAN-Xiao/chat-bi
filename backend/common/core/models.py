from pydantic import field_validator
from sqlmodel import BigInteger, SQLModel, Field
from typing import Optional

from common.utils.snowflake import snowflake

class SnowflakeBase(SQLModel):
    id: Optional[int] = Field(
        default_factory=snowflake.generate_id,
        primary_key=True,
        sa_type=BigInteger(),
        index=True,
        nullable=False
    )
    
    @field_validator("id", mode="before")
    def validate_id(cls, v):
        if isinstance(v, str):
            if not v:
                return None
            try:
                return int(v)
            except ValueError:
                raise ValueError("Invalid bigint string")
        elif isinstance(v, int):
            return v
        raise TypeError("BigInt must be int or string")
    
    
    class Config:
        json_encoders = {
            int: lambda v: str(v) if v > 2**53-1 else v
        }