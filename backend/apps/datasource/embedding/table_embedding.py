"""
脚本说明：这个脚本放数据源相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
# 作者：Junjun
# 日期：2025/9/23
import json
import time
import traceback
from typing import Callable

from apps.ai_model.embedding import EmbeddingModelCache
from apps.datasource.embedding.utils import cosine_similarity, load_embedding_payload
from common.core.config import settings
from common.utils.utils import AppLogUtil


def get_table_embedding(tables: list[dict], question: str):
    """
    是什么：get_table_embedding 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源需要的数据找出来，整理成后面好用的样子。
    """
    _list = []
    for table in tables:
        _list.append({"id": table.get('id'), "schema_table": table.get('schema_table'), "cosine_similarity": 0.0})

    if _list:
        try:
            text = [s.get('schema_table') for s in _list]

            model = EmbeddingModelCache.get_model()
            start_time = time.time()
            results = model.embed_documents(text)
            end_time = time.time()
            AppLogUtil.info(str(end_time - start_time))

            q_embedding = model.embed_query(question)
            for index in range(len(results)):
                item = results[index]
                _list[index]['cosine_similarity'] = cosine_similarity(q_embedding, item)

            _list.sort(key=lambda x: x['cosine_similarity'], reverse=True)
            _list = _list[:settings.TABLE_EMBEDDING_COUNT]
            # print(len(_list))
            AppLogUtil.info(json.dumps(_list))
            return _list
        except Exception:
            traceback.print_exc()
    return _list


def calc_table_embedding(
        tables: list[dict],
        question: str,
        stale_embedding_callback: Callable[[list[int]], None] | None = None,
):
    """
    是什么：calc_table_embedding 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    _list = []
    for table in tables:
        _list.append(
            {"id": table.get('id'), "schema_table": table.get('schema_table'), "embedding": table.get('embedding'),
             "cosine_similarity": 0.0, "table_name": table.get('table_name')})

    if _list:
        if any(not item.get('embedding') for item in _list):
            AppLogUtil.info("table embedding missing, return all visible tables")
            return _list
        try:
            parsed_embeddings = [load_embedding_payload(item.get('embedding')) for item in _list]
            stale_embeddings = [item for item in parsed_embeddings if not item.current]
            if stale_embeddings:
                AppLogUtil.info(
                    "table embedding stale, return all visible tables: "
                    + ",".join(sorted({item.reason for item in stale_embeddings}))
                )
                return _list

            # text = [s.get('schema_table') for s in _list]
            #
            model = EmbeddingModelCache.get_model()
            start_time = time.time()
            # results = model.embed_documents(text)
            # end_time = time.time()
            # AppLogUtil.info(str(end_time - start_time))
            q_embedding = model.embed_query(question)
            parsed_embeddings = [load_embedding_payload(item.get('embedding'), model) for item in _list]
            stale_embeddings = [item for item in parsed_embeddings if not item.current]
            if stale_embeddings:
                AppLogUtil.info(
                    "table embedding stale after model resolve, return all visible tables: "
                    + ",".join(sorted({item.reason for item in stale_embeddings}))
                )
                if stale_embedding_callback:
                    stale_embedding_callback([int(item.get("id")) for item in _list if item.get("id")])
                return _list

            dimension_mismatch_ids = [
                int(_list[index].get("id"))
                for index, item in enumerate(parsed_embeddings)
                if _list[index].get("id") and item.dim != len(q_embedding)
            ]
            if dimension_mismatch_ids:
                AppLogUtil.info(
                    f"table embedding dimension mismatch, queue refresh and return all visible tables: {dimension_mismatch_ids}"
                )
                if stale_embedding_callback:
                    stale_embedding_callback(dimension_mismatch_ids)
                return _list

            for index, item in enumerate(parsed_embeddings):
                _list[index]['cosine_similarity'] = cosine_similarity(q_embedding, item.vector or [])

            _list.sort(key=lambda x: x['cosine_similarity'], reverse=True)
            _list = _list[:settings.TABLE_EMBEDDING_COUNT]
            # print(len(_list))
            end_time = time.time()
            AppLogUtil.info(str(end_time - start_time))
            AppLogUtil.info(json.dumps([{"id": ele.get('id'), "schema_table": ele.get('schema_table'),
                                            "cosine_similarity": ele.get('cosine_similarity'), "table_name": ele.get('table_name')}
                                           for ele in _list]))
            return _list
        except Exception:
            traceback.print_exc()
    return _list
