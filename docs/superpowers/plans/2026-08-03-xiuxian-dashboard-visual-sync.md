# 修仙核心与 ROI 看板视觉同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 flam 默认推荐核心看板与 ROI 看板的视觉配置从 flam 同步到修仙，同时保留修仙 SQL、数据源和业务口径，并新增修仙 ROI 柱状图。

**Architecture:** 新增一个 datasource-scoped 迁移脚本，读取并校验两条修仙默认看板记录，只对 `component_data` 网格和 `canvas_view_info` 的通用图表展示字段做确定性转换。新增 ROI 图表从修仙 ROI 总览视图复制 SQL、日期和数据源配置，只改视图 ID、标题、轴/系列/类型及布局；数据库写入使用完整行备份、事务锁和双字段 CAS。

**Tech Stack:** Python 3.11、psycopg 3、PostgreSQL JSON、pytest、现有 `core_system_db_config`。

## Global Constraints

- 同步方向只能是 flam 到修仙；不得写入 flam 记录。
- 目标看板固定为修仙默认推荐核心看板 `afe201c9762c448aa0495f3508c01793` 与 ROI 看板 `17531de20e5d439f9ddfb2eeececced5`。
- 修仙看板绑定 datasource `6`、原有视图 datasource、SQL、日期过滤、字段名和业务口径必须保留；新增 ROI 图表继承修仙 `ROI总览` 的视图 datasource；禁止复制 datasource `3` SQL。
- 迁移默认只读，只有 `--apply` 写库；每条记录必须完整备份并用原始 `component_data` 与 `canvas_view_info` 做 CAS。
- 不覆盖工作区其他未提交文件，不执行 `git add .`、`git reset --hard` 或回滚用户修改。

---

### Task 1: 建立视觉转换器的失败测试

**Files:**
- Create: `tests/test_sync_xiuxian_dashboard_visuals.py`
- Test target: `tools/sync_xiuxian_dashboard_visuals.py`

**Interfaces:**
- Consumes: JSON `components` 数组、`canvas` 映射和修仙目标看板 ID。
- Produces: `transform_core_dashboard(components, canvas)`、`transform_roi_dashboard(components, canvas)`，返回 `(new_components, new_canvas, summary)`。

- [ ] **Step 1: 写纯函数行为测试**

  覆盖以下断言：核心 `ARPU与ARPPU`、`新增用户趋势` 变为 `column`，`每日渠道新增用户` 变为 `area`；ROI 地区图变为 `area`、广告地区图变为 `column`；ROI 新图存在且横轴为 `日期`、指标为 `首日ROI`/`3日ROI`；新图 SQL 等于修仙原 `ROI总览` SQL；所有原有 SQL、datasource 和 dateFilter 不变；两次转换结果相同且布局无重叠；缺少必需标题、重复组件 ID 或 ROI 新图已存在但内容不一致时抛出 `ValueError`。

- [ ] **Step 2: 运行测试确认失败**

  Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_sync_xiuxian_dashboard_visuals.py -q`

  Expected: FAIL，原因是目标模块或转换函数尚不存在。

### Task 2: 实现确定性 JSON 转换

**Files:**
- Create: `tools/sync_xiuxian_dashboard_visuals.py`
- Modify: `tests/test_sync_xiuxian_dashboard_visuals.py`

**Interfaces:**
- `transform_core_dashboard(components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]`
- `transform_roi_dashboard(components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]`
- `validate_layout(components: Sequence[Mapping[str, Any]]) -> None`

- [ ] **Step 1: 实现标题索引和严格校验**

  按 `canvas[view_id].chart.title` 建立唯一标题索引；组件 ID 必须唯一、每个组件必须有 canvas 视图、`x/y/sizeX/sizeY` 必须为正整数。缺失或重复目标直接失败，不用“第一个字段”或“第一个图表”兜底。

- [ ] **Step 2: 实现核心图表展示变换**

  仅更新匹配视图的 `chart.type` 与 `chart.sourceType`，并将修仙已有 `xAxis`、`yAxis`、`series` 保留在实际字段集合内；将共享图表按 flam 视觉类型映射，保留修仙独有图表和 SQL。重排组件时使用确定性标题顺序，禁止重写未涉及视图的 JSON 字段。

- [ ] **Step 3: 实现 ROI 新图复制**

  使用固定的新视图 ID（脚本常量）保证幂等。第一次运行从修仙 `ROI总览` 视图深拷贝整条视图配置，再设置标题 `图表`、类型/sourceType `column`、xAxis `日期`、yAxis `首日ROI`/`3日ROI`、series 为空；保留原 SQL、datasource、dateFilter、sourceConfig 及其他执行字段。若目标 ID 已存在，必须逐字段验证后复用，不能重复追加。

- [ ] **Step 4: 实现 flam 对齐布局和无重叠检查**

  ROI 组件按设计中的五行坐标写入；核心只在共享语义图表所在行调整类型和尺寸，不删除修仙独有图表。使用矩形相交检查保证所有组件无重叠。

- [ ] **Step 5: 运行测试确认通过**

  Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_sync_xiuxian_dashboard_visuals.py -q`

  Expected: PASS，且输出无 warning/error。

