# ChatMon SaaS Skill 误匹配修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收紧平台级 ChatMon Data Skill 的领域触发条件，使普通 BI 问题不再误入 MCP 路径，同时保留明确告警问题的匹配能力。

**Architecture:** 保持通用 `find_matching_executable_saas_skill` 算法不变，只修正 `tools/seed_saas_mcp_data_skills.py` 中四条平台配置。测试直接读取种子脚本的 `DATA_SKILLS`，用生产相同的解析和匹配函数验证负向与正向行为；验证通过后运行幂等种子脚本更新系统数据库。

**Tech Stack:** Python 3.11、pytest、psycopg、现有 SaaS Skill 解析器与幂等种子脚本。

## Global Constraints

- 普通 BI 问题不能仅凭“查看、列表、趋势、数量、明细”等通用词命中 ChatMon Skill。
- 明确包含“告警、舆情、风险反馈、ChatMon、告警 ID”等领域语义的问题仍可命中对应 Skill。
- 不修改通用匹配算法、MCP 权限校验或未绑定提示。
- 不改动当前工作树中已有的修仙数据脚本、测试、Excel 和设计文档变更。
- 代码注释、测试说明、提交信息使用中文。

---

### Task 1: 用真实种子数据复现误匹配

**Files:**
- Create: `tests/test_seed_saas_mcp_data_skills.py`
- Read: `tools/seed_saas_mcp_data_skills.py`
- Read: `backend/apps/chat/task/saas_skill.py`

**Interfaces:**
- Consumes: `seed_saas_mcp_data_skills.DATA_SKILLS: list[dict[str, str]]`
- Consumes: `find_matching_executable_saas_skill(data_skill_text: str | None, question: str | None) -> ExecutableSaasSkillMatch | None`
- Produces: 对平台实际种子配置的负向和正向匹配回归测试。

- [ ] **Step 1: 写入失败回归测试和正向保护测试**

```python
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from seed_saas_mcp_data_skills import DATA_SKILLS
from apps.chat.task.saas_skill import find_matching_executable_saas_skill


def _platform_saas_skill_text() -> str:
    return "\n\n".join(skill["prompt"] for skill in DATA_SKILLS)


@pytest.mark.parametrize(
    "question",
    [
        "查看近半月朱果的变化情况",
        "查看近七天金币变化趋势",
        "查看订单明细列表",
    ],
)
def test_chatmon_skills_do_not_match_generic_bi_questions(question: str):
    assert find_matching_executable_saas_skill(_platform_saas_skill_text(), question) is None


@pytest.mark.parametrize(
    ("question", "expected_skill_id"),
    [
        ("查看最近7天告警列表", "saas_chatmon_alert_search"),
        ("查看最近7天舆情趋势", "saas_chatmon_alert_count"),
    ],
)
def test_chatmon_skills_still_match_explicit_domain_questions(
    question: str,
    expected_skill_id: str,
):
    match = find_matching_executable_saas_skill(_platform_saas_skill_text(), question)
    assert match is not None
    assert match.definition["id"] == expected_skill_id
```

- [ ] **Step 2: 运行负向用例确认 RED**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_saas_mcp_data_skills.py::test_chatmon_skills_do_not_match_generic_bi_questions -q`

Expected: FAIL；至少“查看近半月朱果的变化情况”实际得到 `saas_chatmon_alert_search`，证明测试捕获当前缺陷。

- [ ] **Step 3: 运行正向用例记录当前基线**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_saas_mcp_data_skills.py::test_chatmon_skills_still_match_explicit_domain_questions -q`

Expected: PASS；明确告警和舆情问题当前可正常匹配。

---

### Task 2: 收紧四条 ChatMon Skill 领域条件

**Files:**
- Modify: `tools/seed_saas_mcp_data_skills.py:31-34`
- Modify: `tools/seed_saas_mcp_data_skills.py:87-90`
- Modify: `tools/seed_saas_mcp_data_skills.py:189-194`
- Modify: `tools/seed_saas_mcp_data_skills.py:305-308`
- Test: `tests/test_seed_saas_mcp_data_skills.py`
- Test: `tests/test_saas_skill_execution.py`

