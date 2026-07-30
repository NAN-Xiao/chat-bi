# Data Skill 数据库当前日期清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清除 flam 与修仙 Data Skills 中会诱导 SQL 使用数据库当前时间函数的规则和示例，并同步系统库配置。

**Architecture:** 保持日期契约由平台 token 与 `date_filter` 驱动，在数据源种子层改写冲突语义。固定 metric 与实时业务语义不依赖数据库会话日期，发布继续复用现有幂等 upsert 与 embedding 刷新流程。

**Tech Stack:** Python、pytest、PostgreSQL、现有 Data Skill 种子脚本

## Global Constraints

- 不放宽聊天日期严格校验。
- 不把 flam 或修仙业务字段硬编码进平台运行时。
- 只改数据源作用域 Data Skills、测试和发布数据。
- 保留仅用于禁止说明的 `CURDATE()` 文本。

---

### Task 1: 建立主动日期函数扫描契约

**Files:**
- Modify: `backend/tests/test_flam_first_zombie_data_skill_seed.py`
- Modify: `backend/tests/test_xiuxian_data_skill_seed.py`

**Interfaces:**
- Consumes: 两个种子模块导出的 `DATA_SKILLS`
- Produces: 区分禁止性说明与主动 SQL/规则用法的回归断言

- [ ] **Step 1: 写失败测试**：遍历启用种子 prompt，移除“不得/禁止/不要使用”说明行后，断言不再出现 `CURDATE(`。
- [ ] **Step 2: 验证 RED**：运行两个新增测试，预期列出当前冲突 Skill。
- [ ] **Step 3: 更新旧断言**：删除将 `DATE_SUB(CURDATE(), ...)` 锁定为正确行为的断言，改为看板 token/date_filter 契约。

### Task 2: 修复 flam 与修仙语义源

**Files:**
- Modify: `tools/seed_flam_first_zombie_data_skills.py`
- Modify: `tools/seed_xiuxian_data_skills.py`

**Interfaces:**
- Consumes: 平台 `{{dashboard_start_yyyymmdd}}` / `{{dashboard_end_yyyymmdd}}` 契约
- Produces: 无主动数据库当前日期函数的 `DATA_SKILLS`

- [ ] **Step 1: 修复 flam**：将历史窗口与 SQL 示例改为 token；实时规则改用明确业务时区或要求调用方提供日期边界。
- [ ] **Step 2: 修复修仙**：将历史窗口、日期骨架和修复示例改为 token；固定 metric 保留固定语义但不使用数据库当前时间函数。
- [ ] **Step 3: 验证 GREEN**：运行两个种子测试文件，预期全部通过。

### Task 3: 发布与系统库验证

**Files:**
- Execute: `tools/seed_flam_first_zombie_data_skills.py`
- Execute: `tools/seed_xiuxian_data_skills.py`

**Interfaces:**
- Consumes: 修复后的幂等种子配置
- Produces: 更新后的 `custom_prompt` 和 embedding

- [ ] **Step 1: 运行脚本帮助与测试确认发布命令和安全边界。**
- [ ] **Step 2: 执行两个幂等发布脚本并刷新 embedding。**
- [ ] **Step 3: 查询系统库，确认主动 `CURDATE()` 用法为 0，数据源绑定未变化。**
- [ ] **Step 4: 运行日期校验、SQL 修复与 Smart QA 回归，并执行 `compileall`、`git diff --check`。**
