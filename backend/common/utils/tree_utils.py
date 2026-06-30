"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from typing import List, Optional, Dict, TypeVar, Protocol, Any
from pydantic import BaseModel


class ITreeNode(Protocol):
    """
    类说明：ITreeNode 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    id: Optional[str]
    pid: Optional[str]
    children: List['ITreeNode']

T = TypeVar('T', bound=ITreeNode)

def build_tree_generic(nodes: List[T], root_pid: Any = None) -> List[T]:
    """
    是什么：build_tree_generic 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存通用工具需要的东西，让后续流程能继续往下走。
    """
    node_dict: Dict[str, T] = {node.id: node for node in nodes if node.id is not None}
    tree: List[T] = []

    for node in nodes:
        if node.pid == root_pid:
            tree.append(node)
        elif node.pid in node_dict:
            node_dict[node.pid].children.append(node)

    return tree