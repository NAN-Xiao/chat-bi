# 知识裁决与 SQL 修复实施计划

> 执行方式：在当前链接工作树内按任务顺序执行，先测试后实现。

**Goal:** 修复 flam 20 题测试中的裁决超时、格式失败、可修复违规终止与裁决误判，并记录完整调用次数。

**Architecture:** 共用知识裁决服务返回经过 Schema 和原文证据校验的决策。普通规则违规交回原有校验和有限 SQL 修复；有证据的知识违规携带原文进入修复；真正冲突、无法判断与服务错误明确停止。当前授权边界独立校验，业务规则不能覆盖权限。

**Tech Stack:** Python、Pydantic、LangChain、SQLModel、LangGraph、pytest；真实浏览器复测。

**Spec:** 本任务用户已确认的修复方案，以及 `.codex-runtime/flam-ai-dashboard-20-browser-20260916/report.md`。

## 约束

- 工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`，初始工作区干净。
- 保持 LLM_REQUEST_TIMEOUT=120、LLM_TASK_MAX_WAIT_SECONDS=900、LLM_MAX_RETRIES=1；不叠加网络重试，格式重生成最多一次。
- 所有原文证据属于当前已授权知识上下文；不增加跨空间检索，不以超时或格式失败绕过校验。
- 不修复本轮另行发现的 MAU、兵种、科技、活动指标业务口径，避免混入本任务。

## Task 1：裁决协议、证据与格式恢复

Files: `backend/apps/knowledge_base/authority.py`、`backend/tests/test_knowledge_authority.py`。

- [x] 增加空响应后合法响应、连续非法响应、超时、伪造拒绝依据、同层冲突、非覆盖规则等失败测试并运行确认。
- [x] 新增结构化裁决类型与可修复知识违规异常，区分 not_applicable/resolved/invalid_output/conflict/uncertain。
- [x] 原文证据同时约束允许与拒绝；冲突需两条同层原文。协议失败最多重生成一次；服务失败保留错误类型，不额外重试。
- [x] 精简重复知识上下文但保留来源、作用域与完整规则；明确模板参数解析与权限校验职责。
- [x] 测试全部通过后检查错误与成功两侧的证据边界。

## Task 2：共享调用方与修复链路

Files: `backend/apps/chat/task/llm.py`、`backend/apps/chat/task/smart_qa_graph.py`、`backend/apps/chat/task/sql_repair.py`、`backend/apps/chat/task/assistant_workflow.py`、`backend/apps/analysis_assistant/api/analysis_assistant.py`；对应 pytest 文件。

- [x] 测试知识违规进入有限修复、修复后重新验证全部规则、真实冲突不执行 SQL。
- [x] AI看板与分析助手接入相同异常分类；修复消息包含文档来源、原文和规则，不回退到冲突旧规则。
- [x] 用户错误展示稳定中文信息和错误码，详细异常只进入服务端日志。

## Task 3：调用审计与补零误判

Files: `backend/apps/knowledge_base/review_audit.py`、`backend/apps/chat/models/chat_model.py`、`backend/apps/chat/curd/chat.py`、相关调用方；平台 Skill 后续迁移与测试。

- [x] 裁决每次逻辑调用记录 start/finish、模型、租户、数据源、record/request、Tokens、格式重试和状态；SDK重试另行计数，避免 double count。
- [x] 补零规则用表达式结构校验支持聚合表达式，不改变自定义正则的语义；通过幂等后续迁移更新平台 Skill，保留其余配置。
- [x] 用带匹配行、无匹配行、COUNT(*)、COUNT(column)、COALESCE 聚合与非零默认值验证，不以放宽所有正则绕过校验。

## Task 4：回归与真实页面

- [x] 执行知识裁决、SQL修复、工作流、分析助手及平台Skill相关测试。
- [x] 按本地运行手册更新当前工作树服务，核对超时配置与独立队列。
- [x] 先复测题11/51/61/91/96，再复测原20题；同一次题目的截图、SQL、日志关联记录，保留原失败证据。
- [x] 汇总修复内容、测试结果、剩余业务问题和工作树/分支；不自行提交或推送。

## 执行结果

480项相关后端测试通过，前端类型检查通过；原5道裁决失败题均在浏览器生成图表。整轮原20题全部达到终态，18题生成可视化组件，2题因缺少业务口径/投放成本未生成。完整记录见 `.codex-runtime/knowledge-review-fix-20260916/report.md`。

已备份并定向发布平台 Skill 281 的通用结构校验更新及当前模型的裁决专用配置，没有执行全量迁移。测试期间保留其他任务对题库及知识配置的并发调整，报告区分原始快照重放与当前页面复测。
