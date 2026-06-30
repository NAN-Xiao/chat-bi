"""
脚本说明：这个脚本定义系统管理的输入输出结构，帮接口和业务代码统一数据格式。
"""
from typing import Optional
from pydantic import BaseModel


class LogoutSchema(BaseModel):
    """
    类说明：LogoutSchema 用来描述系统管理的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    token: Optional[str] = None
    flag: Optional[str] = 'default'
    origin: Optional[int] = 0
    data: Optional[str] = None