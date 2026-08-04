"""修仙推荐看板 Data Skill 的唯一主题目录。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicDefinition:
    """一个 Data Skill 主题及其包含的推荐看板组件。"""

    slug: str
    name: str
    description: str
    view_ids: tuple[str, ...]
    guidance: str


MAX_SQL_BLOCKS_PER_SKILL = 6
MAX_PROMPT_CHARS = 17_000

TOPICS = (
    TopicDefinition(
        "realtime-payment",
        "修仙实时付费趋势",
        "实时每小时支付记录数与收入金额。",
        (
            "2193936101973073920",
        ),
        "event_realtime 的 ServerPayLog 按小时统计支付记录数，并汇总 personal.money 为收入金额。",
    ),
    TopicDefinition(
        "new-users-platform",
        "修仙新增用户总量与系统归因",
        "新增总量与系统归因。",
        (
            "1c5288d1fe144ddea2b9e82c5ac72b24",
            "bdc788729cbc4157bfe3046170c1f92a",
            "10d4c025e0bf4d9a9f3bd60194cdabb0",
        ),
        "新增用户使用 UserRegister 去重 uid；系统归因读取注册事件行的 deviceinfo/userinfo，不能用后续活跃覆盖。",
    ),
    TopicDefinition(
        "channel-acquisition",
        "修仙渠道新增与投放获客",
        "渠道新增与单渠道获客。",
        (
            "8683537b4c2641afa1cefb2dec8dfb06",
            "b687a5175da64fc3a3d37ee9a0ec12b2",
            "918d4fd1c4d649d5bae371828928f409",
            "96d0dcd61c3a4a9e8a9922d813fce866",
            "d03e4b19ba1d4c668c9e6c64b5f16fc9",
        ),
        "渠道归因取 UserRegister 注册行的 mediaSource/campaignName；新增用户按 uid 去重，不把活跃人数当新增。",
    ),
    TopicDefinition(
        "active-dau-wau-mau",
        "修仙 DAU、WAU 与 MAU",
        "活跃规模和周期去重。",
        (
            "6b458210dec64fdc8c067b301272f347",
            "e4344fa52c564002931ce13ea3657027",
            "0369399df2eb4a3299d6d34f9663101b",
            "ad88b71e2b08435c8c7a0606c5579f30",
        ),
        "DAU/WAU/MAU 使用 UserActive 去重 uid；WAU/MAU 按完整自然周/月去重，不能相加日活。",
    ),
    TopicDefinition(
        "active-lifecycle",
        "修仙活跃生命周期与维度拆解",
        "活跃生命周期、渠道、系统和周登录天数。",
        (
            "fd9a8fe1127e4f21bf1809a6560ec6e2",
            "816451c6645a4451b7e85bbfb74d7ee7",
            "6c96d753e08742579580d52764d5589b",
            "d4675e033a9c4d4881264a66861b066e",
            "2ae501be08934d758f82802abf016059",
        ),
        "活跃 cohort 使用 UserActive；生命周期、渠道、系统均取同一活跃事件上下文，周登录天数先按用户去重日期。",
    ),
    TopicDefinition(
        "new-user-retention",
        "修仙新增 cohort 留存",
        "渠道新增用户近 15 个自然日 D1/D3/D7 cohort 留存，补齐日期与渠道组合。",
        (
            "f99d0fb5f3624192953bdbfa31549abd",
            "531bc723e3cb42f0a1fe2c412d7f05b0",
            "57c366462db9418ba14fcde0febeb18d",
            "b0f27793e48349c1a6a7fbf40ff03ffd",
            "e797a8af6785452e9fdcee7d80786b6e",
        ),
        "分母固定 UserRegister cohort，渠道依次取 mediaSource、campaignName、未知；Dn 分子为精确第 n 日 UserActive 去重 uid。"
        "D7 只统计相对观察截止日已经过至少 7 个完整自然日的注册 cohort，未成熟 cohort 不得进入分母；"
        "使用看板日期 token 时，注册事件别名必须在自身分区条件中同时写 "
        "`e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}` 以及 "
        "`e.dt <= CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)`；"
        "对应 D7 活跃观察日必须等于注册日加 7 天且不得超过 `{{dashboard_end_yyyymmdd}}`。"
        "用户要求样本数时，输出各渠道纳入计算的成熟 cohort 注册用户数。"
        "按日趋势可补齐 cohort 日期，但未成熟 Dn 单元格返回 NULL；已成熟且无留存用户时才显示 0。",
    ),
    TopicDefinition(
        "active-retention",
        "修仙活跃留存与回流",
        "活跃 cohort 留存。",
        ("464bc0c1f62049a5b2562fd09d699640",),
        "活跃留存先固定观察日 UserActive cohort，再按精确后续日期计算，不与新增留存混用。",
    ),
    TopicDefinition(
        "serverpaylog-revenue",
        "修仙 ServerPayLog 收入与 ARPU/ARPPU",
        "真实收入、按渠道统计累计付费用户数、付费人均指标与新增首日付费 cohort。",
        (
            "22d89d4a69224e53994d21fb44b376aa",
            "2192510609759838208",
            "3b585529d8e84bc3ac1ea3bf55746450",
            "a6eb26710f7b4dc6ab69ded704c32fee",
            "9eff78876b1b405385f96d8559a286a8",
        ),
        "普通收入只汇总 ServerPayLog.personal.money；ARPPU 分母为 ServerPayLog 去重 uid，ARPU 分母为 UserActive 去重 uid。新增首日付费金额是独立的注册 cohort 快照口径：UserRegister 按 dt+uid 去重，连接注册日 user 快照并汇总 pay.pay1；dt/regdate 使用 YYYYMMDD 和 SIGNED，按天展示补齐无数据日期。",
    ),
    TopicDefinition(
        "payer-penetration",
        "修仙付费用户、渗透与累计付费",
        "按渠道统计累计付费用户数、付费渗透率与累计金额。",
        (
            "95d8497afac14f0a90342031fb43bc04",
            "f499305aa9b44a209cbe72cb68985a46",
            "304e66bb74254b9e88d8711ce33d94cc",
            "e4b33de129da47629caa61612cca8100",
            "eba39b8352a34136872404c16fbd17a9",
            "fc272fe6a3a74cda90a0564a98890fab",
        ),
        (
            "日付费用户按 ServerPayLog.uid 去重；近15日活跃用户付费率按天计算，"
            "分母为 UserActive 去重 uid，分子为当天同时存在 UserActive 和 "
            "ServerPayLog 的去重 uid；这是每日比率，不是累计付费率。"
            "所选时间窗口的累计付费金额为 SUM(ServerPayLog.personal.money)；"
            "累计付费用户为 COUNT(DISTINCT ServerPayLog.uid)，即全窗口去重 uid。按日累计用户趋势"
            "先确定每名用户在窗口内的首次付费日，再累计首次付费人数，不能累计每日去重人数。"
        ),
    ),
    TopicDefinition(
        "orders-products",
        "修仙订单、礼包、月卡与支付流程",
        "订单、商品、礼包、月卡留存和支付流程事件。",
        (
            "bcd7dc9ca6c349909fa74c8d4b0502d7",
            "ab85f87857774883833dbca9b5ea41ba",
            "e65001c16c52433e8afac84c6b2c92a0",
        ),
        "真实订单和商品使用 ServerPayLog 的 personal.orderId/personal.productid；月卡购买 cohort 使用 ServerPayLog，留存活跃使用 UserActive；PayBuyRet 仅描述流程事件分布，不命名为真实交易。",
    ),
    TopicDefinition(
        "player-snapshot",
        "修仙当前等级、付费分层与用户快照",
        "当前等级和付费分层。",
        (
            "7f71477b49404ad289485f4f22d34c2f",
            "3a449b3049314a668661ae65f70e38f1",
        ),
        """<!-- data-skill-sql-validation:[
  {
    "match":["活跃用户","DAU","dau"],
    "required_sql_contains":["UserActive"],
    "message":"修仙按等级分析活跃用户时，活跃人群必须来自 UserActive 去重 uid；user 快照只提供目标日期的等级标签，不能直接统计为活跃用户。"
  }
] -->
当前分布读取目标日期 user 快照；等级段人均累计付费使用 paytotal，并明确其累计快照语义。
当问题要求按等级统计活跃用户、DAU 或相关付费指标时，先用目标日期 UserActive 去重 uid 固定活跃人群，再按 uid 关联同日 user 快照取得 lastinfo.level；不得直接把 user 快照行数命名为活跃用户数。""",
    ),
    TopicDefinition(
        "hero-growth",
        "修仙英雄养成",
        "英雄升级、升星和星级分布。",
        (
            "99e31069e8b54504a321b7b8066bf946",
            "7a582c5a24ab463a8378e43ae63eda83",
        ),
        "英雄养成使用已确认的 HeroStarUp/HeroLevelUp 事件和 personal 英雄字段，按 uid 去重用户。",
    ),
)

EXPECTED_VIEW_IDS = frozenset(
    {
        "2193936101973073920",
        "1c5288d1fe144ddea2b9e82c5ac72b24",
        "bdc788729cbc4157bfe3046170c1f92a",
        "10d4c025e0bf4d9a9f3bd60194cdabb0",
        "8683537b4c2641afa1cefb2dec8dfb06",
        "b687a5175da64fc3a3d37ee9a0ec12b2",
        "918d4fd1c4d649d5bae371828928f409",
        "96d0dcd61c3a4a9e8a9922d813fce866",
        "d03e4b19ba1d4c668c9e6c64b5f16fc9",
        "6b458210dec64fdc8c067b301272f347",
        "e4344fa52c564002931ce13ea3657027",
        "0369399df2eb4a3299d6d34f9663101b",
        "ad88b71e2b08435c8c7a0606c5579f30",
        "fd9a8fe1127e4f21bf1809a6560ec6e2",
        "816451c6645a4451b7e85bbfb74d7ee7",
        "6c96d753e08742579580d52764d5589b",
        "d4675e033a9c4d4881264a66861b066e",
        "2ae501be08934d758f82802abf016059",
        "f99d0fb5f3624192953bdbfa31549abd",
        "531bc723e3cb42f0a1fe2c412d7f05b0",
        "57c366462db9418ba14fcde0febeb18d",
        "b0f27793e48349c1a6a7fbf40ff03ffd",
        "e797a8af6785452e9fdcee7d80786b6e",
        "464bc0c1f62049a5b2562fd09d699640",
        "22d89d4a69224e53994d21fb44b376aa",
        "2192510609759838208",
        "3b585529d8e84bc3ac1ea3bf55746450",
        "a6eb26710f7b4dc6ab69ded704c32fee",
        "9eff78876b1b405385f96d8559a286a8",
        "95d8497afac14f0a90342031fb43bc04",
        "f499305aa9b44a209cbe72cb68985a46",
        "304e66bb74254b9e88d8711ce33d94cc",
        "e4b33de129da47629caa61612cca8100",
        "eba39b8352a34136872404c16fbd17a9",
        "fc272fe6a3a74cda90a0564a98890fab",
        "bcd7dc9ca6c349909fa74c8d4b0502d7",
        "ab85f87857774883833dbca9b5ea41ba",
        "e65001c16c52433e8afac84c6b2c92a0",
        "7f71477b49404ad289485f4f22d34c2f",
        "3a449b3049314a668661ae65f70e38f1",
        "99e31069e8b54504a321b7b8066bf946",
        "7a582c5a24ab463a8378e43ae63eda83",
    }
)


def validate_prompt_length(prompt: str) -> None:
    """校验完整提示词长度，供 SQL 注入后再次调用。"""

    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError("修仙推荐看板 Skill 提示词超过字符上限")


def build_topic_prompt(topic: TopicDefinition) -> str:
    """为单个主题生成统一的 Data Skill 提示词骨架。"""

    view_ids = "、".join(topic.view_ids)
    prompt = f"""# {topic.name}

