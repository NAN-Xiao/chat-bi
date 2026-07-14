# 修仙埋点对象参数展开 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于修仙项目真实事件样本，将后端 `object` 参数安全展开为 Excel 事件参数字典中的 JSON 子字段。

**Architecture:** 单个 Node.js 构建器使用 `@oai/artifact-tool` 读取已有模板和原始打点定义，并通过只读 MySQL 查询采样候选事件。构建器在本地解析 `personal` JSON，仅将有样本的标量叶子字段写入输出工作簿；未采样对象保持原参数行并标明采样状态。

**Tech Stack:** Node.js、`@oai/artifact-tool`、Python `pymysql`、Excel `.xlsx`。

## Global Constraints

- 采样源固定为 `xtxdj.event`，产品视图已限定为 `110000047`。
- 采样窗口固定为 `user` 视图最大业务日期向前 28 天。
- 不执行 `event` 的无索引聚合、逐字段 JSON 过滤或全历史扫描。
- 仅将真实样本中出现的 JSON 叶子字段写入字典；未采样对象不使用原表样例补全。
- 保持“事件参数对照”页既有列顺序、表格结构、事件分组与视觉样式。
- 最终工作簿输出至 `outputs/xiuxian_tracking_fill/tracking_dictionary_template_xiuxian.xlsx`。

---

### Task 1: 构建受限采样和 JSON 路径清单

**Files:**
- Create: `outputs/xiuxian_tracking_fill/build_xiuxian_object_parameters.mjs`
- Read: `D:/AIWork3/djinchao/chat-bi/docs/修仙项目-BI打点整理.xlsx`
- Read: `outputs/xiuxian_tracking_fill/tracking_dictionary_template.xlsx`
- Test: `outputs/xiuxian_tracking_fill/xiuxian_object_sampling_summary.json`

**Interfaces:**
- Consumes: 后端页字段列 `事件名称(event)`、`参数名`、`参数说明`、`参数类型`、`备注说明`。
- Consumes: 数据库候选行 `(event, personal)`，时间范围为 `[max(user.dt)-27 天, max(user.dt)]`。
- Produces: `SampledObjectParameter[]`，其中包含 `eventName`、`propertyName`、`leafPath`、`sampleType`、`examples`、`parentDescription` 与 `sampleCount`。

- [ ] **Step 1: 从原始后端页识别 object 参数并继承事件名**

在构建器中读取“后端”页的已用区域；当当前行的事件名为空时，沿用最近一个非空事件名。仅收集 `参数类型` 等于 `object` 的行，并保留父参数说明与备注。

```js
let currentEventName = "";
for (const row of backendRows.slice(1)) {
  if (text(row[3])) currentEventName = text(row[3]);
  if (currentEventName && text(row[7]).toLowerCase() === "object" && text(row[5])) {
    objectParameters.push({ eventName: currentEventName, propertyName: text(row[5]) });
  }
}
```

- [ ] **Step 2: 以受限 SQL 读取候选事件行**

Python 子进程先执行 `SELECT MAX(dt) FROM user`，再使用计算出的 28 天范围和 object 参数的事件名集合查询 `event` 视图。查询只返回 `event, personal`，并使用 `LIMIT 5000`。

```sql
SELECT event, personal
FROM event
WHERE dt BETWEEN %s AND %s
  AND event IN (%s, ...)
LIMIT 5000
```

- [ ] **Step 3: 在本地递归展开 JSON 值**

对象键使用 `.` 拼接，数组对象元素使用 `[]` 标记。字符串值仅在内容本身是有效 JSON 对象或数组时继续解析；普通文本保持为叶子值。

```js
function flattenJson(value, path) {
  if (Array.isArray(value)) return value.flatMap((item) => flattenJson(item, `${path}[]`));
  if (isPlainObject(value)) return Object.entries(value).flatMap(([key, item]) => flattenJson(item, `${path}.${key}`));
  return [{ path, type: inferScalarType(value), example: value }];
}
```

- [ ] **Step 4: 写出可审计的采样摘要**

