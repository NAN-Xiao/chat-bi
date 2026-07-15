# 修仙 PayBuyRet 付费与 ARPPU 语义修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为修仙 datasource 6 新增基于 `PayBuyRet.personal.ed_money` 的付费与 ARPPU Data Skill，并阻止智能问答再次使用累计 `paytotal` 计算当日指标。

**Architecture:** 保持通用 BI 运行链路不变，只扩展现有修仙 Data Skill 种子。新 Skill 通过数据源作用域、业务说明、MySQL 8 参考 SQL 和现有 `data-skill-sql-validation` 元数据同时约束语义检索与生成后校验。

**Tech Stack:** Python 3.11、pytest、PostgreSQL `custom_prompt`、MySQL 8/AnalyticDB、现有 Data Skill embedding 服务。

## Global Constraints

- 仅作用于 `tenant_id=7482727237662281728`、`datasource_id=6`。
- 成功付费只使用 `event='PayBuyRet'`、`personal.ed_isSuccess=true`、`personal.ed_money>0`。
- ARPPU 使用成功付费金额除以同一观察窗口内去重 `uid`。
- `pay.paytotal` 和 `allianceinfo.paytotal` 不得用于当日收入、当日付费人数或 ARPPU。
- `personal.ed_orderId` 当前为空，`personal.ed_payId` 不是唯一交易号；不得伪造订单去重。
- 零付费日的金额和人数为 0，ARPPU 为 `NULL`。
- 不修改全局提示词、通用后端逻辑、前端图表或其他数据源语义。
- 所有新增代码注释、测试说明、提交信息使用中文。

---

### Task 1: 用失败测试锁定修仙付费语义合同

**Files:**
- Create: `backend/tests/test_xiuxian_data_skill_seed.py`
- Read: `tools/seed_xiuxian_data_skills.py`

**Interfaces:**
- Consumes: `seed_xiuxian_data_skills.DATA_SKILLS`、`TENANT_ID`、`DATASOURCE_ID`，以及 `apps.chat.task.llm._data_skill_sql_validation_error(question, sql, data_skill)`。
- Produces: 针对 Skill 作用域、事件字段、公式、订单限制、SQL 校验元数据和现有日期 Skill 保留行为的回归测试。

- [ ] **Step 1: 创建目标测试文件**

```python
"""验证修仙数据源 Data Skill 种子的付费与 ARPPU 口径。"""
from __future__ import annotations

import sys
from pathlib import Path

from apps.chat.task.llm import _data_skill_sql_validation_error

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import seed_xiuxian_data_skills as seed


def _payment_skill() -> dict[str, str]:
    return next(
        skill
        for skill in seed.DATA_SKILLS
        if "data-skill-source:xiuxian:paybuyret-monetization-arppu" in skill["prompt"]
    )


def test_xiuxian_payment_skill_is_scoped_and_keeps_date_skill() -> None:
    assert seed.TENANT_ID == 7482727237662281728
    assert seed.DATASOURCE_ID == 6
    assert len(seed.DATA_SKILLS) == 2
    assert any(
        "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
        for skill in seed.DATA_SKILLS
    )
    assert _payment_skill()["name"] == "修仙付费收入与 ARPPU 口径"


def test_xiuxian_payment_skill_documents_verified_paybuyret_formula() -> None:
    prompt = _payment_skill()["prompt"]

    assert "event = 'PayBuyRet'" in prompt
    assert "personal.ed_money" in prompt
    assert "personal.ed_isSuccess" in prompt
    assert "COUNT(DISTINCT uid)" in prompt
    assert "SUM(ed_money) / NULLIF(COUNT(DISTINCT uid), 0)" in prompt
    assert "pay.paytotal" in prompt
    assert "不能用于当日付费金额、当日付费人数或 ARPPU" in prompt
    assert "ed_orderId" in prompt
    assert "ed_payId" in prompt
    assert "不能代替订单号" in prompt


def test_xiuxian_payment_skill_rejects_cumulative_snapshot_arppu_sql() -> None:
    prompt = _payment_skill()["prompt"]
    wrong_sql = """
    SELECT dt,
           SUM(JSON_EXTRACT(pay, '$.paytotal'))
             / NULLIF(COUNT(DISTINCT uid), 0) AS ARPPU
    FROM `user`
    GROUP BY dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", wrong_sql, prompt) == (
        "修仙付费趋势必须使用 PayBuyRet 的成功事件、personal.ed_money 和去重 uid；"
        "paytotal 是累计快照，不能计算当日收入、当日付费人数或 ARPPU。"
    )


def test_xiuxian_payment_skill_allows_verified_paybuyret_arppu_sql() -> None:
    prompt = _payment_skill()["prompt"]
    correct_sql = """
    SELECT e.dt,
           SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)))
             / NULLIF(COUNT(DISTINCT e.uid), 0) AS ARPPU
    FROM `event` e
    WHERE e.event = 'PayBuyRet'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_isSuccess')) IN ('true', '1')
      AND CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')) AS DECIMAL(18, 4)) > 0
    GROUP BY e.dt
    """

    assert _data_skill_sql_validation_error("查看近七天的 ARPPU", correct_sql, prompt) is None
```

