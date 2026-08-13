# AI 看板日期错误修复设计

## 背景

flam AI 看板 100 题测试中，#65 稳定出现 `missing_date_filter`，#96 稳定出现 `realtime_table`。两者都在 Smart Q&A 的 `prepare_sql` 阶段失败，尚未执行 SQL。

## 目标

1. SQL JSON 中包含区间别名（例如 `[2000, +∞)`）时，解析器必须完整保留 `date_filter`。
2. 查询明确指向当前业务日且使用 `event_realtime` 时，受控日期 token 必须能渲染为当前业务日边界。
3. 保持历史表日期模板、实时表选表规则、权限校验和禁止静默回退等现有约束。

## 设计

### JSON 提取

将 `extract_nested_json` 的括号扫描改为字符串感知：只在 JSON 字符串之外维护 `{}`、`[]` 栈，并正确处理反斜杠转义。这样 SQL 字符串中的区间别名、JSON 路径和日期 token 都不会干扰外层 JSON 边界。

不通过给宽松解析器单独补 `date_filter` 来掩盖问题，因为同一缺陷还可能丢失后续新增的结构化字段。

### 实时日期渲染

聊天问题中的“今天”“今日”“当天”统一归一化为通用 `today` 日期预设，避免被默认过去 7 天覆盖。

保留 `prepare_dashboard_date_filter` 对普通 Dashboard 实时表的能力标记；在聊天执行入口增加显式实时策略：仅当 SQL 使用 `event_realtime`、日期配置完整且表达式解析结果严格等于当前业务日时，渲染受控 token。其他实时范围继续返回 `realtime_table`，不自动改查 `event`，也不放宽跨日实时查询。

该策略只解决 Smart Q&A 当前日实时查询，不改变持久 Dashboard 的实时表能力状态。

## 错误处理

- JSON 本身无效时继续走现有宽松解析或格式错误流程。
- `event_realtime` 缺少日期配置、使用非当天范围、参数类型不匹配或 SQL 无法解析时继续显式失败。
- 历史 SQL 的默认日期窗口和日期表达式行为不变。

## 测试

- 回归测试：包含 `[2000, +∞)`、看板日期 token 和完整 `date_filter` 的有效 SQL JSON 能被完整解析。
- 回归测试：当天 `event_realtime` SQL 可渲染成单日 `yyyymmdd` 边界。
- 回归测试：“今天”问题归一化为 `today`，不回退为过去 7 天。
- 保护测试：跨日或历史范围的 `event_realtime` 仍报 `realtime_table`。
- 运行日期过滤、Smart Q&A 和通用 JSON 工具相关测试。
