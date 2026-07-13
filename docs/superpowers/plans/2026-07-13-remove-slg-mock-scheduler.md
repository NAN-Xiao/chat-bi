# 移除 SLG Mock 定时滚动造数子系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完整删除 SLG Mock 定时滚动造数的运行、镜像、部署和发布入口，同时保持一次性数据库初始化与 `--recreate` 重建能力不变。

**Architecture:** 删除独立调度子系统的专属文件，并从共享 Compose 与发布文档中移除引用。基础造数器保持原样，通过文件差异检查和既有回归测试证明重建链路未受影响。

**Tech Stack:** Python 3、pytest、Docker Compose YAML、Markdown、Git

## Global Constraints

- 不修改 `tools/create_slg_bi_mock_db.py`。
- 不修改 `tools/create_slg_bi_mock_db_prod.py`。
- 不连接、删除或迁移任何数据库及 `mock_generation_state` 表。
- 不删除基础生成器中的 `auto_gen_time`、日期过滤、ID 偏移或过期清理函数。
- 不修改专题看板补数、Data Skills 或其他 `seed_slg_bi_*` 脚本。
- Git 提交信息使用中文。

---

### Task 1: 建立基础生成器回归基线

**Files:**
- Test: `tests/test_slg_mock_auto_gen_time.py`
- Verify: `tools/create_slg_bi_mock_db.py`
- Verify: `tools/create_slg_bi_mock_db_prod.py`

**Interfaces:**
- Consumes: 现有一次性造数入口和自动生成字段回归测试。
- Produces: 删除定时子系统前的可重复验证基线。

- [ ] **Step 1: 运行基础生成器专项测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_slg_mock_auto_gen_time.py -q
```

Expected: 全部测试通过，退出码为 `0`。

- [ ] **Step 2: 验证一次性造数入口参数**

Run:

```powershell
backend\.venv\Scripts\python.exe tools/create_slg_bi_mock_db.py --help
```

Expected: 输出包含 `--recreate`、`--db-name`、`--players`、`--start-date`、`--days` 和 `--seed`，退出码为 `0`。

- [ ] **Step 3: 记录两个基础生成器的当前对象哈希**

Run:

```powershell
git hash-object tools/create_slg_bi_mock_db.py tools/create_slg_bi_mock_db_prod.py
```

Expected: 输出两行 Git 对象哈希；最终验证时输出必须完全一致。

### Task 2: 删除定时运行和部署子系统

**Files:**
- Delete: `tools/slg_bi_mock_scheduled_generator.py`
- Delete: `tests/test_slg_mock_scheduled_generator.py`
- Delete: `Dockerfile.slg-mock-generator`
- Delete: `Jenkinsfile.slg-mock-generator`
- Delete: `deploy/slg_mock_generator.yaml`
- Modify: `docker-compose.yaml:49`

**Interfaces:**
- Consumes: Task 1 的基础生成器基线。
- Produces: 不再包含定时造数运行、镜像、CI 或 Compose 启动入口的仓库配置。

- [ ] **Step 1: 删除专属运行和部署文件**

使用补丁完整删除五个专属运行/部署文件和专项测试文件，不修改任何基础造数器文件。

- [ ] **Step 2: 从 Compose 删除定时造数服务**

从 `docker-compose.yaml` 删除从下列服务头开始、到 `networks:` 前结束的完整区块：

```yaml
  slg-mock-generator:
