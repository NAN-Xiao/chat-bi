"""
脚本说明：这个脚本放后端基础能力相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from pydantic import BaseModel

class FileRequest(BaseModel):
    """
    类说明：FileRequest 用来描述后端基础能力的数据格式，让请求入参、返回结果和内部传值更清楚。
    """
    file: str
