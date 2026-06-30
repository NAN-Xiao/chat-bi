"""
脚本说明：这个脚本放数据库连接相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
# 作者：Junjun
# 日期：2025/9/9

import json
from base64 import b64encode

import requests
from elasticsearch import Elasticsearch

from apps.datasource.models.datasource import DatasourceConf
from common.error import SingleMessageError


def get_es_auth(conf: DatasourceConf):
    """
    是什么：get_es_auth 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    username = f"{conf.username}"
    password = f"{conf.password}"

    credentials = f"{username}:{password}"
    encoded_credentials = b64encode(credentials.encode()).decode()

    return {
        "Content-Type": "application/json",
        "Authorization": f"Basic {encoded_credentials}"
    }


def get_es_connect(conf: DatasourceConf):
    """
    是什么：get_es_connect 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    es_client = Elasticsearch(
        [conf.host],  # ES 地址
        basic_auth=(conf.username, conf.password),
        verify_certs=conf.ssl,
        compatibility_mode=True,
        headers=get_es_auth(conf)
    )
    return es_client


# 获取表列表
def get_es_index(conf: DatasourceConf):
    """
    是什么：get_es_index 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    es_client = get_es_connect(conf)
    indices = es_client.cat.indices(format="json")
    res = []
    if indices is not None:
        for idx in indices:
            index_name = idx.get('index')
            desc = ''
            # 获取映射信息
            mapping = es_client.indices.get_mapping(index=index_name)
            mappings = mapping.get(index_name).get("mappings")
            if mappings.get('_meta'):
                desc = mappings.get('_meta').get('description')
            res.append((index_name, desc))
    return res


# 获取字段列表
def get_es_fields(conf: DatasourceConf, table_name: str):
    """
    是什么：get_es_fields 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    es_client = get_es_connect(conf)
    index_name = table_name
    mapping = es_client.indices.get_mapping(index=index_name)
    properties = mapping.get(index_name).get("mappings").get("properties")
    res = []
    if properties is not None:
        for field, config in properties.items():
            field_type = config.get("type")
            desc = ''
            if config.get("_meta"):
                desc = config.get("_meta").get('description')

            if field_type:
                res.append((field, field_type, desc))
            else:
                # 对象、嵌套等类型。
                res.append((field, ','.join(list(config.keys())), desc))
    return res


# def get_es_data(conf: DatasourceConf, sql: str, table_name: str):
#     r = requests.post(f"{conf.host}/_sql/translate", json={"query": sql})
#     if r.json().get('error'):
#         print(json.dumps(r.json()))
#
#     es_client = get_es_connect(conf)
#     response = es_client.search(
#         index=table_name,
#         body=json.dumps(r.json())
#     )
#
#     # print(response)
#     fields = get_es_fields(conf, table_name)
#     res = []
#     for hit in response.get('hits').get('hits'):
#         item = []
#         if 'fields' in hit:
#             result = hit.get('fields')  # {'title': ['Python'], 'age': [30]}
#             for field in fields:
#                 v = result.get(field[0])
#                 item.append(v[0]) if v else item.append(None)
#             res.append(tuple(item))
#             # print(hit['fields']['title'][0])
#         # elif '_source' in hit:
#         #     print(hit.get('_source'))
#     return res, fields


def get_es_data_by_http(conf: DatasourceConf, sql: str):
    """
    是什么：get_es_data_by_http 是一个可以复用的小步骤，负责数据库连接相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
    """
    url = conf.host
    while url.endswith('/'):
        url = url[:-1]

    host = f'{url}/_sql?format=json'

    # 安全改进：启用 SSL 证书校验。
    # 注意：生产环境中应始终设置 verify=True，或提供 CA 证书包路径。
    # If using self-signed certificates, provide the cert path: verify='/path/to/cert.pem'
    # verify_ssl = True if not url.startswith('https://localhost') else False

    response = requests.post(
        host,
        data=json.dumps({"query": sql}),
        headers=get_es_auth(conf),
        verify=conf.ssl,
        timeout=30  # 添加超时时间，避免请求挂起。
    )

    # print(response.json())
    res = response.json()
    if res.get('error'):
        raise SingleMessageError(json.dumps(res))
    fields = res.get('columns')
    result = res.get('rows')
    return result, fields
