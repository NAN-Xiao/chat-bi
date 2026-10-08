# 排行榜内置浏览器验收

2026-09-30。Codex 内置浏览器真实操作，没有注入组件状态、伪造响应或修改前端文件。

工作树 `D:/AIWork6/release_1.3.0`，分支 `release/release_1.3.0`。当前工作空间 gig、授权数据源 12。独立测试看板“排行榜编译验收-20260930”，ID `1990f7c87a5e45a0836a8c87fa4f5a1c`。

有界查询核对最大业务日为 2026-09-29，最近 28 天范围为 **2026-09-02—2026-09-29**。只读取 1548 条相关业务明细，用独立 Python 计数；不创建业务聚合表或视图。

| 场景 | 结果 |
|---|---|
| 国家主体、注册次数、默认排序 | ROW_NUMBER 模板，CN=200 |
| 附加登录次数 | CN 注册=200，登录=1347，独立聚合不相乘 |
| 同时展示媒体来源 | 主体对应多值，明确显示 RANKING_PROPERTY_CONFLICT，清空旧预览 |
| 改为唯一国家属性 | 恢复五个业务列，内部 guard 不展示 |
| 并列且跳过 | RANK 模板实际执行成功 |
| 并列不跳过 + 升序 | DENSE_RANK 与 ASC 实际执行成功 |
| 应用、保存、刷新 | 看板显示 1 / CN / 200 / 1347 / CN |
| 重开编辑 | 主体、事件、附加指标别名、属性、升序、并列规则及日期完整恢复；保存前后及重新生成的 SQL 均逐字一致，预览成功 |

业务样本只有一个非空国家，实际并列由 PostgreSQL 多主体 VALUES 测试验证：ROW_NUMBER 为 1/2/3、RANK 为 1/1/3、DENSE_RANK 为 1/1/2。

浏览器最终 SQL 再执行，与独立明细计数比较 **1 行 6 单元格完全一致**（含 guard=0）。业务字段和事件名只用于验收，不进入平台编译逻辑。

实际浏览器生成日志：

| request_id | 编译耗时 | llm_calls | http_attempts |
|---|---:|---:|---:|
| be548a35c1564827a1f7057a4eafb4e1 | 250 ms | 0 | 0 |
| 22d3cf67c1aa4475b2755205f43b4f03 | 389 ms | 0 | 0 |
| 33486e14626447b48156d5125fd89427 | 219 ms | 0 | 0 |

编译耗时不包含业务查询；当前数据源属性查询约数十秒。

证据保存在 `.codex-runtime/ranking-20260930/`：`browser-final.sql`、`business-reconciliation.json`、`browser-property-conflict.png`、`browser-saved-ranking.png`、`backend-tests.log`、`baseline-tests.log`，不纳入 Git。
