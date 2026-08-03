# AI 看板独立问题库重新生成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除已确认的历史 AI 看板题库和测试产物，并基于当前推荐看板为 `flam` 与“修仙”分别生成 100 个可独立提交的问题。

**Architecture:** 先用显式路径清单删除 42 项旧产物，再以只读数据库查询得到的当前推荐看板 ID、名称、数据源和图表主题作为题库边界。两份 JSON 由当前配置驱动编写，最后用独立 PowerShell 脚本执行结构、范围、唯一性、独立性和覆盖度校验。

**Tech Stack:** Windows PowerShell、PostgreSQL、JSON、Git

## Global Constraints

- 本轮只生成问题库，不向 AI 看板提交问题。
- `flam` 排除“运营总览”文件夹及其 4 个 ChatMon 子看板。
- “修仙”覆盖当前全部 10 个有效推荐叶子看板。
- 每个空间严格生成 100 个彼此独立的问题。
- 不修改推荐看板、Data Skill、数据源、权限、业务数据或产品运行代码。
- 不删除 `.codex-runtime` 中与已确认 42 项清单无关的内容。
- 不覆盖或回退工作区中已有的未提交改动。

---

### Task 1: 删除 42 项历史产物

**Files:**
- Delete: `.codex-runtime` 下已确认的 32 个文件和 10 个目录
- Preserve: `.codex-runtime` 下不在显式清单中的所有内容

**Interfaces:**
- Consumes: 用户确认的 42 项删除清单。
- Produces: 不含任何清单内旧产物的运行目录。

- [ ] **Step 1: 解析并验证删除目标**

在 PowerShell 中建立包含 42 个名称的显式数组。对每个名称执行 `Join-Path (Resolve-Path '.codex-runtime')`，并验证父目录严格等于仓库根目录下的 `.codex-runtime`。目录只允许使用清单中的 10 个固定名称，不接受通配符、环境变量展开或递归搜索结果作为删除目标。

- [ ] **Step 2: 永久删除验证通过的目标**

使用 `Remove-Item -LiteralPath` 删除文件；仅对清单中已验证的 10 个目录使用 `Remove-Item -LiteralPath -Recurse`。不存在的目标记录为已清理，不扩大删除范围。

- [ ] **Step 3: 验证旧产物清空**

重新按相同 42 项清单执行 `Test-Path -LiteralPath`。

Expected: `remaining old artifacts: 0`，且仓库现有未提交源代码状态不变。

### Task 2: 生成 flam 100 题

**Files:**
- Create: `.codex-runtime/flam-ai-dashboard-100-questions-2026-08-02.json`

**Interfaces:**
- Consumes: 当前只读数据库中的 14 个有效推荐叶子看板。
- Produces: 100 项 JSON 数组，每项字段为 `id`、`workspace`、`dashboard_id`、`dashboard_name`、`datasource_id`、`question`、`topic`、`time_scope`、`expected_answer_kind`、`independent`。

- [ ] **Step 1: 按当前看板分配题量**

使用以下精确分配，总数为 100：

| 看板 | ID | 题数 |
| --- | --- | ---: |
| 养成看板 | `1683de014d814e90b2c6dc002df8da1f` | 5 |
| 核心看板 | `6d50bd7dfc9f46ba961d636814c3294d` | 5 |
| 新增看板 | `bb3ab5f2697a42af98ab90da4679cb77` | 5 |
| 活跃看板 | `8c93878ee7af41b9b3832547856d25e6` | 5 |
| 留存分析 | `8f86e50234794606bd2a33ec41ffa660` | 5 |
| 付费概览 | `259414f219f94aacaa46f4e531646b9d` | 15 |
| 主城建设 | `db9df7a9015c4b4bb033810ffc5a84d2` | 10 |
| 出征数据 | `4bae835c4243481b9963122b5275ed81` | 10 |
| 渠道分析 | `5cee4cf41a024c56ac9de0e3aef9aefe` | 5 |
| 活动分析 | `29ea652e2969440b91899cfb254dd0ca` | 10 |
| 经济系统 | `f26870db68cb44bd974b0160ea91cdae` | 10 |
| ROI看板 | `2b990d3821fa4c3d97f0dda519b644e8` | 5 |
| 投放看板 | `e423819a72454bc9ab71646d41aa5fd6` | 5 |
| 实时看板 | `760150000bdc4abbb740880d494f5a5a` | 5 |

- [ ] **Step 2: 编写 100 个独立问题**

所有记录固定 `workspace="flam"`、`datasource_id=3`、`independent=true`。问题必须完整陈述指标、维度和时间范围，不包含“继续”“再看”“上一题”“刚才”“前面结果”或其他多轮指代；题目只使用对应看板当前图表标题能够支持的主题。

- [ ] **Step 3: 做 JSON 基础解析检查**

Run:

```powershell
$items = @(Get-Content -Raw '.codex-runtime\flam-ai-dashboard-100-questions-2026-08-02.json' | ConvertFrom-Json)
if ($items.Count -ne 100) { throw "flam count=$($items.Count)" }
"flam parsed: $($items.Count)"
```

