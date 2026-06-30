"""
脚本说明：这个脚本放数据库连接相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
# 作者：Junjun
# 日期：2025/7/16

from enum import Enum
from typing import List

from common.utils.utils import equals_ignore_case


class ConnectType(Enum):
    """
    类说明：ConnectType 收拢数据库连接里固定的可选值，避免代码里到处写零散字符串。
    """
    sqlalchemy = ('sqlalchemy')
    py_driver = ('py_driver')

    def __init__(self, type_name):
        """
        是什么：ConnectType.__init__ 是 ConnectType 里的一个步骤，帮它完成数据库连接相关的一件事。
        谁调用：创建 ConnectType 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.type_name = type_name


class DB(Enum):
    """
    类说明：DB 把数据库连接相关的数据和行为放在一起，便于其他代码直接复用。
    """
    excel = ('excel', 'Excel/CSV', '"', '"', ConnectType.sqlalchemy, 'PostgreSQL', [])
    redshift = ('redshift', 'AWS Redshift', '"', '"', ConnectType.py_driver, 'AWS_Redshift', [])
    ck = ('ck', 'ClickHouse', '"', '"', ConnectType.sqlalchemy, 'ClickHouse', [])
    dm = ('dm', '达梦', '"', '"', ConnectType.py_driver, 'DM', [])
    doris = ('doris', 'Apache Doris', '`', '`', ConnectType.py_driver, 'Doris', [])
    es = ('es', 'Elasticsearch', '"', '"', ConnectType.py_driver, 'Elasticsearch', [])
    kingbase = ('kingbase', 'Kingbase', '"', '"', ConnectType.py_driver, 'Kingbase', [])
    sqlServer = ('sqlServer', 'Microsoft SQL Server', '[', ']', ConnectType.sqlalchemy, 'Microsoft_SQL_Server', [])
    mysql = ('mysql', 'MySQL', '`', '`', ConnectType.sqlalchemy, 'MySQL', ['local_infile'])
    oracle = ('oracle', 'Oracle', '"', '"', ConnectType.sqlalchemy, 'Oracle', [])
    pg = ('pg', 'PostgreSQL', '"', '"', ConnectType.sqlalchemy, 'PostgreSQL', [])
    starrocks = ('starrocks', 'StarRocks', '`', '`', ConnectType.py_driver, 'StarRocks', [])
    hive = ('hive', 'Apache Hive', '`', '`', ConnectType.py_driver, 'Hive', [])

    def __init__(self, type, db_name, prefix, suffix, connect_type: ConnectType, template_name: str,
                 illegalParams: List[str]):
        """
        是什么：DB.__init__ 是 DB 里的一个步骤，帮它完成数据库连接相关的一件事。
        谁调用：创建 DB 这个对象时，Python 会先调用它。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.type = type
        self.db_name = db_name
        self.prefix = prefix
        self.suffix = suffix
        self.connect_type = connect_type
        self.template_name = template_name
        self.illegalParams = illegalParams

    @classmethod
    def get_db(cls, type, default_if_none=False):
        """
        是什么：DB.get_db 是 DB 里的一个步骤，帮它完成数据库连接相关的一件事。
        谁调用：需要通过类本身做这件事时，代码会调用它。
        做了什么：把数据库连接需要的数据找出来，整理成后面好用的样子。
        """
        for db in cls:
            """ if db.type == type: """
            if equals_ignore_case(db.type, type):
                return db
        if default_if_none:
            return DB.pg
        else:
            raise ValueError(f"Invalid db type: {type}")
