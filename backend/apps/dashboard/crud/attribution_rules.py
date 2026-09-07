"""The attribution result contract: target contributions and distinct touch activity."""

ATTRIBUTION_METRIC_COLUMNS = {
    "total_touch_count": "总触发数",
    "effective_touch_count": "有效触发次数",
    "effective_touch_rate": "有效触发率",
    "effective_entity_count": "有效触发用户数",
    "attributed_value": "对目标事件的贡献值",
    "contribution_rate": "对目标事件的贡献度",
}

ATTRIBUTION_RULES = [
    "每条目标事件独立回溯并分配贡献；首次/末次选择该目标窗口内最早/最晚触点，线性按全部触点记录等分，不能按事件类型或用户去重后分配。",
    "targets 必须保留每次目标的 target_id；touches 必须在关联前保留每条触点的 touch_id、entity_id。优先使用元数据事件唯一键；查询内编号必须在关联前创建，同一触点参与多个目标时 touch_id 不变。",
    "目标贡献只支持 count（每次目标 target_value=1）和 sum（每次目标 target_value 为所选数值属性），不能把 UID 去重数、平均值或极值静默解释成次数或金额求和。",
    "目标事件扫描用户选择的时间范围；当天触点扫描从起始自然日 00:00 开始，每个目标只匹配同一天且不晚于目标的触点；自定义触点扫描从目标查询起点向前扩展一个完整窗口。日期编码必须先解析后用于运算。",
    "同一 touch_id 可对多个 target_id 分配贡献；有效触发次数按实际获得归因资格的 touch_id 去重，不按匹配行数或 target_id 计数。首次/末次未获选触点的贡献和有效触发次数为零。",
    "总触发数 total_touch_count 是扩展计算范围内、符合触点自身筛选的 COUNT(DISTINCT touch_id)，不受归因方式影响，也不能只统计成功匹配目标的触点。",
    "有效触发次数 effective_touch_count=有效触点 COUNT(DISTINCT touch_id)；有效触发用户数 effective_entity_count=有效触点 COUNT(DISTINCT entity_id)，必须来自触点侧分析主体。",
    "effective_touch_rate=effective_touch_count*100.0/NULLIF(total_touch_count,0)。各触点类型/分组即使贡献为零也要从触点全集保留；使用触点统计 LEFT JOIN 贡献统计，禁止只从有效触点构建结果。",
    "attributed_value=SUM(target_value*linear_weight)，每个目标的分配权重之和为1；target_count 可另外 COUNT(DISTINCT target_id) 展示，不能替代触发次数。",
    "includeDirect=true：窗口内没有满足主体、时间、筛选及关联属性的触点时，目标的完整指标值归入直接转化；直接转化没有真实触点，三个触发计数为0，有效触发率为NULL，不能用虚构 touch_id 凑数。false：排除这些无触点目标。",
    "contribution_rate=本行贡献值*100.0/NULLIF(参与本次归因的总目标指标值,0)。分母按当前配置的目标分组计算并跨全部归因事件；勾选直接转化时纳入其目标值。",
    "现有 groups 保持目标事件分组语义；若配置明确提供 attributionSide=touch，字段取触点发生时的属性且贡献率分母不得按该触点分组重新归一化。",
    "events[i].relatedProperty.enabled=true 时，只为该归因事件增加 targetProperty=touchProperty 条件，与主体和窗口条件同时生效；任何一侧缺失都不能绕过匹配要求。未配置关联属性时不得猜测业务键。",
    "分别建立 touches_total（总触点统计）、selected_touches（首次/末次/线性实际获选的触点）、effective_touches（按 touch_id 去重）、contributions（目标值分配汇总），再关联为结果；总触点不能被目标关联放大或被获选条件缩小。",
]
