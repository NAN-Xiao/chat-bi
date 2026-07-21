# 修仙核心看板实时指标卡 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在修仙空间核心看板顶部安全新增四张当天实时指标卡。

**Architecture:** 使用独立修复脚本构造四个固定 ID 的 `metric` 组件与视图，读取业务库生成当前快照，备份系统库原配置后通过 CAS 更新。纯函数负责布局与视图构造，数据库函数只负责只读查询、备份和事务写入。

**Tech Stack:** Python 3.11、pytest、PostgreSQL（系统库）、MySQL 兼容分析引擎（业务库）。

## Global Constraints

- 当天数据只能读取 `event_realtime`。
- 产品固定为 `110000047`。
- 充值人数必须使用 `COUNT(DISTINCT uid)`。
- 充值金额必须使用 `ServerPayLog.personal.money`。
- 不修改用户当前未提交的前端文件。
- 不执行 Git 提交。

---

### Task 1: 固化指标与布局契约

**Files:**
- Create: `backend/tests/test_add_xiuxian_core_dashboard_realtime_metrics.py`
- Create: `tools/add_xiuxian_core_dashboard_realtime_metrics.py`

- [ ] 编写四项 SQL、字段和布局的失败测试。
- [ ] 运行定向测试并确认因模块缺失失败。
- [ ] 实现指标规格、视图构造和幂等布局改写。
- [ ] 运行定向测试并确认通过。

### Task 2: 安全更新核心看板

**Files:**
- Modify: `tools/add_xiuxian_core_dashboard_realtime_metrics.py`

- [ ] 实现系统库数据源解密和业务库只读查询。
- [ ] 实现目标看板备份、CAS 更新和覆盖复验。
- [ ] 以只读模式输出变更摘要。
- [ ] 使用 `--apply` 写入核心看板。

### Task 3: 完整验证

**Files:**
- Verify: `.codex-runtime/xiuxian-core-dashboard-metric-backups/`

- [ ] 运行脚本只读复验，确认重复执行不会再次下移。
- [ ] 执行四条业务 SQL，核对当天结果。
- [ ] 重新读取系统库，确认四卡位于顶部且原组件下移 8 行。
- [ ] 检查本地看板页面能够加载新卡片。
