# 间隔分析确定性 SQL

间隔分析使用工作空间事件配置编译 SQL，不调用 LLM 生成或修复 SQL。编译结果仍经过只读、日期参数、权限字段、结果契约和起点日期来源校验；配置错误直接返回明确提示。

## 配置要求

- 起点事件和终点事件必须来自同一授权事件明细表，并使用同一个事件名字段。
- 工作空间事件元数据必须唯一声明 `event_time`，并声明 `datetime`、`epoch_seconds` 或 `epoch_milliseconds` 编码。
- `event_id` 或 `event_sequence` 可以作为同一主体同一时间下的附加稳定排序键；没有该配置时仍按事件时间生成间隔 SQL。
- 主体、起终事件筛选、全局筛选、关联属性和分组字段都必须来自当前授权 Schema。

## 配对和结果

编译器使用主体及关联属性分区，在事件时间以及已配置的附加排序键上使用 `LAG`，只保留相邻的“起点 -> 终点”配对。没有附加排序键时仅按事件时间排序。间隔按秒计算，保留 `0 <= interval_seconds <= limitSeconds`，分组字段从起点行传递。跨自然日配对归到起点日期；毫秒事件时间保留小数秒精度。

连续日粒度使用非递归日期骨架，日期集合 `LEFT JOIN` 聚合结果；计数缺失补零，时长统计保持 NULL。MySQL 兼容方言使用排序插值计算分位数，AnalyticDB 使用 `APPROX_PERCENTILE`，StarRocks/Doris 使用 `PERCENTILE_APPROX`，PostgreSQL 使用 `PERCENTILE_CONT`。

## 当前数据源提示

现有 datasource 10 的事件元数据已声明 `event.time` 为毫秒时间字段，但尚未配置 `event_id` 或 `event_sequence`。间隔分析仍可生成 SQL；如果同一主体存在相同事件时间，未配置附加排序键时数据库的同时间行顺序不保证稳定。
