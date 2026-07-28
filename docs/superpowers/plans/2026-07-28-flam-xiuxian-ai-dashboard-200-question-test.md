# flam 与修仙 AI 看板 200 题测试实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于当前推荐看板，为 `flam` 和`修仙`空间各生成 100 个问题，通过真实 AI 看板 UI 完成测试，并交付逐题可审计结果。

**Architecture:** 测试分为只读盘点、题目夹具、浏览器提交、数据库结果同步和报告分类五层。两个空间分阶段运行，同一会话严格串行，浏览器通道不超过本地 Worker 并发上限；UI 是唯一提交入口，数据库只用于只读核验和结果审计。

**Tech Stack:** Windows PowerShell、ChatBI 本地四服务、内置浏览器控制、Python 3、PostgreSQL、JSON、Markdown

## Global Constraints

- `flam` 排除名称为“运营总览”的入口及其内容，其他当前推荐入口均需检查。
- `修仙`覆盖全部当前推荐入口。
- 两个空间各生成 100 个唯一问题，每个空间采用 20 个会话、每会话 5 个连续问题。
- 时间范围混合昨天、近 3/7/14/21/30/60/90 天、本周、本月、指定区间和不限定时间。
- 200 个问题必须通过真实 AI 看板 UI 提交，不能用接口直调替代。
- 同一会话内严格串行，浏览器执行通道最多 4 个，两个空间不得混跑。
- 不修改推荐看板、Data Skill、数据源、权限、业务数据或业务代码。
- 所有运行产物写入 `.codex-runtime`，不纳入 Git 提交。
- 完成率、有效回答率、业务数据返回率和图表成功率必须分别报告。

---

### Task 1: 验证本地栈并盘点推荐看板

**Files:**
- Create: `.codex-runtime/ai-dashboard-recommended-inventory-2026-07-28.json`
- Create: `.codex-runtime/ai-dashboard-recommended-inventory-2026-07-28.md`
- Read: `tools/stack-local.ps1`
- Read: `tools/worker-local.ps1`

**Interfaces:**
- Consumes: 仓库根目录 `.env`、系统数据库 `core_dashboard` 和 `core_datasource`。
- Produces: 两个空间的推荐入口清单，字段为 `workspace`、`tenant_id`、`dashboard_id`、`name`、`node_type`、`source`、`datasource_id`、`excluded`、`ui_status`、`chart_titles`。

- [ ] **Step 1: 计算独立队列并检查四服务状态**

Run:

```powershell
$workspaceRoot=(Resolve-Path '.').Path
$workspaceSlug=Split-Path -Leaf $workspaceRoot
$computerSlug=if($env:COMPUTERNAME){$env:COMPUTERNAME}else{'local'}
$queueName="local-$computerSlug-$workspaceSlug" -replace '[^A-Za-z0-9_.-]','-'
.\tools\stack-local.ps1 -Action status -BackendPorts 8000 -QueueName $queueName -StartMcp -SkipDatabase -SkipRedis -SkipNginx
.\tools\worker-local.ps1 -Action status -Workers 1 -QueueName $queueName
Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess
```

Expected: API `8000`、MCP `8001`、前端 `5173` 均监听，Worker 使用以 `local-` 开头且不等于 `default` 的同一队列。

- [ ] **Step 2: 执行 HTTP 与模型配置健康检查**

Run:

```powershell
Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 10 | Select-Object StatusCode
try { Invoke-WebRequest 'http://127.0.0.1:8000/api/v1/system/getLoginMethod' -UseBasicParsing -TimeoutSec 10 } catch { [int]$_.Exception.Response.StatusCode }
try { Invoke-WebRequest 'http://127.0.0.1:8001/' -UseBasicParsing -TimeoutSec 10 } catch { [int]$_.Exception.Response.StatusCode }
& '.\backend\.venv\Scripts\python.exe' -c "from common.core.config import settings; print(settings.LLM_REQUEST_TIMEOUT, settings.LLM_TASK_MAX_WAIT_SECONDS, settings.LLM_MAX_RETRIES)"
```

Expected: 前端 `200`，API 返回 HTTP 响应且 `401` 可接受，MCP 根路径 `404` 可接受，模型配置输出 `120 900 1`。

- [ ] **Step 3: 只读导出数据库推荐入口**

Run: 使用 `backend\.venv\Scripts\python.exe` 加载根目录 `.env`，查询 `sys_tenant`、`core_dashboard` 和 `core_datasource`，只选择 `delete_flag=0`、`is_default=1` 的当前空间记录，并写入盘点 JSON。

Expected: `flam` 与`修仙`均有清单；`flam` 的“运营总览”记录为 `excluded=true`，不存在其他被静默排除的入口。

- [ ] **Step 4: 通过 UI 核对入口与图表标题**

Run: 在内置浏览器分别进入两个空间的推荐看板列表，逐一打开入口，将实际落页、空看板、数据源错配、外部 MCP 类型和可见图表标题回写盘点 JSON，并生成 Markdown 摘要。

