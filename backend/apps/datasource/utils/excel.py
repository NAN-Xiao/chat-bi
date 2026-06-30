"""
脚本说明：这个脚本放数据源相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
import pandas as pd

FIELD_TYPE_MAP = {
    'int64': 'int',
    'int32': 'int',
    'float64': 'float',
    'float32': 'float',
    'datetime64': 'datetime',
    'datetime64[ns]': 'datetime',
    'object': 'string',
    'string': 'string',
    'bool': 'string',
}

USER_TYPE_TO_PANDAS = {
    'int': 'int64',
    'float': 'float64',
    'datetime': 'datetime64[ns]',
    'string': 'string',
}


def infer_field_type(dtype) -> str:
    """
    是什么：infer_field_type 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    dtype_str = str(dtype)
    return FIELD_TYPE_MAP.get(dtype_str, 'string')


def parse_excel_preview(save_path: str, max_rows: int = 10):
    """
    是什么：parse_excel_preview 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    sheets_data = []
    if save_path.endswith(".csv"):
        df = pd.read_csv(save_path, engine='c')
        fields = []
        for col in df.columns:
            fields.append({
                "fieldName": col,
                "fieldType": infer_field_type(df[col].dtype)
            })
        preview_df = df.head(max_rows).replace({pd.NA: None, float('nan'): None})
        preview_data = preview_df.to_dict(orient='records')
        sheets_data.append({
            "sheetName": "Sheet1",
            "fields": fields,
            "data": preview_data,
            "rows": len(df)
        })
    else:
        sheet_names = pd.ExcelFile(save_path).sheet_names
        for sheet_name in sheet_names:
            df = pd.read_excel(save_path, sheet_name=sheet_name, engine='calamine')
            fields = []
            for col in df.columns:
                fields.append({
                    "fieldName": col,
                    "fieldType": infer_field_type(df[col].dtype)
                })
            preview_df = df.head(max_rows).replace({pd.NA: None, float('nan'): None})
            preview_data = preview_df.to_dict(orient='records')
            sheets_data.append({
                "sheetName": sheet_name,
                "fields": fields,
                "data": preview_data,
                "rows": len(df)
            })
    return sheets_data
