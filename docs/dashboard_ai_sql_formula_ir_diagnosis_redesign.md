# 手动看板 AI SQL 公式 IR 与诊断节点重构方案

## 背景

当前手动看板点击“计算/生成”时，前端会把图表配置提交到后端 `dashboard/ai_sql_generate` 接口。后端通过 Agent graph 串行执行配置理解、配置诊断、SQL 生成和 SQL 校验。

现有问题是：LLM 诊断节点同时承担“理解配置”“判断配置是否合法”“决定是否阻断 SQL 生成”三个职责。对于自定义公式，尤其是 `atomicMetric` 跨事件公式，例如：

```text
ARPU = 后端充值金额求和 / 当日活跃用户去重数
```

SQL 生成节点本身可以先分别聚合 `ServerPayLog` 和 `UserActive`，再在外层做除法。但诊断节点可能把它误判为“两个事件直接聚合，会导致行数膨胀”，从而阻断 SQL 生成。

重构目标是：不再保留“LLM 诊断节点拥有阻断权”的旧形态，改为代码层确定性校验做裁判，LLM 只负责解释和建议。

## 目标

- 自定义公式先被解析为可验证、可生成 SQL 的公式 IR。
- 是否阻断由确定性校验决定，不由 LLM 直接决定。
- LLM 只解释意图、风险提醒和优化建议。
- 复杂公式不因“复杂”本身被阻断；只有超出当前公式语言能力或配置不完整时才阻断。
- 后续公式能力扩展通过显式语法和代码生成能力演进，而不是让 LLM 猜 SQL。

## 新链路

建议把现有链路：

```text
collect_context
  -> understand_config
  -> diagnose_config
  -> generate_sql
  -> validate_sql
  -> finalize_response
```

重构为：

```text
collect_context
  -> normalize_manual_config
  -> build_formula_ir
  -> deterministic_validate
  -> build_sql_plan
  -> generate_sql
  -> validate_sql
  -> explain_advice
  -> finalize_response
```

其中：

- `normalize_manual_config`：把前端配置整理成后端稳定结构。
- `build_formula_ir`：把分析指标、公式指标、`atomicMetric`、运算符、括号和数字常量解析成公式 IR。
- `deterministic_validate`：代码层判断是否可生成 SQL。
- `build_sql_plan`：确定基础聚合、过滤、时间粒度、分组和外层公式计算方式。
- `generate_sql`：根据当前配置和 SQL plan 生成 SQL。
- `explain_advice`：LLM 根据代码层结果解释 warnings / suggestions，不拥有阻断权。

## 公式 IR 设计

公式 IR 不应该保存为一段自然语言，而应该保存成结构化表达式树。

示例：

```json
{
  "formula": {
    "alias": "arpu",
    "decimal_places": 2,
    "expression": {
      "type": "binary",
      "operator": "/",
      "left": {"type": "metric_ref", "id": "revenue"},
      "right": {"type": "metric_ref", "id": "active_users"}
    }
  },
  "base_metrics": [
    {
      "id": "revenue",
      "source": "atomicMetric",
      "event": "ServerPayLog",
      "field": "personal.money",
      "aggregation": "sum"
    },
    {
      "id": "active_users",
      "source": "atomicMetric",
      "event": "UserActive",
      "field": "uid",
      "aggregation": "count_distinct"
    }
  ]
}
```

这样系统能明确知道：跨事件并不是直接混聚合，而是先生成两个基础聚合，再在外层计算公式。

## 阻断与非阻断规则

只有代码层可以产生阻断。

阻断示例：

- 没有数据源。
- 公式 token 不完整，例如 `A /`。
- 括号不匹配。
- 除法缺少分母。
- 明确除以常量 `0`。
- `metric` token 引用了不存在的基础指标。
- `atomicMetric` 缺少字段、事件、计算字段或聚合方式。
- `sum` / `avg` 选择了非数值字段。
- 字段不存在或用户无权限。
- 需要跨表计算但没有明确关联规则。
- 生成 SQL 不是只读 `SELECT` / `WITH`。

非阻断示例：

- 分子分母来自不同事件。
- 公式较复杂，但能被 IR 正确解析。
- 图表标题是默认值。
- 指标别名不清晰。
- 图表类型不够适合。
- `selectedFields` 包含未使用字段。
- 全局筛选同时作用于分子和分母，但字段合法且用户明确配置。

## LLM 诊断的新职责

LLM 不再输出最终 `success=false` 决策。后端可以让 LLM 根据确定性校验结果生成说明：

```json
{
  "can_generate_sql": true,
  "blocking": [],
  "warnings": [
    {
      "code": "cross_event_formula",
      "message": "公式分子分母来自不同事件，系统会先分别聚合再相除。"
    }
  ],
  "suggestions": []
}
```