Expected: 每个数据库入口都有 `ui_status`；不可用入口有明确原因，不从其他看板借用题目。

### Task 2: 生成并校验两套 100 题夹具

**Files:**
- Create: `.codex-runtime/flam-ai-dashboard-100-questions-2026-07-28.json`
- Create: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-07-28.json`
- Create: `.codex-runtime/validate-ai-dashboard-questions-2026-07-28.ps1`
- Read: `.codex-runtime/ai-dashboard-recommended-inventory-2026-07-28.json`

**Interfaces:**
- Consumes: Task 1 盘点中的有效看板名称、图表标题、数据源和入口类型。
- Produces: JSON 数组项 `{id, session, workspace, dashboard_id, dashboard_name, datasource_id, question, expected_answer_kind, time_scope}`。

- [ ] **Step 1: 按 20 个主题会话编写 flam 题目**

每个会话写入 5 个连续问题，覆盖有效普通看板与外部 MCP 看板。问题不得引用“运营总览”入口及其内容；空入口或错误落页不分配题目。

Expected: 100 项，`id=1..100`，`session=1..20` 且每个会话恰好 5 项。

- [ ] **Step 2: 按 20 个主题会话编写修仙题目**

每个会话写入 5 个连续问题，覆盖全部有效推荐看板；不得引用 flam 专有字段、指标或数据源。

Expected: 100 项，`id=1..100`，`session=1..20` 且每个会话恰好 5 项。

- [ ] **Step 3: 编写夹具校验脚本**

脚本读取两个 JSON，检查：数组长度 100、ID 连续且唯一、问题文本唯一、20 个会话各 5 题、空间与数据源正确、看板 ID 存在于盘点、flam 不含被排除入口、时间范围至少覆盖 8 种口径。

Run:

```powershell
.\.codex-runtime\validate-ai-dashboard-questions-2026-07-28.ps1
```

Expected: 输出 `flam: 100 valid`、`修仙: 100 valid` 和 `all checks passed`。

- [ ] **Step 4: 人工抽查语义与多轮依赖**

每个空间抽查首题、末题及每个会话的第 2、5 题，确认后续问题可以从本会话前文理解，且不需要另一个会话的隐藏上下文。

Expected: 40 个会话均可独立重放。

### Task 3: 浏览器双空间冒烟与上下文隔离

**Files:**
- Create: `.codex-runtime/ai-dashboard-browser-smoke-2026-07-28.json`
- Read: `.codex-runtime/flam-ai-dashboard-100-questions-2026-07-28.json`
- Read: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-07-28.json`

**Interfaces:**
- Consumes: 两套通过校验的题目夹具、Task 1 验证过的本地四服务。
- Produces: 两个空间各一次 UI 提交的请求记录、空间标签、数据源标签和终态证据。

- [ ] **Step 1: 在 flam 空间提交一题冒烟问题**

Run: 打开 flam 的有效普通推荐看板，从题目夹具选择对应会话首题，通过 AI 看板输入框提交并等待终态。

Expected: 页面空间为 flam、数据源为 `3`、问题文本与记录一致，得到成功、能力边界或明确产品错误之一，不停留在“思考中”。

- [ ] **Step 2: 关闭 flam 请求并切换修仙空间**

Run: 关闭当前抽屉或新建会话，切换到修仙空间，打开修仙有效推荐看板。

Expected: 页面不显示 flam 的问题、图表或数据源；当前数据源为 `6`。

- [ ] **Step 3: 在修仙空间提交一题冒烟问题**

Run: 从修仙夹具选择对应会话首题提交并等待终态。

Expected: 数据库记录的 `tenant_id`、问题和浏览器当前空间一致。

- [ ] **Step 4: 保存冒烟证据并决定是否放行批量测试**

只有两个空间均无上下文串线、Worker 健康且没有孤儿请求时才进入 Task 4；否则暂停并记录阻断原因。

### Task 4: 执行 flam 100 题并采集结果

**Files:**
- Create: `.codex-runtime/flam-ai-dashboard-100-attempts-2026-07-28.jsonl`
- Create: `.codex-runtime/flam-ai-dashboard-100-results-2026-07-28.json`
- Read: `.codex-runtime/flam-ai-dashboard-100-questions-2026-07-28.json`

**Interfaces:**
- Consumes: flam 题目夹具、已通过的浏览器冒烟会话。
- Produces: 100 个问题的全部尝试和每题最新可用终态。

- [ ] **Step 1: 建立不超过 4 个 flam 浏览器通道**

每个通道一次只运行一个会话；同一会话的 5 题必须逐题等待终态后再提交下一题。

- [ ] **Step 2: 运行 20 个主题会话**

每次提交后记录 `workspace`、`dashboard_id`、`datasource_id`、`question_id`、`session`、`question`、`record_id`、`started_at`、`finished_at`、`finish`、`error` 和页面答案摘要。

Expected: 100 个不同问题均至少有一次提交尝试，且没有“运营总览”来源。

