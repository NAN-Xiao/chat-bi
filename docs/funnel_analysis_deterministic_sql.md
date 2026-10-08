# 漏斗分析确定性 SQL 编译

2026-09-29，工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。在原有留存、属性、间隔及独立编译 API 的本地改动上增量实现，未提交或推送。

界面约束更新：按用户“不要修改前端界面”的要求，已撤回本功能新增的提示控件、分组入口隐藏、按钮和等待文案调整。保留原有页面布局与控件；编译接口路由、筛选条件保存/恢复修复和校验逻辑继续保留。以下历史测试截图中的界面文案不代表当前界面。

## 行为与边界

漏斗配置通过现有 `/api/v1/dashboard/sql_compile` 生成 SQL；旧 AI 接口收到漏斗请求时也走同一个编译路径。上下文只读取授权元数据，不调用 LLM、Embedding、Data Skill 自动排序或模型修复。显式附加 Data Skill 仍返回错误；其他需要模型的分析不受影响。

- 支持当前工作空间授权默认事件表，2–10 步、步骤别名、重复事件、步骤/全局筛选、关联属性。
- 保留每个候选首步；按主体、首步时间、关联键维持路径，逐步取最早有效后续时间；最终按主体去重计数。
- 顺序延续 `>=`，重复事件允许同一时刻满足多步。改变为严格不同事件行属于新的产品协议。
- `duration` 相对首步计算，天为固定 86400 秒；`same_day` 使用业务时区自然日。范围字段用于看板范围，步骤时间来自明确的 event_time 元数据，不用分区日期推断事件顺序。
- 全部事件受看板日期参数约束；不自动越过结束日期扩展观察期。
- 关联键 NULL 保留首步样本，后续不与 NULL 匹配。步骤结果始终为六列和完整 N 行；无样本人数为 0，分母为 0 的比率为 NULL；比例为 0–1。
- 非法输入、越权字段、缺失角色/编码、未知事件、伪造 JSON 路径、公式、近似模式和普通分组明确拒绝。
- 物理字段和事件参数分别解析。同名 JSON 参数不能替换物理事件时间、事件名、日期范围或强制表筛选。统一关联参数先验证所选事件的映射，再按其他步骤的明确字典映射解析。
- 保存的非法窗口和关联开关阻止生成；默认值只用于新建。已知旧格式只能在新字段缺席且旧值有效时迁移，不截断非法窗口、不覆盖显式当前值。
- 保留原有普通分组入口；不支持的分组配置通过现有校验提示报告，可使用原有分组控件移除。保留不足两步的旧步骤，显示错误而不是用三个空步骤覆盖。
- 保留请求取消、60 秒编译预算、65 秒客户端超时及零自动重放。预览仍是独立 SQL 执行流程；用户行权限继续使用既有 `deny_on_overlap`，不批量改写已保存 SQL。

## 主要代码

- `backend/apps/dashboard/crud/funnel_sql_plan.py`：原始输入校验、事件/物理字段解析和不可变查询计划。
- `backend/apps/dashboard/crud/funnel_sql_compiler.py`：固定逐步 CTE、主体计数和比率。
- `backend/apps/dashboard/crud/funnel_sql_validation.py`：完整计划 AST/日期 token 一致性；保留既有独立 SQL 校验工具。
- `backend/apps/dashboard/crud/ai_sql_generator.py`：已有上下文、编译、校验、修复路由的漏斗接入。
- 前端 `DashboardSqlEditor.vue`、`funnelAnalysis.ts`、`FunnelWindowPicker.vue`：独立编译调用、严格恢复及原有交互中的配置校验，不新增界面控件。

模板一致性不用于证明算法正确；独立结果样例和原生数据库执行验证算法。未引入原生 window_funnel 优化、通用编译框架、跨表模型或新的日期 UI。

## 本轮验证

