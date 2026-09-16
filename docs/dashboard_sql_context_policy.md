# 图表配置生成 SQL 的上下文策略

图表配置通过 `/dashboard/ai_sql_generate` 生成 SQL 时，仅采用平台级（`PLATFORM_PUBLIC`）Data Skill。工作空间级、个人级 Data Skill 和知识库文档不参与该流程。

## 生效范围

- 上下文收集：使用当前用户有权限的数据源、表字段元数据、事件字典、图表配置和平台级 Data Skill，不加载知识库。
- SQL 生成与修复：共用上述上下文，不注入知识库正文或知识库优先级规则。
- SQL 校验：保留结果契约、字段映射、方言和只读校验，不调用知识库冲突裁决；JSON 路径与当前配置冲突时明确报错。

平台级 Data Skill 仍受原有启用状态、可见性、用户停用偏好、工作空间排除列表、数据源范围、所需表权限和使用场景限制。“仅平台级”不表示无条件加载所有平台 Skill。

作用域过滤在相关性排序和同名 Skill 覆盖处理之前执行，避免工作空间或个人规则替换平台规则。调用方传入非平台 Skill ID 时，该条目不会进入上下文，也不会自动替换成其他 Skill。没有匹配的平台 Skill 时，继续依据显式图表配置和授权元数据处理，不回退到知识库或其他作用域 Skill。

## 维护入口

- `backend/apps/chat/curd/custom_prompt.py`：`find_data_skills(..., platform_only=True)` 在召回前限定条目作用域。
- `backend/apps/datasource/crud/sql_engine.py`：`BusinessSqlContextService.build(..., platform_data_skills_only=True)` 将该策略传给共享 Skill 服务。
- `backend/apps/dashboard/crud/ai_sql_generator.py`：图表配置入口固定启用平台级限制。

共享服务的默认策略仍允许当前用户可用的其他作用域 Skill。智能问数、分析助手等入口的知识库及 Data Skill 策略保持原有行为。

## 回归验证

对应测试覆盖自动召回、显式 Skill ID、同名覆盖、模型选择、数据源和工作空间排除条件，以及 SQL 生成、修复和校验不使用知识库。

在 `backend` 目录运行：

```text
python -m pytest tests/test_custom_prompt_datasource_scope.py tests/test_sql_engine_context.py tests/test_dashboard_ai_sql_generator.py tests/test_knowledge_authority.py -q
```