- [ ] **Step 3: 同步数据库结果信号**

只读查询 `chat_record` 与 `chat_log`，为每题补充 `has_sql_answer`、`has_chart_answer`、`has_analysis`、耗时和 token 用量；不得仅依据抽屉历史判断。

- [ ] **Step 4: 检查未完成任务和运行健康**

若存在 `finish=false`、网络错误或连续任务失败，暂停新提交，检查 Worker、Redis、API 日志并保存当前进度，不把基础设施故障判为 SQL 或业务失败。

### Task 5: 执行修仙 100 题并采集结果

**Files:**
- Create: `.codex-runtime/xiuxian-ai-dashboard-100-attempts-2026-07-28.jsonl`
- Create: `.codex-runtime/xiuxian-ai-dashboard-100-results-2026-07-28.json`
- Read: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-07-28.json`

**Interfaces:**
- Consumes: 修仙题目夹具；Task 4 已完全停止并关闭的 flam 浏览器通道。
- Produces: 100 个修仙问题的全部尝试和每题最新可用终态。

- [ ] **Step 1: 关闭 flam 会话并重新核对修仙上下文**

Expected: 所有通道当前空间为修仙、数据源为 `6`，页面不存在 flam 残留答案。

- [ ] **Step 2: 运行 20 个修仙主题会话**

使用与 Task 4 相同的串行会话和最多 4 通道策略，保存每次提交的完整审计字段。

Expected: 100 个不同问题均至少有一次提交尝试。

- [ ] **Step 3: 同步数据库结果信号**

只读查询当前修仙 `tenant_id` 下的 `chat_record` 与 `chat_log`，补充 SQL、图表、分析、耗时和 token 信号。

- [ ] **Step 4: 检查跨空间隔离和未完成任务**

Expected: 修仙结果不存在 flam 数据源 ID、看板 ID 或回答内容；所有未完成项进入 Task 6 复测列表。

### Task 6: 失败复测、分类和最终报告

**Files:**
- Create: `.codex-runtime/ai-dashboard-retests-2026-07-28.jsonl`
- Create: `.codex-runtime/flam-ai-dashboard-100-test-results-2026-07-28.md`
- Create: `.codex-runtime/xiuxian-ai-dashboard-100-test-results-2026-07-28.md`
- Create: `.codex-runtime/ai-dashboard-200-test-summary-2026-07-28.md`
- Modify: `.codex-runtime/flam-ai-dashboard-100-results-2026-07-28.json`
- Modify: `.codex-runtime/xiuxian-ai-dashboard-100-results-2026-07-28.json`

**Interfaces:**
- Consumes: 两个空间的题目、尝试、结果和推荐入口盘点。
- Produces: 最终逐题分类、复测证据、空间报告和 200 题汇总。

- [ ] **Step 1: 生成复测清单**

选择 `finish=false`、`sql_error`、`chart_error`、`runtime_error` 以及上下文不完整的题目。能力边界保留原结果，除非证据显示是临时工具不可用。

- [ ] **Step 2: 在独立会话复测失败项**

单轮问题在新会话独立复测一次；多轮问题从该会话第 1 题开始完整重放。保存初次和复测两条尝试，不覆盖原始证据。

- [ ] **Step 3: 形成最终分类**

按 `data_chart_success`、`data_text_success`、`text_success`、`capability_boundary`、`sql_error`、`chart_error`、`runtime_error`、`running_or_orphaned` 分类。每题必须恰好有一个最终类别。

- [ ] **Step 4: 验证结果完整性**

Run:

```powershell
$f=@(Get-Content -Raw '.codex-runtime\flam-ai-dashboard-100-results-2026-07-28.json' | ConvertFrom-Json)
$x=@(Get-Content -Raw '.codex-runtime\xiuxian-ai-dashboard-100-results-2026-07-28.json' | ConvertFrom-Json)
if($f.Count -ne 100 -or $x.Count -ne 100){throw '结果数量不是各100条'}
if((@($f.id | Sort-Object -Unique)).Count -ne 100 -or (@($x.id | Sort-Object -Unique)).Count -ne 100){throw '结果ID不唯一'}
if(@($f | Where-Object {$_.status -eq 'running_or_orphaned'}).Count -gt 0){Write-Warning 'flam仍有未结束任务'}
if(@($x | Where-Object {$_.status -eq 'running_or_orphaned'}).Count -gt 0){Write-Warning '修仙仍有未结束任务'}
'result integrity checks passed'
```

Expected: 两个结果文件各 100 条、ID 唯一；未结束任务为 0，或在报告中有明确未解决原因。

- [ ] **Step 5: 生成三份报告并完成最终核对**

报告分别列出问题数、终态完成数、有效回答数、业务数据返回数、图表成功数、能力边界和各错误类型；逐项链接题目、结果、复测及入口盘点文件。

Expected: 汇总总数严格等于 200，各分类相加与空间问题数一致，不使用“全部成功”概括只有运行终态的记录。
