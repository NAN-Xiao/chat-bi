# JSON 子字段 SQL 映射修复设计

## 目标

消除 AI SQL 生成把逻辑字段路径错误映射到 JSON 宿主列的风险。例如，`personal.money` 必须生成 `personal` 列上的 `$.money` 路径，不能生成 `ext` 列上的 `$.personal.money`。

该能力适用于所有数据源和工作空间元数据，不包含任何 First Zombie、游戏或特定业务字段的特例。

## 方案

### 1. 保留结构化映射

公式指标、普通指标和筛选条件中的 JSON 子字段必须在规范化结果中保留以下元数据：

- `sourceField`：物理 JSON 列名。
- `jsonPath`：JSON 路径。
- `isJsonSubfield`：字段为 JSON 子字段的标记。
- `expression`：由后端按数据源方言生成的受控 SQL 表达式。

逻辑名称仅用于显示和关联；不得根据点号拆分逻辑名称推测物理列或 JSON 路径。

### 2. 确定性表达式

后端从工作空间字段元数据解析 JSON 子字段，并为 SQL 生成上下文提供已编译的 `expression`。LLM 必须使用该表达式，不能自行重写 JSON 宿主列或路径。

若选中的 JSON 子字段缺少 `sourceField`、`jsonPath` 或可编译的 `expression`，请求应在生成前失败，并提示字段映射配置不完整。

### 3. 生成后校验

生成 SQL 后，校验每个已选择 JSON 子字段是否使用了与元数据一致的 JSON 宿主列和路径。表达式缺失、宿主列不一致或路径不一致时，拒绝执行并返回明确校验错误。

校验不通过时不自动替换为相似字段，也不回退到第一个 JSON 列。

## 数据流

```text
工作空间字段元数据
  -> 指标/筛选配置规范化（保留 sourceField、jsonPath）
  -> 方言表达式编译（expression）
  -> LLM SQL 生成
  -> JSON 表达式语义校验
  -> 只读 SQL 校验与执行
```

## 测试

- JSON 子字段元数据在公式指标规范化后完整保留。
- `personal.money` 的受控表达式使用 `personal` 和 `$.money`。
- SQL 使用错误宿主列或错误路径时被拒绝。
- 缺失映射时生成前失败，不触发 LLM 调用。
- 非 JSON 字段和已有只读 SQL 校验行为保持不变。

## 非目标

- 不恢复向 LLM 发送业务库样例数据。
- 不按业务名称、表名或字段名增加特殊分支。
- 不修改现有用户未提交的前端文件。
