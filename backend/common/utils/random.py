import secrets
import string

def get_random_string(length=16):
    """
    是什么：get_random_string 是 backend/common/utils/random.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
