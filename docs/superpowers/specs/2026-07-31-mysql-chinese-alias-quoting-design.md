# MySQL 中文别名引用设计

## 目标

强化 Smart Q&A 生成 SQL 的提示规则：在 MySQL、AnalyticDB、Doris、StarRocks 等使用反引号的方言中，中文输出别名必须使用反引号引用，并在后续合法引用该别名时继续保留反引号。

期望示例：

```sql
SELECT
  `c`.`register_date` AS `注册日期`,
  `c`.`region` AS `地区`
FROM `cohort` `c`
GROUP BY `c`.`register_date`, `c`.`region`
ORDER BY `注册日期`, `地区`
```

如果上游 CTE 或子查询已经把字段输出为中文名，则可以限定引用：

```sql
SELECT `c`.`注册日期`, `c`.`地区`
FROM `cohort` `c`
GROUP BY `c`.`注册日期`, `c`.`地区`
ORDER BY `注册日期`, `地区`
```

## 规则边界

- 反引号用于标识符；不得使用单引号包裹中文别名，因为单引号表示字符串值。
- `ORDER BY` 可以引用当前查询最终输出的中文别名，并必须保留反引号。
- `GROUP BY` 不得把当前层刚定义的 `SELECT` 别名伪装成来源表字段。当前层应使用原始字段或完整表达式；只有上游 CTE/子查询已实际输出该中文列时，才可写成 `` `c`.`注册日期` ``。
- SQL 子句顺序保持 `GROUP BY` 在前、`ORDER BY` 在后。
- 规则按数据源方言表达。此次强化 MySQL 系反引号规则，不改变 PostgreSQL 等方言使用双引号的现有行为。

## 实现范围

1. 强化 MySQL SQL 生成模板，增加中文别名及其 `ORDER BY` 引用的明确正反例。
2. 刷新平台通用 SQL 日期与分组 Data Skill，使已部署环境也能获得相同约束，并明确同层别名与上游字段的区别。
3. 增加提示模板和平台 Data Skill 的回归测试，确认生成上下文包含上述规则。

不增加 SQL AST 校验，不自动改写模型生成的 SQL，也不增加静默兼容回退。

## 验证

- 单元测试验证 MySQL SQL 系统提示包含中文别名反引号规则、合法示例和同层 `GROUP BY` 边界。
- 迁移测试验证平台 Data Skill 的刷新内容包含相同约束。
- 运行相关后端测试，确认现有 SQL 生成提示与迁移行为未回归。