将采样窗口、object 参数总数、已命中参数数、每个叶子字段的路径、类型和最多三个示例写入 `xiuxian_object_sampling_summary.json`。摘要不得写入数据库凭据或原始完整用户数据。

- [ ] **Step 5: 验证采样边界**

运行构建器的采样阶段，确认摘要中没有凭据、没有 `object` 父字段被当作叶子字段，且无样本参数明确标记为 `sampleCount: 0`。

Run: `C:\Users\elex\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe outputs\xiuxian_tracking_fill\build_xiuxian_object_parameters.mjs --sample-only`

Expected: 生成采样摘要，且所有展开叶子路径均附带至少一个真实样本。

### Task 2: 生成并校验最终工作簿

**Files:**
- Modify: `outputs/xiuxian_tracking_fill/build_xiuxian_object_parameters.mjs`
- Create: `outputs/xiuxian_tracking_fill/tracking_dictionary_template_xiuxian.xlsx`
- Create: `outputs/xiuxian_tracking_fill/preview_tracking_dictionary_template_xiuxian.png`
- Test: `outputs/xiuxian_tracking_fill/xiuxian_object_parameter_check.ndjson`

**Interfaces:**
- Consumes: Task 1 输出的 `SampledObjectParameter[]`。
- Consumes: 模板“事件参数对照”页的 9 列结构。
- Produces: 保留事件块的表格行；已采样 `object` 参数替换为子字段行，未采样对象行保留并标记。

- [ ] **Step 1: 读取模板并定位“事件参数对照”页**

使用 `SpreadsheetFile.importXlsx` 读取现有模板，读取 `A1:I` 已用区和现有格式。不要修改其他工作表、工作簿名称或模板中的公式。

```js
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sheet = workbook.worksheets.getItem("事件参数对照");
const existingRows = sheet.getUsedRange(true).values;
```

- [ ] **Step 2: 按事件块替换已采样 object 参数**

对每个事件参数行，根据 `(事件名, 属性名)` 查找采样结果。命中时移除父对象行，按叶子路径写入新行；第一行保留事件列 A-D，后续行保持为空，以延续模板的分组表现。未命中时保留父行，并把备注更新为“参数说明；近 28 天未采样到 JSON 子字段，保留对象参数”。

```js
const description = compactJoin([
  parentDescription,
  leafMeaning,
  exampleText && `示例：${exampleText}`,
]);
rows.push([eventName, eventDisplayName, eventDescription, eventTag, "personal", leafPath, leafDisplayName, leafType, description]);
```

- [ ] **Step 3: 填写可确认的子字段含义**

子字段备注必须以父参数说明开头。对可由字段名确定的通用含义，写入明确说明，例如 `itemId` 为物品 ID、`itemNum` 为物品数量、`seat` 为阵位、`level` 为等级、`heroid` 为长老 ID、`petid` 为灵兽 ID、`WORLD_ZHU_GUO` 为世界资源朱果。无法确认语义的动态 ID 子键只说明“子键为游戏内效果/枚举 ID，值为对应数值”。

- [ ] **Step 4: 保持既有格式并输出**

复制原工作簿后仅重写“事件参数对照”的内容区域，延续表头、列宽、冻结首行、自动换行、边框和事件块内 A-D 列的无横线分组规则。导出到指定输出路径。

```js
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
```

- [ ] **Step 5: 内容、公式与视觉校验**

使用 `workbook.inspect` 检查资源变化、抽卡、阵容等代表性事件块，断言有样本对象已经变为子路径，未采样对象仍保留父路径且备注含“未采样”。扫描 `#REF!|#DIV/0!|#VALUE!|#NAME\?|#N/A`，渲染“事件参数对照”页前 100 行并检查表头、列宽、换行和分组边框。

Run: `C:\Users\elex\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe outputs\xiuxian_tracking_fill\build_xiuxian_object_parameters.mjs`

Expected: 最终 `.xlsx`、采样摘要、代表性检查和预览图全部生成；公式错误扫描为空。
