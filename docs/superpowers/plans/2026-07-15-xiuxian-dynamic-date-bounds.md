# 修仙 Data Skill 动态日期边界实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除修仙工作空间 Data Skill 中的最大日期聚合，以用户日期要求动态生成单行 `bounds`，未指定日期时默认查询截至昨天的最近 28 个自然日。

**Architecture:** 只修改数据源 `6` 的工作空间级语义配置，不修改平台通用 SQL 生成器。日期 Skill 负责动态日期规则，付费 Skill 复用该规则并保留近七天 ARPPU 示例；种子脚本继续通过现有幂等 upsert 和 embedding 刷新流程发布配置。

**Tech Stack:** Python 3、pytest、PostgreSQL/psycopg、MySQL/AnalyticDB SQL 提示词。

## Global Constraints

- 用户指定绝对日期时直接使用其起止日期。
- 用户指定相对窗口时根据窗口长度动态计算边界，截止日默认为昨天。
- 用户未指定日期窗口时默认查询截至昨天的最近 28 个自然日。
- 起止日期均包含；最近 `N` 个完整自然日的开始日期为 `CURDATE() - N DAY`，结束日期为 `CURDATE() - 1 DAY`。
- 修仙 Data Skill prompt 不得包含最大日期聚合或“标准聚合 SQL”章节。
- 不修改其他数据源或平台通用 SQL 生成逻辑。

---

### Task 1: 建立动态日期边界回归测试

**Files:**
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py:59-88`

**Interfaces:**
- Consumes: `seed_xiuxian_data_skills.DATA_SKILLS: list[dict[str, str]]`
- Produces: 日期 Skill 和付费 Skill 的动态边界行为断言。

- [ ] **Step 1: 将现有最大业务日期断言改成目标行为测试**

```python
def test_xiuxian_payment_skill_uses_partition_bounds_for_recent_seven_days() -> None:
    prompt = _payment_skill()["prompt"]
    assert "MAX(" not in prompt.upper()
    assert "bounds (start_dt, end_dt) AS (" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 7 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
    assert "e.dt BETWEEN b.start_dt AND b.end_dt" in prompt


