import pyodbc
from apps.datasource.models.datasource import DatasourceConf

def get_connection(conf: DatasourceConf):
    conn_str = (
        "DRIVER={MySQL ODBC 9.3 Unicode Driver};"  # todo driver config
        f"SERVER={conf.host};"
        f"DATABASE={conf.database};"
        f"UID={conf.username};"
        f"PWD={conf.password};"
        f"PORT={conf.port};"
    )
    conn = None
    try:
        conn = pyodbc.connect(conn_str)
        print("Connect Success")
        return conn
    except pyodbc.Error as e:
        print(f"Connect Fail：{e}")
        raise e
    finally:
        if conn is not None:
            conn.close()
