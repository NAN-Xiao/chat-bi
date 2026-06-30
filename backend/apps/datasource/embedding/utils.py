# 作者：Junjun
# 日期：2025/9/23
import math


def cosine_similarity(vec_a, vec_b):
    """
    是什么：cosine_similarity 是 backend/apps/datasource/embedding/utils.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 cosine_similarity 的语义处理数据源相关逻辑，并把结果返回或写入状态。
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("The vector dimension must be the same")

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)