def test_xiuxian_date_skill_uses_dynamic_bounds_without_max_date_scan() -> None:
    prompt = _date_skill()["prompt"]
    assert "MAX(" not in prompt.upper()
    assert "## 标准聚合 SQL" not in prompt
    assert "未指定日期窗口时，默认查询截至昨天的最近 28 个自然日" in prompt
    assert "用户指定相对日期窗口" in prompt
    assert "用户指定绝对起止日期" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 29 DAY)" in prompt
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_xiuxian_data_skill_seed.py -q
```

Expected: FAIL，失败原因包括当前 prompt 仍包含 `MAX(`、仍包含“标准聚合 SQL”，而不是导入或环境错误。

### Task 2: 修改修仙日期与付费 Data Skill

**Files:**
- Modify: `tools/seed_xiuxian_data_skills.py:41-115`
- Modify: `tools/seed_xiuxian_data_skills.py:165-231`
- Modify: `tests/test_seed_xiuxian_data_skills.py:29-54`

**Interfaces:**
- Consumes: 用户问题中的相对日期窗口、绝对日期窗口或未指定日期状态。
- Produces: 供 SQL 生成模型使用的动态 `bounds.start_dt/end_dt` 规则和示例。

- [ ] **Step 1: 重写日期 Skill 的日期窗口规则**

删除“标准聚合 SQL”、最大业务日期搜索说明和相应示例，保留以下规则及非固定示例：

```markdown
## 日期窗口规则

- 用户指定绝对起止日期时，直接将用户日期转换为 `YYYYMMDD` 整数边界。
- 用户指定相对日期窗口时，根据用户要求的窗口长度动态计算边界，结束日期默认为昨天；下面 SQL 仅用于展示边界写法，不表示固定查询范围。
- 用户未指定日期窗口时，默认查询截至昨天的最近 28 个自然日。
- 起止日期均包含。最近 `N` 个完整自然日应使用当前日期减 `N` 天作为开始日期、当前日期减 1 天作为结束日期。

```sql
WITH bounds AS (
    SELECT
        CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
        CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS end_dt
)
```
```

后续查询继续通过 `JOIN bounds b` 或 `CROSS JOIN bounds b` 使用 `dt BETWEEN b.start_dt AND b.end_dt`，但 prompt 中不再出现任何最大日期聚合文本。

- [ ] **Step 2: 重写近七天 ARPPU 示例的边界 CTE**

```sql
WITH RECURSIVE bounds (start_dt, end_dt) AS (
    SELECT
        CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
        CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS end_dt
),
params (end_date, start_date) AS (
    SELECT
        STR_TO_DATE(CAST(end_dt AS CHAR), '%Y%m%d') AS end_date,
        STR_TO_DATE(CAST(start_dt AS CHAR), '%Y%m%d') AS start_date
    FROM bounds
)
```

同时将 `pay` CTE 的过滤改为：

```sql
FROM `event` e
CROSS JOIN bounds b
WHERE e.dt BETWEEN b.start_dt AND b.end_dt
```

- [ ] **Step 3: 更新根目录种子测试**

将 `len(module.DATA_SKILLS) == 1` 修正为 `2`，通过 marker 获取日期 Skill，并断言：

```python
date_skill = next(
    skill for skill in module.DATA_SKILLS
    if "data-skill-source:xiuxian:date-partition-aggregation" in skill["prompt"]
)
prompt = date_skill["prompt"]
assert "MAX(" not in prompt.upper()
assert "## 标准聚合 SQL" not in prompt
assert "未指定日期窗口时，默认查询截至昨天的最近 28 个自然日" in prompt
assert "DATE_SUB(CURDATE(), INTERVAL 29 DAY)" in prompt
assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in prompt
```

- [ ] **Step 4: 运行修仙 Data Skill 测试**

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py -q
```

Expected: PASS，0 failures。

- [ ] **Step 5: 运行通用提示词回归测试**

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_dashboard_ai_sql_generator.py::test_dashboard_prompt_requires_safe_cte_time_boundaries backend/tests/test_llm_sql_answer_parser.py -q
```

Expected: PASS，0 failures。

- [ ] **Step 6: 提交代码与测试**

```powershell
git add -- tools/seed_xiuxian_data_skills.py tests/test_seed_xiuxian_data_skills.py backend/tests/test_xiuxian_data_skill_seed.py
git commit -m "修复：移除修仙最大日期聚合扫描"
```

### Task 3: 发布并验证数据库 Data Skill

**Files:**
- Runtime update only: system database table `custom_prompt`, tenant `7482727237662281728`, datasource `6`。

**Interfaces:**
- Consumes: `tools/seed_xiuxian_data_skills.py::main()`。
- Produces: 更新后的 Data Skill rows 和匹配当前 embedding 配置的向量。

- [ ] **Step 1: 运行幂等种子脚本**

```powershell
.\backend\.venv\Scripts\python.exe tools\seed_xiuxian_data_skills.py
```

Expected: 输出两个 Data Skill ID，并显示 `embeddings 已保存: 2`。

- [ ] **Step 2: 查询启用记录并验证 prompt**

使用 `tools/core_system_db.py` 的 `core_system_db_config()` 连接系统库，查询：

```sql
SELECT id,
       name,
       position('MAX(' in upper(prompt)) AS max_position,
       position('## 标准聚合 SQL' in prompt) AS standard_section_position,
       embedding IS NOT NULL AS has_embedding
FROM custom_prompt
WHERE tenant_id = 7482727237662281728
  AND type = 'DATA_SKILL'
  AND active = TRUE
  AND specific_ds = TRUE
  AND datasource_ids @> '[6]'::jsonb
ORDER BY id;
```

Expected: 修仙日期与付费两条记录的 `max_position=0`、`standard_section_position=0`、`has_embedding=true`。

- [ ] **Step 3: 检查最终差异和工作区边界**

```powershell
git status --short
git diff --check HEAD~1..HEAD
```

Expected: 本次提交只包含种子脚本和两组测试；用户已有的设计文档与 Excel 修改仍保持未提交状态。