- [ ] **Step 2: 运行目标测试并确认失败原因正确**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_data_skill_seed.py -q
```

Expected: FAIL，失败点为找不到 `data-skill-source:xiuxian:paybuyret-monetization-arppu`，证明测试覆盖的是缺失语义而不是环境问题。

---

### Task 2: 新增修仙付费 Data Skill 并通过测试

**Files:**
- Modify: `tools/seed_xiuxian_data_skills.py:23-112`
- Test: `backend/tests/test_xiuxian_data_skill_seed.py`
- Test: `backend/tests/test_llm_sql_answer_parser.py`

**Interfaces:**
- Consumes: 现有 `_upsert_skill(cur, skill, now)` 基于 Skill 首行 marker 幂等写入的接口。
- Produces: `DATA_SKILLS` 中第二个数据源级 Skill，marker 为 `data-skill-source:xiuxian:paybuyret-monetization-arppu`。

- [ ] **Step 1: 在现有日期 Skill 后新增付费 Skill**

新增 Skill 的 `name`、`description` 和 `prompt` 必须完整包含以下内容；不修改 `_upsert_skill`、`_save_embeddings` 和 `main`：

```python
    {
        "name": "修仙付费收入与 ARPPU 口径",
        "description": "规范修仙 PayBuyRet 成功付费事件的人民币收入、付费用户、付费事件次数和 ARPPU，禁止把累计 paytotal 当作当日指标。",
        "prompt": """<!-- data-skill-source:xiuxian:paybuyret-monetization-arppu -->
<!-- data-skill-sql-validation:[
  {
    "match":["ARPPU","arppu"],
    "required_sql_contains":["PayBuyRet","ed_money","ed_isSuccess"],
    "forbidden_sql_contains":["paytotal"],
    "message":"修仙付费趋势必须使用 PayBuyRet 的成功事件、personal.ed_money 和去重 uid；paytotal 是累计快照，不能计算当日收入、当日付费人数或 ARPPU。"
  },
  {
    "match":["当日付费金额","每日付费金额","付费金额趋势","当日付费用户","每日付费用户","付费用户趋势","每日收入","收入趋势","每日流水","流水趋势","近七天收入","近7天收入"],
    "required_sql_contains":["PayBuyRet","ed_money","ed_isSuccess"],
    "forbidden_sql_contains":["paytotal"],
    "message":"修仙当日付费指标必须使用 PayBuyRet 的成功事件和 personal.ed_money；paytotal 只表示累计付费快照。"
  }
] -->
# 修仙付费收入与 ARPPU 口径

## 适用范围

- 仅适用于当前修仙工作空间的数据源，datasource_id=6。
- 适用于付费金额、收入、流水、付费用户、付费事件次数和 ARPPU。
- ARPU、付费率需要另行确认活跃用户事件和分母，不得根据字段名猜测。

## 已确认事件与字段

- 成功付费事件：`event = 'PayBuyRet'`。
- 人民币当次金额：`personal.ed_money`，SQL 路径为 `$.ed_money`。
- 成功标识：`personal.ed_isSuccess`，仅保留 `true` 或 `1`。
- 付费用户标识：`uid`。
- 支付平台订单号：`personal.ed_orderId`，但当前数据为空，不能用于订单去重。
- `personal.ed_payId` 会被多个用户和多笔支付复用，不是唯一交易号，不能代替订单号。

## 指标定义

- 当日付费金额：成功且 `ed_money > 0` 的 `PayBuyRet` 事件金额求和。
- 当日付费用户数：同一口径下 `COUNT(DISTINCT uid)`。
- 当日付费事件次数：同一口径下 `COUNT(*)`；不能命名为去重订单数。
- 当日 ARPPU：`SUM(ed_money) / NULLIF(COUNT(DISTINCT uid), 0)`。
- `pay.paytotal` 和 `allianceinfo.paytotal` 是累计快照，不能用于当日付费金额、当日付费人数或 ARPPU。
- 周/月 ARPPU 必须在周期内重新计算成功付费金额除以周期去重付费用户数，不能汇总或平均每日 ARPPU。

## 日期与空值

- 日期过滤、输出和最大业务日期锚点遵守“修仙业务日期与按日聚合口径”。
- “近七天”必须以最大可用业务日期为结束日期，向前包含七个自然日。
- 趋势必须补齐自然日；无付费日期的金额和人数为 0，ARPPU 为 `NULL`。

## MySQL 8 近七天 ARPPU 参考 SQL

```sql
WITH RECURSIVE bounds AS (
    SELECT MAX(dt) AS end_dt
    FROM `event`
),
params AS (
    SELECT
        STR_TO_DATE(CAST(end_dt AS CHAR), '%Y%m%d') AS end_date,
        DATE_SUB(STR_TO_DATE(CAST(end_dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY) AS start_date
    FROM bounds
),
days AS (
    SELECT start_date AS calendar_date, end_date
    FROM params
    UNION ALL
    SELECT DATE_ADD(calendar_date, INTERVAL 1 DAY), end_date
    FROM days
    WHERE calendar_date < end_date
),
pay AS (
    SELECT
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS pay_date,
        e.uid,
        CAST(
            NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')), '')
            AS DECIMAL(18, 4)
        ) AS ed_money
    FROM `event` e
    CROSS JOIN bounds b
    WHERE e.dt BETWEEN
          CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(b.end_dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED)
          AND b.end_dt
      AND e.event = 'PayBuyRet'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_isSuccess')) IN ('true', '1')
      AND CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_money')), '') AS DECIMAL(18, 4)) > 0
),
daily_pay AS (
    SELECT
        pay_date,
        SUM(ed_money) AS revenue,
        COUNT(DISTINCT uid) AS payers,
        COUNT(*) AS payment_event_count
    FROM pay
    GROUP BY pay_date
)
SELECT
    DATE_FORMAT(d.calendar_date, '%Y-%m-%d') AS dt,
    ROUND(COALESCE(p.revenue, 0), 2) AS revenue,
    COALESCE(p.payers, 0) AS payers,
    COALESCE(p.payment_event_count, 0) AS payment_event_count,
    ROUND(p.revenue / NULLIF(p.payers, 0), 2) AS arppu
FROM days d
LEFT JOIN daily_pay p ON p.pay_date = d.calendar_date
ORDER BY d.calendar_date;
```

## 禁止事项

- 不要使用 `user.pay.paytotal` 的日快照求和或累计付费人数计算 ARPPU。
- 不要把 `ed_payId` 当订单号去重。
- 不要在当前 Skill 中猜测 ARPU、付费率、退款或净收入口径。
- 不要把本口径传播到其他数据源。
""",
    },
