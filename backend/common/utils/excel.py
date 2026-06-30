import pandas as pd

def get_excel_column_count(file_path, sheet_name):
    """
    是什么：get_excel_column_count 是 backend/common/utils/excel.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：读取或查询通用工具相关数据，整理后返回给调用方。
    """
    df_temp = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        engine='calamine',
        header=0,
        nrows=0
    )
    return len(df_temp.columns)