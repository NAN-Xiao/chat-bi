# 大模型读取超时解耦实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将大模型读取超时提高到 120 秒，同时将流式任务总等待上限保持为 900 秒。

**Architecture:** 保留 `LLM_REQUEST_TIMEOUT` 作为模型 HTTP 读取和流式空闲超时配置，新增 `LLM_TASK_MAX_WAIT_SECONDS` 专门控制后台流式任务总等待。OpenAI 客户端接口保持不变，只解除任务总等待时间对读取超时倍数的依赖。

**Tech Stack:** Python 3.11、Pydantic Settings、LangChain OpenAI、pytest

## Global Constraints

- `LLM_REQUEST_TIMEOUT` 默认值必须为 120 秒。
- `LLM_TASK_MAX_WAIT_SECONDS` 默认值必须为 900 秒。
- `LLM_MAX_RETRIES` 保持为 1。
- 不修改图表历史消息、Schema 裁剪和提示词逻辑。
- 新增配置必须支持环境变量覆盖。

---

### Task 1: 解耦读取超时与任务总等待

**Files:**
- Modify: `backend/common/core/config.py:245`
- Modify: `backend/apps/chat/task/llm.py:2474`
- Create: `backend/tests/test_llm_timeout_config.py`

**Interfaces:**
- Consumes: `common.core.config.settings`
- Produces: `settings.LLM_REQUEST_TIMEOUT: int` 和 `settings.LLM_TASK_MAX_WAIT_SECONDS: int`

- [x] **Step 1: 编写失败测试**

```python
from common.core.config import Settings


def test_llm_timeout_defaults_are_decoupled(monkeypatch):
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_TASK_MAX_WAIT_SECONDS", raising=False)

    settings = Settings(_env_file=None)

    assert settings.LLM_REQUEST_TIMEOUT == 120
    assert settings.LLM_TASK_MAX_WAIT_SECONDS == 900


def test_llm_timeout_values_support_environment_overrides(monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "150")
    monkeypatch.setenv("LLM_TASK_MAX_WAIT_SECONDS", "600")

    settings = Settings(_env_file=None)

    assert settings.LLM_REQUEST_TIMEOUT == 150
    assert settings.LLM_TASK_MAX_WAIT_SECONDS == 600
```

- [x] **Step 2: 运行测试并确认按预期失败**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_llm_timeout_config.py -v`

Expected: FAIL，因为读取超时仍为 45，且 `LLM_TASK_MAX_WAIT_SECONDS` 尚不存在。

- [x] **Step 3: 实现最小配置变更**

在 `backend/common/core/config.py` 中定义：

```python
LLM_REQUEST_TIMEOUT: int = 120
LLM_TASK_MAX_WAIT_SECONDS: int = 900
LLM_MAX_RETRIES: int = 1
```

在 `LLMService.await_result()` 中将：

```python
max_wait_seconds = max(settings.LLM_REQUEST_TIMEOUT * 20, settings.LLM_REQUEST_TIMEOUT + 300)
```

替换为：

```python
max_wait_seconds = max(
    settings.LLM_TASK_MAX_WAIT_SECONDS,
    settings.LLM_REQUEST_TIMEOUT,
)
```

这样环境变量误配为“总等待小于单次读取超时”时，任务也不会先于底层读取超时结束。

- [x] **Step 4: 运行针对性测试并确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_llm_timeout_config.py -v`

Expected: 2 passed。

- [x] **Step 5: 运行相关回归测试**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_llm_recommend_reasoning_config.py backend/tests/test_assistant_workflow.py -v`

Expected: 全部通过。

- [x] **Step 6: 检查代码差异**

Run: `git diff --check && git diff -- backend/common/core/config.py backend/apps/chat/task/llm.py backend/tests/test_llm_timeout_config.py`

Expected: `git diff --check` 退出码为 0；差异仅包含超时解耦与测试。

- [x] **Step 7: 提交实现**

```bash
git add backend/common/core/config.py backend/apps/chat/task/llm.py backend/tests/test_llm_timeout_config.py
git commit -m "修复：解耦大模型读取超时与任务等待上限"
```