```

- [ ] **Step 2: 运行目标测试并确认通过**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_data_skill_seed.py -q
```

Expected: `4 passed`。

- [ ] **Step 3: 运行现有 Data Skill SQL 校验回归测试**

Run:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_llm_sql_answer_parser.py tests/test_custom_prompt_datasource_scope.py -q
```

Expected: 全部通过，没有改变其他数据源的规则匹配或 Skill 作用域。

- [ ] **Step 4: 运行 Python 语法检查和 Git 空白检查**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m py_compile tools\seed_xiuxian_data_skills.py backend\tests\test_xiuxian_data_skill_seed.py
git diff --check
```

Expected: 两条命令退出码均为 0。

- [ ] **Step 5: 提交实现与测试**

```powershell
git add -- tools/seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py
git commit -m "修复：统一修仙 PayBuyRet 付费与 ARPPU 口径"
```

Expected: 仅提交上述两个文件，不包含用户现有的 Excel 和设计文档修改。

---

### Task 3: 幂等写入系统库并做端到端口径验证

**Files:**
- Run: `tools/seed_xiuxian_data_skills.py`
- Verify: PostgreSQL `custom_prompt`
- Verify: 修仙 MySQL `event`

**Interfaces:**
- Consumes: Task 2 产生的两个 `DATA_SKILLS` 和现有 embedding 保存接口。
- Produces: 系统库中两个活动、可见、仅绑定 datasource 6 的 Data Skill，以及成功刷新的 embedding。