LLM 只返回用户可读文案，例如：

```json
{
  "intent": "分析近 30 天每日 ARPU",
  "message": "配置可以生成 SQL。",
  "advice": "当前公式会按日分别计算充值总额和活跃用户数，再计算 ARPU。",
  "suggestions": []
}
```

即使 LLM 文案里出现“建议调整”或“需要确认”，也不能覆盖代码层的 `can_generate_sql=true`。

## 第一版公式语言边界

第一版建议支持：

- 基础分析指标引用。
- 公式内 `atomicMetric`。
- 运算符 `+ - * /`。
- 括号。
- 数字常量。
- 小数位 `ROUND`。
- 除法自动使用 `NULLIF(分母, 0)`。
- 多个公式指标。
- 公式指标与普通分析指标混用。

第一版明确不支持并阻断：

- 公式引用另一个公式指标。
- 自定义函数，例如 `LOG(A)`、`SQRT(A)`。
- 条件表达式，例如 `IF(A > 0, B, C)`。
- 窗口函数。
- 跨数据源公式。
- 没有语义关联规则的跨表公式。
- 循环引用。

## 长期公式语言扩展

公式 IR 的目标不是限制复杂度，而是把复杂公式变成可验证、可生成 SQL 的表达式树。后续演进应把公式语言扩展为显式能力，而不是让 LLM 临场猜测。

长期可以把公式语言扩展，比如第二版支持：

- 条件表达式：`IF(condition, true_value, false_value)`，用于“满足条件才计入”一类指标。
- 空值和除零保护：`COALESCE(A, 0)`、`NULLIF(A, 0)`，用于显式表达兜底策略。
- 安全标量函数：`ABS(A)`、`ROUND(A, n)` 等只依赖当前行或当前聚合结果的函数。
- 时间对比类公式：同比、环比、固定偏移周期对比。
- 时间窗口类公式：移动平均、滚动求和、累计值。
- 排名类公式：窗口内排名、分组内 TopN。
- 模板化复合公式：留存、转化、漏斗等由多阶段基础指标组合而成的公式。

这些扩展不能通过“LLM 看到复杂公式后直接自由生成 SQL”来实现，而应该逐个注册为公式语言能力。每类能力都需要定义：

- 语法形式，例如函数名、参数个数、参数类型和是否允许嵌套。
- IR 节点类型，例如 `condition`、`function_call`、`time_shift`、`window_metric`、`funnel_template`。
- 输入输出类型，例如数值、布尔、日期、维度字段、聚合指标。
- 校验规则，例如函数白名单、字段类型约束、时间粒度约束、跨表关联约束。
- SQL 生成规则，例如是否需要子查询、窗口函数、时间自连接或多阶段 CTE。
- 前端编辑约束，例如函数选择器、参数提示、非法组合即时提示。

这些能力上线前需要同时补齐：

- 公式 parser。
- IR 节点类型。
- 确定性校验规则。
- SQL 生成规则。
- 单元测试和快照测试。
- 前端公式编辑器可视化约束。

原则是：每扩展一种公式能力，都必须让代码层显式知道它的语法、输入类型、输出类型和 SQL 生成方式。

## 前端交互调整

前端应按后端返回的问题等级展示：

- `blocking`：阻断生成，按钮停在配置页，弹出“需要修正的问题”。
- `warnings`：不阻断，SQL 正常生成，同时在建议弹窗展示风险提醒。
- `suggestions`：不阻断，只作为优化建议。

生成 SQL 后，即使存在 warning，也应该进入 SQL 明细页。

## 测试要求

需要覆盖：

- 合法 ARPU 公式不阻断。
- 合法 ARPPU 公式不阻断。
- 付费率、转化率等跨事件分子分母公式不阻断。
- 公式 token 不完整会阻断。
- 括号不匹配会阻断。
- `sum` 非数值字段会阻断。
- 无权限字段会阻断。
- 跨事件公式产生 warning，但继续生成 SQL。
- LLM advice 不能把 `can_generate_sql=true` 改成 false。

## 迁移建议

建议分三步做：

1. 新增 `formula_ir` 和 `deterministic_validator`，先在现有接口中旁路运行并写测试。
2. 从运行时 graph 中删除旧的 `understand_config` / `diagnose_config` LLM 节点，改由 `deterministic_validate` 控制是否继续生成 SQL。
3. 删除旧的关键词降级函数和 LLM 阻断分支，统一使用确定性校验结果控制流程；`explain_advice` 只合并 warnings / suggestions，不拥有阻断权。