## 适用范围
{topic.description}
对应推荐看板组件：{view_ids}

## 日期规则引用
日期筛选遵循当前数据源的修仙日期分区 Data Skill。用户未指定日期时，生成 SQL 使用截至昨天的最近 28 个自然日；这是生成默认规则，不是现场诊断选窗逻辑，不得查询数据中的最大日期或最大分区来改写边界。

## 业务口径
{topic.guidance}

## 禁止事项
不得把事件次数、去重用户数、收入金额或累计快照互相替代；不得跨数据源套用本主题口径。

## 推荐输出
优先输出与原看板一致的维度、指标、排序和可读别名，并明确时间范围与单位。

## 看板 SQL
按上述组件顺序保留经备份确认的 SQL；每个组件最多对应一个 SQL 块。
"""
    validate_prompt_length(prompt)
    return prompt


def validate_catalog() -> None:
    """校验主题目录的数量、唯一性、完整性与单主题容量。"""

    mapped = [view_id for topic in TOPICS for view_id in topic.view_ids]
    if len(TOPICS) != 12 or len(mapped) != 42 or len(set(mapped)) != 42:
        raise ValueError("修仙推荐看板 Skill 目录数量或唯一性错误")
    if set(mapped) != EXPECTED_VIEW_IDS:
        raise ValueError("修仙推荐看板 Skill 目录存在遗漏或错误组件")
    if any(len(topic.view_ids) > MAX_SQL_BLOCKS_PER_SKILL for topic in TOPICS):
        raise ValueError("单个修仙 Data Skill 超过 SQL 块上限")


validate_catalog()
