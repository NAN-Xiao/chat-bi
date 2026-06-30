from datetime import datetime


def get_timestamp() -> int:
    """
    是什么：get_timestamp 是 backend/common/utils/time.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
    """
    dt_millis = int(datetime.now().timestamp() * 1000)
    return dt_millis