"""
脚本说明：这个脚本放通用工具相关的代码，把具体功能拆成清楚的函数和类供其他地方使用。
"""
from decimal import Decimal

import pandas as pd

from apps.chat.models.chat_model import AxisObj


class DataFormat:
    """
    类说明：DataFormat 把通用工具相关的数据和行为放在一起，便于其他代码直接复用。
    """
    @staticmethod
    def safe_convert_to_string(df):
        """
        是什么：DataFormat.safe_convert_to_string 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        df_copy = df.copy()

        for col in df_copy.columns:
            # 使用map避免ambiguous truth value问题
            df_copy[col] = df_copy[col].map(
                # 关键：在数字字符串前添加零宽空格，阻止pandas的自动格式化
                lambda x: "" if pd.isna(x) else "\u200b" + str(x)
            )

        return df_copy

    @staticmethod
    def normalize_qualified_sql_column_keys(row: dict) -> dict:
        """
        是什么：DataFormat.normalize_qualified_sql_column_keys 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        if not row:
            return row
        out = dict(row)
        for k, v in row.items():
            ks = str(k)
            if "." not in ks:
                continue
            short = ks.rsplit(".", 1)[-1]
            if short not in out:
                out[short] = v
        return out

    @staticmethod
    def normalize_qualified_sql_column_keys_in_object_array(obj_array: list) -> list:
        """
        是什么：DataFormat.normalize_qualified_sql_column_keys_in_object_array 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        if not obj_array:
            return obj_array
        return [
            DataFormat.normalize_qualified_sql_column_keys(obj) if isinstance(obj, dict) else obj
            for obj in obj_array
        ]

    @staticmethod
    def convert_large_numbers_in_object_array(obj_array, int_threshold=1e15, float_threshold=1e10):
        """
        是什么：DataFormat.convert_large_numbers_in_object_array 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """

        def format_float_without_scientific(value):
            """
            是什么：DataFormat.format_float_without_scientific 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
            谁调用：外层函数 convert_large_numbers_in_object_array 跑到对应步骤时会调用它。
            做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
            """
            if value == 0:
                return "0"
            formatted = str(Decimal(str(value)))
            if '.' in formatted:
                formatted = formatted.rstrip('0').rstrip('.')
            return formatted

        def process_object(obj):
            """
            是什么：DataFormat.process_object 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
            谁调用：外层函数 convert_large_numbers_in_object_array 跑到对应步骤时会调用它。
            做了什么：把通用工具的主要流程跑起来，一步步调用需要的处理。
            """
            if not isinstance(obj, dict):
                return obj

            processed_obj = {}
            for key, value in obj.items():
                if isinstance(value, (int, float)):
                    # 只转换大数字
                    if isinstance(value, int) and abs(value) >= int_threshold:
                        processed_obj[key] = str(value)
                    elif isinstance(value, float) and (abs(value) >= float_threshold or abs(value) < 1e-6):
                        processed_obj[key] = format_float_without_scientific(value)
                    else:
                        processed_obj[key] = value
                elif isinstance(value, dict):
                    # 处理嵌套对象
                    processed_obj[key] = process_object(value)
                elif isinstance(value, list):
                    # 处理对象中的数组
                    processed_obj[key] = [process_item(item) for item in value]
                else:
                    processed_obj[key] = value
            return processed_obj

        def process_item(item):
            """
            是什么：DataFormat.process_item 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
            谁调用：外层函数 convert_large_numbers_in_object_array 跑到对应步骤时会调用它。
            做了什么：把通用工具的主要流程跑起来，一步步调用需要的处理。
            """
            if isinstance(item, dict):
                return process_object(item)
            return item

        return [process_item(obj) for obj in obj_array]

    @staticmethod
    def convert_object_array_for_pandas(column_list: list, data_list: list):
        """
        是什么：DataFormat.convert_object_array_for_pandas 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        _fields_list = []
        for field_idx, field in enumerate(column_list):
            _fields_list.append(field.name)

        md_data = []
        for inner_data in data_list:
            _row = []
            for field_idx, field in enumerate(column_list):
                value = inner_data.get(field.value)
                _row.append(value)
            md_data.append(_row)
        return md_data, _fields_list

    @staticmethod
    def convert_data_fields_for_pandas(chart: dict, fields: list, data: list):
        """
        是什么：DataFormat.convert_data_fields_for_pandas 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        _fields = {}
        if chart.get('columns'):
            for _column in chart.get('columns'):
                if _column:
                    _fields[_column.get('value')] = _column.get('name') or _column.get('value')
        if chart.get('axis'):
            if chart.get('axis').get('x'):
                _fields[chart.get('axis').get('x').get('value')] = (
                    chart.get('axis').get('x').get('name') or chart.get('axis').get('x').get('value')
                )
            if chart.get('axis').get('y'):
                # _fields[chart.get('axis').get('y').get('value')] = chart.get('axis').get('y').get('name')
                y_axis = chart.get('axis').get('y')
                if isinstance(y_axis, list):
                    # y轴是数组的情况（多指标字段）
                    for y_item in y_axis:
                        if isinstance(y_item, dict) and 'value' in y_item:
                            _fields[y_item.get('value')] = y_item.get('name') or y_item.get('value')
                elif isinstance(y_axis, dict):
                    # y轴是对象的情况（单指标字段）
                    if 'value' in y_axis:
                        _fields[y_axis.get('value')] = y_axis.get('name') or y_axis.get('value')
            if chart.get('axis').get('series'):
                _fields[chart.get('axis').get('series').get('value')] = (
                    chart.get('axis').get('series').get('name') or chart.get('axis').get('series').get('value')
                )
        _column_list = []
        for field in fields:
            _column_list.append(
                AxisObj(name=field if not _fields.get(field) else _fields.get(field), value=field))

        md_data, _fields_list = DataFormat.convert_object_array_for_pandas(_column_list, data)

        return md_data, _fields_list

    @staticmethod
    def format_pd_data(column_list: list, data_list: list, col_formats: dict = None):
        # 预处理数据并记录每列的格式类型
        # 格式类型：'text'（文本）、'number'（数字）、'default'（默认）
        """
        是什么：DataFormat.format_pd_data 是 DataFormat 里的一个步骤，帮它完成通用工具相关的一件事。
        谁调用：它不依赖实例状态，其他代码需要这个小能力时会调用它。
        做了什么：把通用工具的原始内容拆开、转换或整理，变成程序更好处理的格式。
        """
        _fields_list = []

        if col_formats is None:
            col_formats = {}
        for field_idx, field in enumerate(column_list):
            _fields_list.append(field.name)
            col_formats[field_idx] = 'default'  # 默认不特殊处理

        data = []

        for _data in data_list:
            _row = []
            for field_idx, field in enumerate(column_list):
                value = _data.get(field.value)
                if value is not None:
                    # 检查是否为数字且需要特殊处理
                    if isinstance(value, (int, float)):
                        # 整数且超过15位 → 转字符串并标记为文本列
                        if isinstance(value, int) and len(str(abs(value))) > 15:
                            value = str(value)
                            col_formats[field_idx] = 'text'
                        # 小数且超过15位有效数字 → 转字符串并标记为文本列
                        elif isinstance(value, float):
                            decimal_str = format(value, '.16f').rstrip('0').rstrip('.')
                            if len(decimal_str) > 15:
                                value = str(value)
                                col_formats[field_idx] = 'text'
                        # 其他数字列标记为数字格式（避免科学记数法）
                        elif col_formats[field_idx] != 'text':
                            col_formats[field_idx] = 'number'
                _row.append(value)
            data.append(_row)

        return data, _fields_list, col_formats
