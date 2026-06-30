from typing import List, Optional, Dict, TypeVar, Protocol, Any
from pydantic import BaseModel


class ITreeNode(Protocol):
    id: Optional[str]
    pid: Optional[str]
    children: List['ITreeNode']

T = TypeVar('T', bound=ITreeNode)

def build_tree_generic(nodes: List[T], root_pid: Any = None) -> List[T]:
    """
    是什么：build_tree_generic 是 backend/common/utils/tree_utils.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装通用工具相关对象和数据，并返回或写入对应状态。
    """
    node_dict: Dict[str, T] = {node.id: node for node in nodes if node.id is not None}
    tree: List[T] = []

    for node in nodes:
        if node.pid == root_pid:
            tree.append(node)
        elif node.pid in node_dict:
            node_dict[node.pid].children.append(node)

    return tree