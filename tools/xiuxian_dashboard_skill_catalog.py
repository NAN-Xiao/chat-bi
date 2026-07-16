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


EMPTY_VIEW_ID = "1e4e34743f2d47dfa1c2948742b93a50"
MAX_SQL_BLOCKS_PER_SKILL = 6
MAX_PROMPT_CHARS = 15_000

TOPICS = (
    TopicDefinition(
        "realtime-payment",
        "修仙实时付费趋势",
        "实时与累计付费事件趋势。",
        (
            "eafa54818ed54020a16369a42c99783f",
            "d093ae51d20942ffa69bfcea7a14f740",
        ),
        "ServerPayLog 按业务小时统计真实交易事件次数和累计次数；金额问题转交收入 Skill。",
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
        "新增 cohort D1/D3/D7 留存。",
        (
            "f99d0fb5f3624192953bdbfa31549abd",
            "531bc723e3cb42f0a1fe2c412d7f05b0",
            "57c366462db9418ba14fcde0febeb18d",
            "73f88ab0dce848f39037c345e20fe268",
            "b0f27793e48349c1a6a7fbf40ff03ffd",
            "e797a8af6785452e9fdcee7d80786b6e",
        ),
        "分母固定 UserRegister cohort，Dn 分子为精确第 n 日 UserActive 去重 uid；排除未成熟 cohort。",
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
        "真实收入与付费人均指标。",
        (
            "22d89d4a69224e53994d21fb44b376aa",
            "2192510609759838208",
            "3b585529d8e84bc3ac1ea3bf55746450",
            "a6eb26710f7b4dc6ab69ded704c32fee",
            "9eff78876b1b405385f96d8559a286a8",
        ),
        "收入只汇总 ServerPayLog.personal.money；ARPPU 分母为 ServerPayLog 去重 uid，ARPU 分母为 UserActive 去重 uid。",
    ),
    TopicDefinition(
        "payer-penetration",
        "修仙付费用户、渗透与累计付费",
        "付费用户、渗透率与累计金额。",
        (
            "95d8497afac14f0a90342031fb43bc04",
            "f499305aa9b44a209cbe72cb68985a46",
            "304e66bb74254b9e88d8711ce33d94cc",
            "e4b33de129da47629caa61612cca8100",
            "eba39b8352a34136872404c16fbd17a9",
            "fc272fe6a3a74cda90a0564a98890fab",
        ),
        "日付费用户按 ServerPayLog.uid 去重；累计 paytotal 只用于明确的累计快照指标，不能替代当日收入。",
    ),
    TopicDefinition(
        "orders-products",
        "修仙订单、礼包与支付流程",
        "订单、商品、礼包和支付流程事件。",
        (
            "bcd7dc9ca6c349909fa74c8d4b0502d7",
            "ab85f87857774883833dbca9b5ea41ba",
            "e65001c16c52433e8afac84c6b2c92a0",
        ),
        "真实订单和商品使用 ServerPayLog.orderId/productid；PayBuyRet 仅描述流程事件分布，不命名为真实交易。",
    ),
    TopicDefinition(
        "player-snapshot",
        "修仙当前等级、付费分层与用户快照",
        "当前等级和付费分层。",
        (
            "7f71477b49404ad289485f4f22d34c2f",
            "3a449b3049314a668661ae65f70e38f1",
        ),
        "当前分布读取目标日期 user 快照；等级段人均累计付费使用 paytotal，并明确其累计快照语义。",
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
        "eafa54818ed54020a16369a42c99783f",
        "d093ae51d20942ffa69bfcea7a14f740",
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
        "73f88ab0dce848f39037c345e20fe268",
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


def build_topic_prompt(topic: TopicDefinition) -> str:
    """为单个主题生成统一的 Data Skill 提示词骨架。"""

    view_ids = "、".join(topic.view_ids)
    return f"""# {topic.name}

## 适用范围
{topic.description}
对应推荐看板组件：{view_ids}

## 日期规则引用
日期筛选遵循当前数据源的修仙日期分区 Data Skill；未指定时使用截至昨天的最近 28 个自然日。

## 业务口径
{topic.guidance}

## 禁止事项
不得把事件次数、去重用户数、收入金额或累计快照互相替代；不得跨数据源套用本主题口径。

## 推荐输出
优先输出与原看板一致的维度、指标、排序和可读别名，并明确时间范围与单位。

## 看板 SQL
按上述组件顺序保留经备份确认的 SQL；每个组件最多对应一个 SQL 块。
"""


def validate_catalog() -> None:
    """校验主题目录的数量、唯一性、完整性与单主题容量。"""

    mapped = [view_id for topic in TOPICS for view_id in topic.view_ids]
    if len(TOPICS) != 12 or len(mapped) != 44 or len(set(mapped)) != 44:
        raise ValueError("修仙推荐看板 Skill 目录数量或唯一性错误")
    if set(mapped) != EXPECTED_VIEW_IDS or EMPTY_VIEW_ID in mapped:
        raise ValueError("修仙推荐看板 Skill 目录存在遗漏或错误组件")
    if any(len(topic.view_ids) > MAX_SQL_BLOCKS_PER_SKILL for topic in TOPICS):
        raise ValueError("单个修仙 Data Skill 超过 SQL 块上限")


validate_catalog()