- [ ] **Step 1: 执行幂等种子**

Run:

```powershell
$env:SECRET_KEY='y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s'
.\backend\.venv\Scripts\python.exe tools\seed_xiuxian_data_skills.py
```

Expected: 输出两个 Skill ID，且 `embeddings 已保存: 2`。

- [ ] **Step 2: 再执行一次验证幂等性**

Run: 重复 Step 1 命令。

Expected: 返回与首次相同的两个 Skill ID，仍为 `embeddings 已保存: 2`，系统库没有新增重复记录。

- [ ] **Step 3: 查询系统库验证作用域和 marker**

使用只读 SQL 查询：

```sql
SELECT id,
       name,
       active,
       visible,
       specific_ds,
       datasource_ids,
       embedding IS NOT NULL AS has_embedding
FROM custom_prompt
WHERE tenant_id = 7482727237662281728
  AND type = 'DATA_SKILL'
  AND specific_ds = TRUE
  AND datasource_ids = '[6]'::jsonb
  AND position('data-skill-source:xiuxian:' in COALESCE(prompt, '')) > 0
ORDER BY id;
```

Expected: 恰好两行，名称分别为“修仙业务日期与按日聚合口径”和“修仙付费收入与 ARPPU 口径”，状态均为活动、可见、仅绑定 `[6]`，embedding 非空。

- [ ] **Step 4: 对修仙业务库执行抽样只读对账**

以 `20260709` 至 `20260714` 为固定窗口执行新 Skill 同口径 SQL，验证：

```text
2026-07-09 revenue=3613 payers=18 arppu=200.72
2026-07-10 revenue=158  payers=4  arppu=39.50
2026-07-11 revenue=167  payers=3  arppu=55.67
2026-07-12 revenue=0    payers=0  arppu=NULL
2026-07-13 revenue=0    payers=0  arppu=NULL
2026-07-14 revenue=30   payers=1  arppu=30.00
```

- [ ] **Step 5: 验证 Git 工作区边界**

Run:

```powershell
git status --short
git show --stat --oneline HEAD
```

Expected: 用户原有的 `docs/superpowers/specs/2026-07-14-xiuxian-object-parameter-expansion-design.md` 和 `docs/xiuxian/tracking_dictionary_template_xiuxian_supplemented.xlsx` 修改仍在；实现提交不包含它们。
