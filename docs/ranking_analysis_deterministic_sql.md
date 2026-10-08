# 排行榜固定模板 SQL 编译

2026-09-30，工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。

## 实现

现有页面、请求及结果字段不变。`/dashboard/ai_sql_generate` 后端分流排行榜到配置编译，`/dashboard/sql_compile` 同样支持。成功、失败、修复及说明路径不创建或调用 LLM。

- `ranking_sql_plan.py`：授权元数据、事件/JSON/真实类型/时间/筛选校验及不可变查询计划。
- `ranking_sql_compiler.py`：固定 CTE 结构和 PostgreSQL、MySQL、StarRocks、Doris 方言。
- `ranking_sql_validation.py`：完整查询 AST、日期 token 与授权计划比较。
- `ranking_execution_contract.py`：签名绑定 SQL、租户、数据源、元数据；公共执行校验并剥离内部属性校验列。
- 公共协议分派、SqlEngineResult 及看板缓存保留验证证据；查询失败清除旧成功缓存，禁止过期回退。

## 固定语义

1. 主事件决定主体集合，排除 NULL 主体；每个指标独立按主体聚合再连接，避免明细乘法重复。支持 COUNT、COUNT DISTINCT、SUM、AVG、MIN、MAX。
2. 无匹配附加事件时次数/去重数为 0，其他聚合保留 NULL。主指标 NULL 无论升降序都排最后。
3. default/skip/dense 分别为 ROW_NUMBER/RANK/DENSE_RANK；只有 default 把主体加入排名窗口的次级排序。最终输出按名次、主体排序。
4. 属性取自主事件范围。主体与完整属性组合 DISTINCT 后必须唯一，NULL 与非 NULL 视为不同组合。多值触发 `RANKING_PROPERTY_CONFLICT`；不使用 MAX/MIN/ANY_VALUE 任取，不拆分主体。全局 guard 标记所有行，避免预览截断隐藏冲突。
5. 时间、全局 AND/OR、工作空间强制筛选应用到所有来源。YYYYMMDD/DATE 包含结束日；TIMESTAMP 为排他结束边界。类型/编码不匹配明确拒绝。无时区时间需声明业务时区；MySQL TIMESTAMP 当前明确拒绝，可用明确业务时区 DATETIME 或 epoch。
6. 当前同表事件支持，未配置跨表关联拒绝。普通分组、公式、近似计算明确拒绝，不改变固定主体粒度。
7. JSON 来源、路径、表达式、参数所属事件及数值类型来自服务端。物理文本列不能通过客户端类型或语义标签变成数值。
8. 固定结果列保持 `rank`、`ranking_entity`、`ranking_value`、`simultaneous_metric_N`、`ranking_property_N`。超过服务端行数上限明确报错，内部 guard 不展示。

已有保存 SQL 不批量改写；重新生成使用编译器。排行榜编译拥有独立 60 秒生命周期，保留取消、超时及权限控制。

## 验证

- 排行榜及 SQL 契约定向回归 **121 passed**，含排行榜 72 项及 **13 项真实 PostgreSQL 只读 VALUES**。
- 全后端 **3311 passed、162 skipped、6 failed**。一个源码路径测试从仓库根目录重跑通过，其余五项用修改前模块复现。
- 五项既有失败：平台模板快照、Data Skill 结构异常、嵌入 schema JSON 表达式、默认 embedding 模型、间隔模型全局筛选。堆栈及基线证据在 `.codex-runtime/ranking-20260930/`。
- 独立审查发现日期字面量和缓存失效问题，先补失败测试再修复；复审无剩余 P1/P2。
- 前端 **798 文件 SHA256 一致，新增 0**。本次未修改前端页面内容或源码。
- 本地前端/API/MCP/Worker 正常，API/Worker 共用 `local-DONGJINCHAO-release_1.3.0`；模型配置核对为 `180 / 900 / 1`。
- PostgreSQL 有真实合成数据执行，授权 MySQL 兼容业务源有真实浏览器验收。StarRocks/Doris 只有语法和参数协议测试，未声明真实引擎验收。

浏览器记录见 `ranking_compiler_browser_test_20260930.md`。