- 独立审查提出 4 项重要问题；分别补失败回归后修复：其他表时间映射误拦截、JSON 参数覆盖物理字段、统一关联参数的真实 UI payload、非法关联开关恢复。
- 审查修复后的计划/编译器/graph：72 passed；前端相关行为测试 39 passed、严格恢复源码断言单独 1 passed，类型检查通过。
- 全量后端（提供三类 PostgreSQL 测试 DSN）：2791 passed、2 skipped、7 failed。
- PostgreSQL 使用 READ ONLY 事务和 VALUES CTE，覆盖独立计数/比率、后续首步成功、路径隔离、空样本、十步、筛选、秒/毫秒/原生时间戳、时区和窗口边界；未创建或修改业务表。此前本轮原生漏斗＋留存定向运行 48 passed，全量又运行这些测试。
- 编译/解析覆盖 PostgreSQL、MySQL、StarRocks、Doris。真实执行覆盖 PostgreSQL 和当前 gig 的 MySQL 兼容实例；该实例 `SELECT VERSION()` 返回 `5.6.16-log`，不能据此声称普通 MySQL 5.6 支持相同 CTE 能力。没有独立验证所有兼容发行版或其他两个引擎。

后端 7 个失败与开始前留存实施文档记录的失败同名：platform template snapshot 替身缺少 exec、两项 revenue 旧成熟窗口夹具、Data Skill 校验异常预期、Embedding JSON 文本断言、Embedding 默认模型预期、全量运行中的敏感配置解密状态问题。没有把全量宣称为全绿，也没有扩展修改这些无关模块。

前端旧 `DashboardSqlEditor.analysis-model.test.mjs` 中 13 项已记录的组件拆分源码断言仍不在本任务修复范围；本轮新增的一项旧恢复函数名断言已同步至严格恢复函数，并单独通过。

## 浏览器验收与执行证据

在当前 gig 工作空间新建独立看板“漏斗编译器验收”，ID `5fa0385e44434a50b7ee876f5ed84475`，未改动已有业务看板。

实际页面操作通过：

1. 缺少步骤事件时明确拒绝；开启关联属性但未选字段时明确拒绝并清除旧预览。
2. 两步重复事件、1 天经过时长：2 行、6 列，各步 37 个主体；相邻比例 1、流失率 0，符合非严格顺序协议。
3. 改为当天自然日，重新编译和预览成功。
4. 加入 JSON 媒体来源关联属性，执行成功。
5. 扩展到 10 步重复事件＋当天＋JSON 关联属性，返回 10 行、6 列；十步保留，无步骤丢失。
6. 切换明细表后重新生成，结果保留用户选择的图表类型；应用、保存、重新打开后表格和结果正常。

日志显示所有上述请求调用 `/sql_compile`，`llm_calls=0`、`http_attempts=0`、`network_retries=0`；无 `/embeddings` 请求。

- 两步编译约 250–281ms；未缓存预览约 1.2–2.7s。
- 十步编译约 875ms；未缓存预览约 3.2s。不是压力测试或任意数据量延迟承诺。
- 同一条已绑定日期参数的十步查询已执行 EXPLAIN，返回计划输出估计 10 行。CTE 多次引用会在兼容引擎计划中展开，后续大样本性能优化应保留候选路径，不能 LIMIT/去掉首步或近似计数。
- 保存重开截图：`.codex-runtime/funnel-compiler-saved.png`。
- 实际查询：`.codex-runtime/funnel-browser-compiled.sql`；EXPLAIN 摘要：`.codex-runtime/funnel-browser-explain.txt`。

非法持久化配置、权限撤销、步骤筛选及精度边界由自动化测试覆盖；未通过改变真实用户权限或破坏工作空间元数据来做浏览器负面测试。未声明这些破坏性场景已经手工实测。

本地前端 5173、API 8000、MCP 8001、一个 Worker 已重启加载当前工作树；API/Worker 同用 `local-DONGJINCHAO-release_1.3.0`。重启前当前分支已 fast-forward-only 拉取且无新提交。核对运行配置 `LLM_REQUEST_TIMEOUT=180`、`LLM_TASK_MAX_WAIT_SECONDS=900`、`LLM_MAX_RETRIES=1`。

测试日志及本轮开始前的改动快照保存在本计划专属 `.superpowers/sdd/2026-09-29-retention-funnel-sql-compiler-incremental/`，未将运行数据或数据源凭据提交入库。
