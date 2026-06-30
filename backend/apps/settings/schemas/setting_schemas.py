"""
脚本说明：这个脚本定义后端业务的输入输出结构，帮接口和业务代码统一数据格式。
"""
from pydantic import BaseModel

class term_schema_creator(BaseModel):
    """
    类说明：term_schema_creator 用来描述后端业务的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    term: str
    definition: str
    domain: str
    