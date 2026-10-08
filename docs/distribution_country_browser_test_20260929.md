# 分布分析：国家主体与 UserRegister 内置浏览器验收

日期：2026-09-29。用户明确指定 **以国家字段作为分析主体**，事件为 `UserRegister`。本轮使用 Codex 内置浏览器实际配置、生成、预览、保存和重新加载，没有注入组件状态或伪造接口响应。

## 环境与配置

- 工作树：`D:/AIWork6/release_1.3.0`；分支：`release/release_1.3.0`。
- 工作空间 gig，已授权数据源 12。实际生成并保存的主体表达式为 `JSON_UNQUOTE(JSON_EXTRACT(currentinfo, '$.country'))`；事件为 UserRegister，指标为次数，无额外分组、筛选或同时展示。
- 时间范围：2026-09-01 至 2026-09-28。此窗口内 UserRegister 最后匹配日期为 2026-09-25；不将无事件日期伪造成有主体。
- 新建独立看板“分布编译验收-国家-UserRegister”，报表标题“国家主体 · UserRegister 次数分布”。
- 已保存的看板地址：`http://127.0.0.1:5173/#/dashboard/index?resourceId=7474a74cdfdf46a296947f31a80c26ff&dashboardMode=my`。
- 按 runbook 拉取当前分支（Already up to date）后重启本地前端、API、MCP、Worker。API/Worker 队列为 `local-DONGJINCHAO-release_1.3.0`，三个端口均监听 `0.0.0.0`；验证超时为 180/900/1。未操作远程服务进程。

## 发现并修复的问题

首次浏览器计算被拒绝：`time.field：日期参数与字段声明的 encoding 不一致。`

根因：当前工作空间分区日期元数据使用合法格式写法 `yyyyMMdd`，新分布编译器仅接受全小写 `yyyymmdd`。其他日期转换路径已经使用显式 YYYYMMDD 参数解析，此处的大小写比较错误阻断了合法配置。

修复仅位于 `distribution_sql_plan.py` 的日期编码校验：比较日历格式时统一大小写，不改变元数据，不替换时间字段，也不放宽 epoch 等不同编码的拒绝规则。新增 PostgreSQL/MySQL × 数字/文本日期 × 三种大小写的回归覆盖；修复前 8 项失败、5 项通过（含原冲突编码用例），修复后相关计划、编译、graph/API 共 **127 passed**。

## 浏览器结果

| 用例 | 区间设置 | 编译耗时 | 预览接口耗时 | 结果 |
| --- | --- | --- | --- | --- |
| D01 | 自动区间 | 296 ms | 1603 ms | 15 行、6 个原始结果列，成功 |
| D02 | 离散数字 | 218 ms | 1040 ms | 15 行、6 个原始结果列，成功 |
| D03 | 自定义 0、1、5、10、50 | 235 ms | 846 ms | 15 行、6 个原始结果列，成功 |

三次请求均由现有页面发往 `/dashboard/ai_sql_generate`，后端转入确定性编译。三次日志均为 `status=success, llm_calls=0, http_attempts=0, network_retries=0`；页面保留原 AI limits 查询，不等同于模型调用。

D03 应用到画布并保存；刷新编辑页后图表标题和固定日期范围保留，从看板页重新加载后仍显示该图表。最终保留自定义区间配置。

## 数据含义核对

通过现有 SQL engine，以当前用户真实工作空间上下文及 `deny_on_overlap` 权限策略，对相同授权事件源、日期和工作空间强制条件执行独立只读聚合：

- 15 个有事件的“日期 × 国家”记录；国家值只有 CN。
- 合计 203 条 UserRegister 事件；最后匹配日期为 2026-09-25。
- 例如 09-01 的注册次数为 3，落入自定义 `[1,5)`；09-02 为 6，落入 `[5,10)`。每天参与该事件的国家主体数均为 1。

因此页面现有“全部用户”列里的 **1 表示 1 个国家主体，不是 1 个注册用户**。用户要求不修改前端，本轮保留该原有表头。分布表按国家主体的事件次数分桶，不把国家改成普通分组，也不暗中换回用户 ID。

## 证据与范围

证据目录：`.codex-runtime/distribution-country-20260929/`：

- `D01-auto.sql`、`D02-discrete.sql`、`D03-custom.sql`：从浏览器 SQL 文本框读取的实际模板。
- `cases.json`：三种配置及可见表格证据。
- `independent-country-counts.json`、`independent-check.log`、`checks.txt`：受权限检查的独立有界聚合及核对。
- `backend-8000.err.log/out.log`：实际编译、执行耗时和零模型调用证据。
- `encoding-before.jpg`、`custom-preview.jpg`、`custom-preview-detail.jpg`、`saved-board.jpg`：错误、结果及保存后页面截图。

前端 805 个受跟踪/非忽略文件与实施前内容快照一致，无新增、删除或源码修改。代码变更仅为本次通用日期编码校验及其后端测试；未提交或推送。本次并未覆盖所有事件、所有国家属性来源、全部聚合方式或所有数据库发行版。