**Interfaces:**
- Consumes: Task 1 的真实种子配置测试。
- Produces: 四条只能由 ChatMon 领域词通过前置条件的 `match.keywords_any` 配置。

- [ ] **Step 1: 最小修改四条 `keywords_any`**

将过滤项 Skill 改为：

```json
"keywords_any": ["告警", "舆情", "ChatMon", "chatmon", "alert", "alerts."]
```

将数量 Skill 改为：

```json
"keywords_any": ["告警", "舆情", "风险反馈", "用户反馈", "bug反馈", "Bug反馈", "ChatMon", "chatmon"]
```

将搜索 Skill 改为：

```json
"keywords_any": ["告警", "舆情", "风险反馈", "用户反馈", "ChatMon", "chatmon", "告警ID", "alert_id", "alert-"]
```

将证据 Skill 改为：

```json
"keywords_any": ["告警", "舆情", "ChatMon", "chatmon", "告警ID", "alert_id", "alert-"]
```

- [ ] **Step 2: 运行新测试确认 GREEN**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_seed_saas_mcp_data_skills.py -q`

Expected: `5 passed`。

- [ ] **Step 3: 运行通用 SaaS Skill 回归测试**

Run: `backend\.venv\Scripts\python.exe -m pytest tests/test_saas_skill_execution.py -q`

Expected: 全部通过，无失败和错误。

- [ ] **Step 4: 检查差异质量**

Run: `git diff --check -- tools/seed_saas_mcp_data_skills.py tests/test_seed_saas_mcp_data_skills.py`

Expected: exit code 0，无输出。

- [ ] **Step 5: 提交实现**

```powershell
git add -- tools/seed_saas_mcp_data_skills.py tests/test_seed_saas_mcp_data_skills.py docs/superpowers/plans/2026-07-15-chatmon-saas-skill-match-guard.md
git commit -m "修复：收紧 ChatMon Skill 触发条件"
```

---

### Task 3: 更新并验证系统数据库配置

**Files:**
- Execute: `tools/seed_saas_mcp_data_skills.py`
- Verify: PostgreSQL `zhishu_bi.custom_prompt`

**Interfaces:**
- Consumes: Task 2 中验证通过的 `DATA_SKILLS`。
- Produces: 系统数据库中四条更新后的平台公共 ChatMon Data Skill 和对应 embedding。

- [ ] **Step 1: 运行幂等种子脚本**

Run: `backend\.venv\Scripts\python.exe tools\seed_saas_mcp_data_skills.py`

Expected: 输出 `Upserted SaaS MCP data skills: [248, 249, 250, 251]`，embedding 保存数量为 4；若 ID 因环境不同而变化，以四条 marker 对应的实际 ID 为准。

- [ ] **Step 2: 从数据库读取实际 prompt 做负向复验**

读取 `custom_prompt` 中 `data-skill-source:saas:mcp:chatmon` 四条 prompt，拼接后调用：

```python
match = find_matching_executable_saas_skill(prompt_text, "查看近半月朱果的变化情况")
assert match is None
```

Expected: 断言通过。

- [ ] **Step 3: 从数据库读取实际 prompt 做正向复验**

```python
search_match = find_matching_executable_saas_skill(prompt_text, "查看最近7天告警列表")
count_match = find_matching_executable_saas_skill(prompt_text, "查看最近7天舆情趋势")
assert search_match is not None and search_match.definition["id"] == "saas_chatmon_alert_search"
assert count_match is not None and count_match.definition["id"] == "saas_chatmon_alert_count"
```

Expected: 两个断言均通过。

- [ ] **Step 4: 最终工作树核对**

Run: `git status --short`

Expected: 仅保留任务开始前已经存在的修仙相关用户改动；本任务文件已提交。