Expected: `flam parsed: 100`。

### Task 3: 生成修仙 100 题

**Files:**
- Create: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-08-02.json`

**Interfaces:**
- Consumes: 当前只读数据库中的 10 个有效推荐叶子看板。
- Produces: 与 Task 2 字段一致的 100 项 JSON 数组。

- [ ] **Step 1: 按当前看板分配题量**

使用以下精确分配，总数为 100：

| 看板 | ID | 题数 |
| --- | --- | ---: |
| 养成看板 | `60c291cf41254cb993c6dff2b38cdca6` | 5 |
| 核心看板 | `afe201c9762c448aa0495f3508c01793` | 20 |
| 留存分析 | `32909e56ee174a2a9d8226be17d51ddf` | 15 |
| 付费概览 | `6234ec38697c4924b65c7de11d8bd829` | 15 |
| 新增看板 | `b09e4d57f57b41859a0c2d4609f80f26` | 10 |
| 活跃看板 | `c68e08ee9b4a4be59c3c8fbbe918affd` | 10 |
| ROI看板 | `17531de20e5d439f9ddfb2eeececced5` | 5 |
| 渠道分析 | `a34aef6cb7214f7fa23e5846a0a66236` | 10 |
| 投放看板 | `146ba4deb8b74ab293f38f69d89d4b21` | 5 |
| 实时看板 | `10604280d5a941af9720800bce6e030f` | 5 |

- [ ] **Step 2: 编写 100 个独立问题**

所有记录固定 `workspace="修仙"`、`datasource_id=6`、`independent=true`。不得引用 `flam` 专有的主城建设、出征、兵种、荣耀远征、活动分析、钻石经济、新手引导或 ChatMon 主题。

- [ ] **Step 3: 做 JSON 基础解析检查**

Run:

```powershell
$items = @(Get-Content -Raw '.codex-runtime\xiuxian-ai-dashboard-100-questions-2026-08-02.json' | ConvertFrom-Json)
if ($items.Count -ne 100) { throw "xiuxian count=$($items.Count)" }
"xiuxian parsed: $($items.Count)"
```

Expected: `xiuxian parsed: 100`。

### Task 4: 编写并运行题库校验器

**Files:**
- Create: `.codex-runtime/validate-ai-dashboard-questions-2026-08-02.ps1`
- Test: `.codex-runtime/flam-ai-dashboard-100-questions-2026-08-02.json`
- Test: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-08-02.json`

**Interfaces:**
- Consumes: 两份题库以及计划中固定的当前看板映射。
- Produces: 非零退出码表示校验失败；成功时输出两个空间的数量、覆盖看板数和总成功信息。

- [ ] **Step 1: 编写校验脚本**

校验器必须验证：必填字段存在；各 100 项；ID 为连续 `1..100`；空间、数据源和独立标志固定；看板 ID 与名称严格匹配；所有允许看板至少覆盖一次；单空间及跨空间问题文本唯一；问题不含上下文依赖词；`expected_answer_kind` 至少覆盖 `metric`、`trend`、`comparison`、`ranking`、`composition`、`conversion`、`anomaly` 七类；`time_scope` 至少覆盖 8 种值；“修仙”不含 `flam` 专有主题；`flam` 不含 ChatMon 或“运营总览”范围。

- [ ] **Step 2: 运行完整校验**

Run:

```powershell
& '.\.codex-runtime\validate-ai-dashboard-questions-2026-08-02.ps1'
```

Expected:

```text
flam: 100 valid, 14 dashboards covered
修仙: 100 valid, 10 dashboards covered
all checks passed
```

- [ ] **Step 3: 验证最终产物范围**

列出名称匹配 `ai-dashboard`、`100-questions`、`100-test` 或 `recommended-inventory` 的 `.codex-runtime` 直接子项。

Expected: 仅存在两份 `2026-08-02` 题库和一份 `2026-08-02` 校验脚本；其他无关运行文件保持不变。

### Task 5: 最终复核

**Files:**
- Read: `.codex-runtime/flam-ai-dashboard-100-questions-2026-08-02.json`
- Read: `.codex-runtime/xiuxian-ai-dashboard-100-questions-2026-08-02.json`
- Read: `.codex-runtime/validate-ai-dashboard-questions-2026-08-02.ps1`

**Interfaces:**
- Consumes: Task 1 至 Task 4 的结果。
- Produces: 完成报告和可直接使用的题库路径。

- [ ] **Step 1: 抽查问题语义**

每个看板至少抽查首题，确认问题不依赖上下文、看板归属正确、时间范围可执行、没有跨空间专有主题。

- [ ] **Step 2: 检查 Git 工作区边界**

Run:

```powershell
git status --short
```

Expected: 用户原有未提交文件保持原状；`.codex-runtime` 产物不进入 Git；除本计划文档外没有新增源代码修改。

- [ ] **Step 3: 报告删除与生成结果**

报告永久删除 42 项旧产物、新生成两份各 100 题的 JSON、校验脚本结果，并明确本轮未向 AI 看板提交问题。
