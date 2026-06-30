"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from urllib.parse import urlparse

import requests
from requests.exceptions import RequestException, Timeout


def verify_url(url: str, timeout: int = 5) -> tuple[bool, str]:
    """
    是什么：verify_url 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查通用工具里的数据、权限或配置是否合法，不对就及时拦住。
    """
    try:
        parsed = urlparse(url)
        if not all([parsed.scheme, parsed.netloc]):
            return False, "无效的 URL 格式"

        if parsed.scheme not in ['http', 'https']:
            return False, "URL 必须以 http 或 https 开头"

        response = requests.get(
            url,
            timeout=timeout,
            verify=True
        )

        if response.status_code < 400:
            return True, "URL 可达"
        return False, f"服务器返回错误状态码: {response.status_code}"

    except Timeout:
        return False, f"连接超时 (>{timeout}秒)"
    except RequestException as e:
        return False, f"连接失败: {str(e)}"
    except Exception as e:
        return False, f"验证过程发生错误: {str(e)}"
