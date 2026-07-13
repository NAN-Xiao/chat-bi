# 移除 SLG Mock 定时滚动造数子系统设计

## 背景

仓库当前同时包含一次性 SLG Mock 基础造数器和独立定时滚动造数子系统。当前需求是完整移除定时滚动运行、部署和发布能力，同时保证手工初始化、重新创建数据库及基础明细生成逻辑不受影响。

## 目标

- 删除定时滚动造数器的运行代码、镜像、部署配置、CI、专项测试和专项文档。
- 清除 Compose 和通用发布文档中的定时造数器引用。
- 保持一次性基础造数器的命令、参数、Schema 创建和数据生成行为不变。
- 删除后仓库中不再存在可启动定时造数器的入口。

## 不在范围内

- 不修改 `tools/create_slg_bi_mock_db.py`。
- 不修改 `tools/create_slg_bi_mock_db_prod.py`。
- 不删除基础生成器中的 `auto_gen_time`、日期过滤、ID 偏移或过期清理函数。
- 不删除或迁移现有数据库中的 `mock_generation_state` 表。
- 不修改专题看板补数、Data Skills 或其他 `seed_slg_bi_*` 脚本。

## 删除范围

删除以下定时造数子系统专属文件：

- `tools/slg_bi_mock_scheduled_generator.py`
- `tests/test_slg_mock_scheduled_generator.py`
- `Dockerfile.slg-mock-generator`
- `Jenkinsfile.slg-mock-generator`
- `deploy/slg_mock_generator.yaml`
- `docs/slg_bi_mock_hourly_generator.md`
- `docs/slg_bi_mock_docker_release.md`

修改以下共享文件：

- 从 `docker-compose.yaml` 删除 `slg-mock-generator` 服务和 `mock-data` profile 配置。
- 从 `docs/docker_release_guide.md` 删除定时造数器镜像、配置、运行和发布说明；保留主应用发布说明。

## 保留的重建链路

数据库重新创建仍使用现有独立链路：

```text
tools/create_slg_bi_mock_db.py
  -> create_slg_bi_mock_db_prod.main()
  -> ensure_database(args)
  -> generate(args)
```

典型命令保持不变：

```powershell
python tools/create_slg_bi_mock_db.py --db-name slg_bi_mock --recreate
```

`--players`、`--start-date`、`--days`、`--seed`、`--id-offset` 和 `--auto-gen-time` 等现有参数继续可用。

## 数据与兼容性

本次变更只删除仓库中的定时运行能力，不连接或修改任何数据库。已经由定时造数器写入的业务明细、`auto_gen_time` 字段和 `mock_generation_state` 状态记录保持原状。后续如需清理线上状态表，应作为独立数据库变更评审，不能隐含在本次代码删除中。

## 验证方案

1. 全仓检索不再出现 `slg_bi_mock_scheduled_generator`、`slg-mock-generator`、`slg_mock_generator.yaml` 或 Compose `mock-data` profile 的有效引用。
2. 运行 `tests/test_slg_mock_auto_gen_time.py`，确认基础生成器仍满足 Schema、写入列和清理逻辑约束。
3. 运行基础生成器的参数帮助命令，确认一次性造数入口可加载且仍包含 `--recreate`。
4. 解析 `docker-compose.yaml`，确认删除服务后配置仍合法。
5. 检查 Git diff，确认两个基础造数器文件没有变更。

## 风险与回退

- 删除独立 Jenkinsfile 后，原定时造数镜像不能再从本仓库构建发布，这是预期结果。
- 已经运行中的外部容器不会因代码提交自动停止；其下线属于部署环境操作，不在本次仓库变更范围内。
- 如需回退，可恢复本次删除的专属文件及共享文件中的引用，不涉及数据库回滚。

## 验收标准

- 仓库不再提供定时滚动造数的代码、镜像、部署或 CI 入口。
- 一次性数据库初始化和 `--recreate` 重建能力完整保留。
- 基础造数器文件无改动，相关回归测试通过。
- Compose 配置合法，主应用服务不受影响。
