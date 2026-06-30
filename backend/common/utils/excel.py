"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import pandas as pd

def get_excel_column_count(file_path, sheet_name):
    """
    是什么：get_excel_column_count 是一个可以复用的小步骤，负责通用工具相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把通用工具需要的数据找出来，整理成后面好用的样子。
    """
    df_temp = pd.read_excel(
        file_path,
        sheet_name=sheet_name,
        engine='calamine',
        header=0,
        nrows=0
    )
    return len(df_temp.columns)