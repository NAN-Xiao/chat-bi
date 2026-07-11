# First Zombie 语义口径修复设计

## 目标

修复 datasource `3`（`flam` / `first_zombie`）的支付、国家、留存/LTV 与事件 JSON 字段语义，使新生成 SQL 和已保存看板都使用已验证的业务字段与成熟窗口。

## 证据与边界

- `ServerPayLog.personal.money`、`personal.orderId`、`personal.productid` 在最近 7 天样本中完整存在；`ext` 对应支付路径为空。
- `ServerPayLog.userinfo.country` 完整存在，`currentinfo.country` 为空；跨充值与活跃的国家筛选统一使用 `userinfo.country`。
- `ServerPayLog.personal.money` 日汇总与 `user.pay.paytotal` 日差分在抽样日期逐日对账一致。
- `PAY_EVENTS` 含支付流程事件，不能作为真实交易订单或付费用户的默认集合。交易类指标以 `ServerPayLog` 为准；流程量作为独立指标。
- `pay7`、`pay30` 在未成熟用户中可能已为正值；LTV 与留存必须按 cohort 年龄/目标快照日限制，未成熟结果返回空而非零。
- `event.time` 可用于实时/小时分析；历史日趋势优先使用 `dt` 分区。默认窗口不得在 ADS 大视图中直接执行 `MAX(dt)`。

## 修复范围

### 语义配置与种子

更新 First Zombie 专属 tracking 字典和 Data Skill 种子：

- 交易金额、订单号、礼包 ID 固定为 `ServerPayLog.personal.money`、`personal.orderId`、`personal.productid`。
- 支付流程事件量与真实充值次数/人数分离命名和 SQL。
- 新增付费用户使用 `user.pay.firstpaytime`，不再使用窗口内 `MIN(event.dt)`。
- ARPU/ARPPU、付费率、LTV、留存使用已定义的分母、成熟窗口和最新完整分区规则。
- CCU、建筑和出征的已验证字段从 `ext` 改为对应 `personal` 路径。

### 已保存看板

通过可重复执行的 First Zombie 更新脚本修复 datasource `3` 已保存组件：

- 付费概览中的礼包/商品结构不再从 `ext` 读取。
- 主城建设中的建筑 ID、主城等级不再从 `ext` 读取。
- 出征数据中的主城等级和战力不再从 `ext` 读取。
- 修复范围限定为已识别的 datasource `3` 组件；不会批量修改用户自定义字段或其它数据源。

## 不做的事

- 不在通用前端、后端或 SQL 修复器中硬编码游戏业务规则。
- 不把不同支付流程事件的商品字段强行统一为 `personal.productid`；未确认映射的事件只能按事件类型展示或排除交易指标。
- 不为当前“加速类型”卡猜测替代字段。`ext.ed_detailReason` / `ext.ed_route` 在样本中为空且未发现等价字段；该卡保留明确的缺少映射状态。
- 不通过全表 `MAX(dt)` 生成默认窗口。

## 实现方式

1. 先为种子 SQL/规则补充回归测试，覆盖 `personal` 路径、`ServerPayLog` 交易集合、首次付费与成熟 cohort。
2. 修改 First Zombie 专属 seed 脚本与持久化看板 SQL 定义。
3. 运行幂等 seed/修复脚本，将规则与已保存组件同步至 datasource `3`。
4. 在最近完整分区及最近 7 天窗口上执行只读对账，验证 ARPU、订单、商品路径和留存/LTV 的成熟限制。

## 验收标准

- 新生成的 First Zombie ARPU SQL 使用 `ServerPayLog.personal.money` 和 `UserActive.uid`。
- `ServerPayLog` 的国家筛选使用 `userinfo.country`。
- 已修复组件不再出现 `JSON_EXTRACT(e.ext, ...)` 的受影响路径。
- 真实充值/订单/付费用户指标不再使用多事件流程集合直接计数。
- 未成熟 cohort 不参与相应的 LTV/留存分母或分子。
- 所有 seed 脚本可重复运行，且相关单元测试、静态检查和目标 SQL 对账通过。