### Task 3: 接入备份、CAS 迁移和恢复命令

**Files:**
- Modify: `tools/sync_xiuxian_dashboard_visuals.py`
- Test: `tests/test_sync_xiuxian_dashboard_visuals.py`

**Interfaces:**
- `run(*, apply: bool) -> dict[str, Any]`
- `restore_backup(path: Path) -> dict[str, Any]`
- CLI: `--apply`、`--verify`、`--restore PATH`。

- [ ] **Step 1: 写数据库边界测试**

  用 fake cursor 验证查询同时限制两个目标 ID、tenant `7482727237662281728`、看板 datasource `6`、`scope='default'`；验证备份包含完整原始行、旧/新 SHA-256；验证 `rowcount != 1` 或读回不一致时回滚并抛错；验证 `--apply` 未提供时不执行 UPDATE。

- [ ] **Step 2: 实现目标查询和事务锁**

  复用 `core_system_db_config()`；每条看板执行 `pg_advisory_xact_lock(hashtext(id))`；查询 `core_dashboard` 与 `core_dashboard_tree`，校验名称、tenant、datasource、scope、非删除和 dashboard 类型。

- [ ] **Step 3: 实现 CAS 更新与完整备份**

  备份目录使用 `.codex-runtime/xiuxian-dashboard-visual-sync-backups/<UTC>-<dashboard-id>-<old-sha8>.json`，保存原始数据库行及 old/new hashes。UPDATE 同时以原 `component_data` 与 `canvas_view_info` 为条件，更新 `update_time`、`update_by='codex'` 和递增 version；任一失败整体回滚。

- [ ] **Step 4: 实现只读验证与恢复**

  `--verify` 重新加载两条记录，使用匹配当前状态的 v2 备份检查目标图表、迁移前 SQL/datasource/dateFilter/fields、flam 基准哈希、组件 ID 和布局；`--restore` 严格校验目标身份、默认目录、旧/新 SHA，并仅在当前 JSON 与备份 new SHA 一致时按 CAS 恢复，避免覆盖后续人工编辑。

- [ ] **Step 5: 运行边界测试**

  Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_sync_xiuxian_dashboard_visuals.py -q`

  Expected: PASS。

### Task 4: 执行只读演练并应用

**Files:**
- Runtime only: `.codex-runtime/xiuxian-dashboard-visual-sync-backups/`

- [ ] **Step 1: 运行 dry-run**

  Run: `backend/.venv/Scripts/python.exe tools/sync_xiuxian_dashboard_visuals.py`

  Expected: 输出两个目标看板、预计组件变化、新 ROI 视图 ID 和 `applied=false`，不产生数据库 UPDATE。

- [ ] **Step 2: 运行应用**

  Run: `backend/.venv/Scripts/python.exe tools/sync_xiuxian_dashboard_visuals.py --apply`

  Expected: 输出两份备份路径、`applied=true`，事务提交成功。

- [ ] **Step 3: 运行只读验证和幂等检查**

  Run: `backend/.venv/Scripts/python.exe tools/sync_xiuxian_dashboard_visuals.py --verify`; then rerun without `--apply`.

  Expected: 验证通过；第二次 dry-run 报告 `changed=false`，不产生第二个 ROI 图表。

### Task 5: 前端冒烟与交付检查

**Files:**
- No source changes.

- [ ] **Step 1: 检查本地服务**

  Run: `Get-NetTCPConnection -LocalPort 5173,8000,8001 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess`。

  If unavailable, use the repository local runbook to start the four-service stack before UI verification.

- [ ] **Step 2: 检查两个修仙看板**

  Open the local frontend, switch to 修仙, open 核心看板 and ROI看板. Confirm the shared chart types, the new top-right ROI chart, five-row ROI layout, date controls, and no overlap. Confirm flam dashboards are unchanged.

- [ ] **Step 3: Run focused regression tests**

  Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_sync_xiuxian_dashboard_visuals.py tests/test_xiuxian_dashboard_snapshot.py -q`

  Expected: PASS。

- [ ] **Step 4: Report evidence**

  Record migration JSON output, backup paths, verification output, test output, and any UI limitation. Do not stage runtime backups or unrelated worktree changes.

## 执行结果

- 修仙核心看板与 ROI 看板已按目标配置应用；ROI 新图完整继承修仙 `ROI总览` 的执行配置，视图 datasource 为 `8`。
- v2 备份已记录迁移前完整行、原新 JSON SHA-256 及 flam 核心/ROI 基准哈希；`--verify` 已完成迁移前后逐视图对照。
- 聚焦测试覆盖纯转换、字段/布局漂移、幂等、恢复边界、dry-run、CAS 和事务内读回失败。
- 本地浏览器已检查修仙核心/ROI 看板渲染、ROI 五组件布局和新增柱状图，无空组件或重叠。

