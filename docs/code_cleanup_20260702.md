# 代码清理记录 2026-07-02

本文记录本次业务与代码冗余检查的范围、处理结果和后续技术债。目标是清理确定无用的导入、局部变量和临时脚本，同时不改变当前产品方向、隐藏功能开关和数据权限边界。

## 清理范围

- 前端：围绕 TypeScript/Vue 静态检查中明确可安全处理的未用变量、无效模板写法、冗余布尔转换、无效 `v-memo`、空组件模板、正则多余转义和不必要的 `Function` 类型做小范围修正。
- 后端：使用 Ruff 检查 `F401`、`F841`，清理未用导入、未用局部变量和一个已被字符串注释包住的旧接口块。
- 临时文件：删除根目录两个一次性导入脚本 `tmp_import.ps1`、`tmp_import2.ps1`。这两个脚本包含固定远程地址和明文凭据，不属于可复用项目代码。
- 文档：新增本记录，并在根目录 `README.md` 增加入口。

## 业务边界

- 保留 Smart Q&A 中暂时隐藏的分析/预测相关组件、方法和接口兼容数据，不做永久删除。
- 保留暂时隐藏的主题切换与暗色主题相关代码，不新增入口，也不删除恢复路径。
- 未把 SLG BI 示例数据、指标口径或表名写入平台运行时代码；本次清理仅处理通用代码质量问题。
- 未新增字段、图表、语义层、权限或数据源上下文的静默兼容兜底。
- `backend/apps/datasource/utils/__init__.py` 中的 Excel 工具导入视为包级公开 API，通过 `__all__` 显式声明，而不是删除。

## 已执行检查

前端类型检查：

```powershell
cd frontend
.\node_modules\.bin\vue-tsc.cmd -b --pretty false
```

结果：通过。

前端聚焦 ESLint 检查：

```powershell
cd frontend
.\node_modules\.bin\eslint.cmd . --ext .vue,.js,.ts,.jsx,.tsx --format stylish --rule "prettier/prettier: off" --rule "vue/no-mutating-props: off" --rule "vue/attributes-order: off" --rule "vue/one-component-per-file: off" --rule "vue/require-default-prop: off"
```

结果：`0 errors, 5 warnings`。5 个 warning 均为该聚焦检查临时关闭部分历史规则后暴露出的 `eslint-disable` 未使用提示。

后端未用导入/变量检查：

```powershell
cd backend
uvx ruff check . --select F401,F841 --output-format concise
```

结果：通过。

后端参数未使用检查用于评估但未批量修复：

```powershell
cd backend
uvx ruff check . --select ARG001 --output-format concise
```

结果：仍有 40 个 `ARG001`，需按 API 签名、依赖注入、回调、测试桩和兼容接口逐项确认。

前端完整 ESLint 基线检查：

```powershell
cd frontend
.\node_modules\.bin\eslint.cmd . --ext .vue,.js,.ts,.jsx,.tsx --format stylish --rule "prettier/prettier: off"
```

结果：仍有历史问题，当前为 `109 errors, 15 warnings`，其中 error 主要是仪表盘相关组件的 `vue/no-mutating-props`。

## 已知遗留项

- 前端完整 ESLint 在只关闭 Prettier 时仍有历史 `vue/no-mutating-props` 问题，主要集中在 `DashboardSqlEditor.vue`、`sq-view/index.vue` 和 `CanvasCore.vue` 等仪表盘编辑与画布组件。这类问题需要梳理父子组件数据流，不适合在本次冗余清理中顺手修改。
- 前端完整 Prettier 仍会产生较多格式与换行噪声，本次没有做全仓格式化，避免扩大无关 diff。
- 后端 `ARG001` 未批量修复。该类告警里包含 FastAPI 依赖注入参数、回调签名、测试 monkeypatch 签名和兼容 API 参数，需要按业务路径逐项判断。
- 后端当前虚拟环境未直接提供 Ruff，且 `uv run ruff` 曾受已锁定的 `greenlet` 二进制文件影响；本次使用 `uvx ruff` 完成静态检查。

## 追加修复：租户级鉴权缓存

本次清理后复查发现租户级鉴权缓存存在两个中风险点，已追加修复：

- `USER_INFO` 写入按租户分片后，用户资料、状态、密码、删除和成员关系变更不再依赖操作者 `current_user.tenant_id` 清缓存；改为收集目标用户的所有租户成员关系，并额外包含默认租户分片，统一调用 `clear_user_info_cache(user_id, tenant_ids)` 清理。
- 删除 `single_delete` 和 `clean_user_cache` 两个全仓无调用的用户缓存辅助函数，避免误导维护者以为它们是实际失效路径。
- API Key 鉴权先按未验签 token 中的租户尝试命中租户级缓存；如果查不到，会无条件用不带租户的查询回退一次，再继续做已签名 token 的租户一致性校验。这样可以避免过期/错配的未验签租户导致合法 key 被直接判为 `Invalid access_key`。

追加验证：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q ..\tests\test_apikey_tenant_scope.py tests\test_app_cache.py
uvx ruff check . --select F401,F841 --output-format concise
```

结果：测试 `14 passed`；Ruff `F401,F841` 通过。`apps/system/api/user.py` 仍有 2 个既有 `ARG001`，位于角色校验兼容签名，未在本次缓存风险修复中扩大处理。