```

保留 `shuzhi` 服务和顶层 `networks` 配置不变。

- [ ] **Step 3: 验证 Compose 和运行入口已清除**

Run:

```powershell
docker compose -f docker-compose.yaml config --quiet
rg -n "slg_bi_mock_scheduled_generator|slg-mock-generator|slg_mock_generator.yaml|mock-data" docker-compose.yaml Dockerfile* Jenkinsfile* deploy tools tests
```

Expected: Compose 校验退出码为 `0`；`rg` 不返回任何有效匹配。

- [ ] **Step 4: 提交运行和部署删除**

```powershell
git add -A -- Dockerfile.slg-mock-generator Jenkinsfile.slg-mock-generator deploy/slg_mock_generator.yaml tools/slg_bi_mock_scheduled_generator.py tests/test_slg_mock_scheduled_generator.py docker-compose.yaml
git commit -m "移除SLG定时造数运行子系统"
```

Expected: 提交成功，仅包含上述文件。

### Task 3: 清理专项文档和共享发布说明

**Files:**
- Delete: `docs/slg_bi_mock_hourly_generator.md`
- Delete: `docs/slg_bi_mock_docker_release.md`
- Modify: `docs/docker_release_guide.md:1`

**Interfaces:**
- Consumes: Task 2 删除后的运行和部署边界。
- Produces: 只描述仍然存在的主应用 Docker 发布能力的文档集合。

- [ ] **Step 1: 删除两份定时造数专项文档**

使用补丁完整删除：

```text
docs/slg_bi_mock_hourly_generator.md
docs/slg_bi_mock_docker_release.md
```

- [ ] **Step 2: 清理共享 Docker 发布指南**

在 `docs/docker_release_guide.md` 中：

- 从“当前发布模型”表格删除 `Dockerfile.slg-mock-generator` 和 `deploy/slg_mock_generator.yaml` 两行。
- 完整删除“## 四、SLG BI Mock 造数器镜像”章节。
- 将后续一级章节编号依次前移，保持从“一”到“十四”连续。
- 保留主应用 Dockerfile、Jenkins、Compose、systemd、Nginx、回滚和排障内容不变。

- [ ] **Step 3: 验证文档残留引用**

Run:

```powershell
rg -n --hidden -S "slg_bi_mock_scheduled_generator|slg-mock-generator|slg_mock_generator.yaml|Dockerfile.slg-mock-generator|Jenkinsfile.slg-mock-generator|mock-data" -g '!node_modules/**' -g '!.git/**' -g '!.codegraph/**'
```

Expected: 除设计文档和本实施计划用于描述已删除范围的历史说明外，不存在有效运行、部署或使用引用。

- [ ] **Step 4: 提交文档清理**

```powershell
git add -A -- docs/slg_bi_mock_hourly_generator.md docs/slg_bi_mock_docker_release.md docs/docker_release_guide.md docs/superpowers/plans/2026-07-13-remove-slg-mock-scheduler.md
git commit -m "清理SLG定时造数发布文档"
```

Expected: 提交成功，仅包含专项文档删除、共享指南调整和本实施计划。

### Task 4: 最终回归与范围审计

**Files:**
- Verify: `tools/create_slg_bi_mock_db.py`
- Verify: `tools/create_slg_bi_mock_db_prod.py`
- Test: `tests/test_slg_mock_auto_gen_time.py`
- Verify: `docker-compose.yaml`

**Interfaces:**
- Consumes: Task 1 的哈希基线和 Task 2、Task 3 的提交结果。
- Produces: 基础重建链路未受影响、定时子系统已完整移除的验证证据。

- [ ] **Step 1: 重新运行基础生成器专项测试**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest tests/test_slg_mock_auto_gen_time.py -q
```

Expected: 与 Task 1 一致，全部测试通过。

- [ ] **Step 2: 重新验证一次性造数入口**

Run:

```powershell
backend\.venv\Scripts\python.exe tools/create_slg_bi_mock_db.py --help
```

Expected: 仍包含 `--recreate` 及基础造数参数，退出码为 `0`。

- [ ] **Step 3: 对比基础生成器哈希并检查变更范围**

Run:

```powershell
git hash-object tools/create_slg_bi_mock_db.py tools/create_slg_bi_mock_db_prod.py
git diff HEAD~2..HEAD -- tools/create_slg_bi_mock_db.py tools/create_slg_bi_mock_db_prod.py
git status --short
```

Expected: 哈希与 Task 1 完全一致；基础生成器 diff 为空；工作区只允许存在用户已有的无关改动。

- [ ] **Step 4: 最终检查 Compose 与全仓有效引用**

Run:

```powershell
docker compose -f docker-compose.yaml config --quiet
rg -n --hidden -S "slg_bi_mock_scheduled_generator|slg-mock-generator|slg_mock_generator.yaml|Dockerfile.slg-mock-generator|Jenkinsfile.slg-mock-generator|mock-data" -g '!node_modules/**' -g '!.git/**' -g '!.codegraph/**' -g '!docs/superpowers/specs/2026-07-13-remove-slg-mock-scheduler-design.md' -g '!docs/superpowers/plans/2026-07-13-remove-slg-mock-scheduler.md'
```

Expected: Compose 校验通过；全仓有效引用检索无结果。
