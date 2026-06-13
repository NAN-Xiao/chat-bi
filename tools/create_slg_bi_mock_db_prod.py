from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql


TZ = ZoneInfo("Asia/Shanghai")

EVENTS: dict[str, tuple[str, str, str, dict[str, str]]] = {
    "device_register": ("account", "设备注册", "SDK生成设备或安装实例ID", {"device_id": "设备ID"}),
    "ad_impression": ("acquisition", "广告曝光", "买量广告曝光", {"ad_network": "广告平台", "campaign_id": "广告计划"}),
    "ad_click": ("acquisition", "广告点击", "买量广告点击", {"ad_network": "广告平台", "campaign_id": "广告计划"}),
    "install": ("account", "安装", "客户端首次安装或归因成功", {"campaign_id": "广告计划"}),
    "register": ("account", "注册", "创建角色并进入区服", {"server_id": "区服ID"}),
    "server_select": ("account", "选服", "选择王国/区服", {"server_code": "区服编码"}),
    "app_start": ("session", "启动", "客户端启动", {"network_type": "网络类型"}),
    "login": ("session", "登录", "进入游戏会话", {"lifecycle_day": "生命周期天数"}),
    "logout": ("session", "登出", "会话结束", {"duration_seconds": "会话时长"}),
    "push_open": ("session", "推送打开", "从系统推送唤起客户端", {"push_type": "推送类型"}),
    "offline_reward_claim": ("progression", "离线奖励领取", "领取离线产出或回流奖励", {"offline_hours": "离线小时数"}),
    "tutorial_step": ("tutorial", "新手引导步骤", "新手引导步骤完成", {"step": "步骤序号"}),
    "quest_complete": ("progression", "任务完成", "主线/日常任务完成", {"quest_type": "任务类型"}),
    "level_up": ("progression", "玩家升级", "玩家等级提升", {"from_level": "升级前等级", "to_level": "升级后等级"}),
    "building_upgrade_start": ("progression", "建筑升级开始", "建筑升级开始打点", {"task_id": "任务ID", "building_type": "建筑类型"}),
    "building_upgrade_finish": ("progression", "建筑升级完成", "建筑升级完成打点", {"task_id": "任务ID", "building_type": "建筑类型"}),
    "research_start": ("progression", "科技研究开始", "科技研究开始打点", {"task_id": "任务ID", "research_type": "科技类型"}),
    "research_finish": ("progression", "科技研究完成", "科技研究完成打点", {"task_id": "任务ID", "research_type": "科技类型"}),
    "troop_train_start": ("army", "士兵训练开始", "兵营开始训练士兵", {"task_id": "任务ID", "troop_type": "兵种"}),
    "troop_train_finish": ("army", "士兵训练完成", "训练完成并入库", {"task_id": "任务ID", "troop_count": "士兵数量"}),
    "resource_change": ("economy", "资源变更", "资源产出、消耗或礼包发放", {"resource_type": "资源类型", "change_amount": "变化量"}),
    "item_use": ("economy", "道具使用", "使用资源包、加速等道具", {"item_type": "道具类型"}),
    "speedup_use": ("economy", "加速使用", "建筑/科技/训练加速", {"speedup_seconds": "加速秒数"}),
    "march_start": ("battle", "行军开始", "出征、采集或集结行军开始", {"march_type": "行军类型"}),
    "march_finish": ("battle", "行军结束", "行军完成返回", {"march_type": "行军类型"}),
    "pve_battle_result": ("battle", "PVE战斗结果", "章节PVE战斗结算", {"result": "胜负"}),
    "pvp_battle_result": ("battle", "PVP战斗结果", "玩家间战斗结算", {"result": "胜负"}),
    "world_monster_attack": ("battle", "世界野怪", "世界地图野怪挑战结果", {"monster_level": "野怪等级"}),
    "rally_join": ("alliance", "集结加入", "加入联盟集结", {"rally_type": "集结类型"}),
    "alliance_join": ("alliance", "加入联盟", "玩家加入联盟", {"alliance_id": "联盟ID"}),
    "alliance_help": ("alliance", "联盟帮助", "帮助联盟成员缩短建造/研究时间", {"help_count": "帮助次数"}),
    "alliance_donate": ("alliance", "联盟捐献", "联盟科技捐献", {"donate_type": "捐献类型"}),
    "chat_send": ("social", "聊天发送", "世界/联盟聊天消息", {"chat_channel": "聊天频道"}),
    "mail_read": ("system", "邮件读取", "读取系统邮件、联盟邮件或战报", {"mail_type": "邮件类型"}),
    "shop_view": ("monetization", "商城曝光", "商城或礼包页曝光", {"shop_tab": "商城页签"}),
    "purchase_start": ("monetization", "支付发起", "点击购买并拉起支付", {"order_id": "订单ID", "product_id": "商品ID"}),
    "purchase_success": ("monetization", "支付成功", "订单支付成功", {"order_id": "订单ID", "amount_usd": "美元金额"}),
    "payment_fail": ("monetization", "支付失败", "支付渠道返回失败", {"order_id": "订单ID", "fail_reason": "失败原因"}),
    "purchase_cancel": ("monetization", "支付取消", "玩家取消支付流程", {"order_id": "订单ID"}),
    "refund": ("monetization", "退款", "订单发生退款", {"order_id": "订单ID", "refund_amount_usd": "退款金额"}),
    "client_error": ("quality", "客户端错误", "非崩溃客户端异常", {"error_code": "错误码"}),
    "network_error": ("quality", "网络错误", "请求超时或弱网错误", {"api": "接口名"}),
    "crash": ("quality", "客户端崩溃", "客户端崩溃上报", {"crash_type": "崩溃类型"}),
    "anti_cheat_flag": ("security", "反作弊标记", "可疑行为或风控命中", {"rule_id": "规则ID"}),
}

PRODUCTS = [
    ("first_recharge_099", "首充礼包", "first_pay", Decimal("0.99"), "once", 1, True),
    ("starter_pack_499", "开服成长礼包", "starter", Decimal("4.99"), "once", 1, False),
    ("monthly_card_499", "月卡", "subscription", Decimal("4.99"), "monthly", 3, False),
    ("builder_queue_999", "第二建筑队列", "function", Decimal("9.99"), "once", 5, False),
    ("speedup_pack_999", "8小时加速礼包", "speedup", Decimal("9.99"), "daily", 6, False),
    ("resource_pack_1999", "资源补给礼包", "resource", Decimal("19.99"), "daily", 8, False),
    ("war_pack_4999", "战争动员礼包", "war", Decimal("49.99"), "weekly", 10, False),
    ("legend_pack_9999", "传说统帅礼包", "hero", Decimal("99.99"), "weekly", 12, False),
    ("growth_fund_1999", "成长基金", "growth", Decimal("19.99"), "once", 8, False),
    ("vip_points_999", "VIP点数礼包", "vip", Decimal("9.99"), "daily", 4, False),
]

CHANNELS = [
    ("organic", 0.18),
    ("google_ads", 0.16),
    ("tiktok_ads", 0.14),
    ("facebook_ads", 0.13),
    ("app_store_search", 0.12),
    ("huawei_store", 0.10),
    ("influencer", 0.08),
    ("tap_tap", 0.06),
    ("pre_register", 0.03),
]

COUNTRIES = [
    ("CN", "zh-CN", 0.58),
    ("TW", "zh-TW", 0.09),
    ("HK", "zh-TW", 0.04),
    ("US", "en", 0.08),
    ("JP", "ja", 0.07),
    ("KR", "ko", 0.05),
    ("TH", "th", 0.04),
    ("VN", "vi", 0.03),
    ("DE", "de", 0.02),
]

BUILDINGS = [
    "main_city",
    "barracks",
    "archery_range",
    "stable",
    "farm",
    "lumber_mill",
    "quarry",
    "iron_mine",
    "academy",
    "hospital",
    "embassy",
    "wall",
    "watchtower",
]
RESEARCH_TYPES = [
    "construction_speed",
    "research_speed",
    "infantry_attack",
    "archer_attack",
    "cavalry_attack",
    "troop_health",
    "march_speed",
    "resource_production",
    "hospital_capacity",
]
RESOURCE_TYPES = ["food", "wood", "stone", "iron", "gold"]
TROOP_TYPES = ["infantry", "archer", "cavalry", "siege"]
ANDROID_MODELS = ["Xiaomi 15", "Redmi K70", "Huawei Mate 70", "OPPO Find X8", "vivo X200", "Samsung S25", "OnePlus 13"]
IOS_MODELS = ["iPhone 13", "iPhone 14", "iPhone 15", "iPhone 15 Pro", "iPhone 16", "iPhone 16 Pro"]

TABLE_DESCRIPTIONS = {
    "dim_server": "区服/王国维表。",
    "dim_alliance": "联盟维表。",
    "dim_product": "商品维表。",
    "dim_event_name": "埋点事件字典。",
    "dim_player": "玩家维表，包含注册、设备、归因和当前状态。",
    "fact_sessions": "会话事实表，一行代表一次登录到登出。",
    "fact_events": "生产级统一原始埋点表，一行代表一次客户端或服务端事件。",
    "fact_payments": "支付订单生命周期表，包含成功、失败、取消和退款。",
    "fact_battles": "战斗明细表。",
    "fact_resource_transactions": "资源流水明细表，每行通过event_uid回溯到resource_change事件。",
    "fact_building_upgrades": "建筑升级任务完成明细，包含start/finish事件UID和真实耗时。",
    "fact_research": "科技研究任务完成明细，包含start/finish事件UID和真实耗时。",
    "fact_army_training": "士兵训练任务完成明细，包含start/finish事件UID和真实耗时。",
    "meta_data_dictionary": "数据字典表。",
}

COLUMN_DESCRIPTIONS = {
    "fact_events": {
        "event_uid": "全局事件唯一ID，生产埋点主键，所有明细表通过它回溯原始事件。",
        "client_event_id": "客户端生成的事件ID，用于去重。",
        "trace_id": "一次业务链路的追踪ID。",
        "client_time": "客户端本地事件时间。",
        "server_receive_time": "服务端收到事件时间。",
        "ingest_time": "进入数仓或埋点管道时间。",
        "event_source": "事件来源：client、server、sdk。",
        "event_schema_version": "事件协议版本。",
        "attributes": "事件扩展属性JSON。",
    },
    "fact_resource_transactions": {
        "event_uid": "对应fact_events中的resource_change事件。",
        "business_event_uid": "触发资源变化的业务事件UID，例如任务完成、支付成功或建筑升级。",
    },
    "fact_payments": {
        "payment_status": "订单最终状态：success、failed、cancelled、refunded。",
        "start_event_uid": "purchase_start事件UID。",
        "final_event_uid": "支付成功、失败、取消或退款事件UID。",
        "net_revenue_usd": "净收入，退款订单为0。",
    },
}

GENERIC_COLUMN_DESCRIPTIONS = {
    "server_id": "区服ID。",
    "server_code": "区服编码。",
    "server_name": "区服名称。",
    "open_date": "开服日期。",
    "region": "大区。",
    "timezone": "业务时区。",
    "alliance_id": "联盟ID。",
    "alliance_tag": "联盟标签。",
    "alliance_name": "联盟名称。",
    "language": "语言。",
    "tier": "层级。",
    "create_time": "创建时间。",
    "max_members": "最大成员数。",
    "member_count": "当前成员数。",
    "active_member_7d": "最近7天活跃成员数。",
    "total_power": "总战力。",
    "leader_player_id": "盟主玩家ID。",
    "product_id": "商品ID。",
    "product_name": "商品名称。",
    "product_type": "商品类型。",
    "price_usd": "美元标价。",
    "limit_type": "限购类型。",
    "unlock_level": "解锁等级。",
    "is_first_pay_pack": "是否首充礼包。",
    "event_name": "事件英文名。",
    "event_category": "事件分类。",
    "event_cn_name": "事件中文名。",
    "description": "说明。",
    "required_attrs": "事件关键属性JSON说明。",
    "player_id": "玩家ID。",
    "account_id": "账号ID。",
    "role_id": "角色ID。",
    "device_id": "设备ID。",
    "register_time": "注册时间。",
    "install_date": "安装日期。",
    "country": "国家或地区。",
    "platform": "平台。",
    "channel": "获客渠道。",
    "campaign": "广告计划或活动。",
    "device_tier": "设备档位。",
    "device_model": "设备型号。",
    "os_version": "系统版本。",
    "register_server_id": "注册区服ID。",
    "activity_segment": "活跃分层。",
    "payer_segment": "付费分层。",
    "current_level": "当前玩家等级。",
    "current_vip_level": "当前VIP等级。",
    "current_power": "当前战力。",
    "current_city_level": "当前主城等级。",
    "current_alliance_id": "当前联盟ID。",
    "first_pay_time": "首次付费时间。",
    "total_pay_amount": "累计净付费金额。",
    "last_active_date": "最后活跃日期。",
    "session_id": "会话ID。",
    "session_uid": "会话唯一ID。",
    "session_start": "会话开始时间。",
    "session_end": "会话结束时间。",
    "duration_seconds": "持续时长，秒。",
    "lifecycle_day": "生命周期天数，注册当天为0。",
    "player_level_start": "会话开始玩家等级。",
    "player_level_end": "会话结束玩家等级。",
    "power_start": "会话开始战力。",
    "power_end": "会话结束战力。",
    "client_version": "客户端版本。",
    "app_build": "客户端构建号。",
    "sdk_version": "埋点SDK版本。",
    "network_type": "网络类型。",
    "ip_country": "IP识别国家或地区。",
    "event_id": "事件自增ID。",
    "event_uid": "事件唯一ID。",
    "client_event_id": "客户端事件ID。",
    "trace_id": "链路追踪ID。",
    "event_time": "事件发生时间。",
    "client_time": "客户端本地时间。",
    "server_receive_time": "服务端接收时间。",
    "ingest_time": "进入数据管道时间。",
    "event_date": "事件日期。",
    "player_level": "事件发生时玩家等级。",
    "vip_level": "事件发生时VIP等级。",
    "power": "事件发生时战力。",
    "event_schema_version": "事件协议版本。",
    "event_source": "事件来源。",
    "sequence_in_session": "会话内事件序号。",
    "attributes": "扩展属性JSON。",
    "order_id": "订单ID。",
    "start_event_uid": "开始事件UID。",
    "final_event_uid": "最终状态事件UID。",
    "amount_usd": "订单标价金额。",
    "gross_revenue_usd": "流水收入金额。",
    "refund_amount_usd": "退款金额。",
    "net_revenue_usd": "净收入金额。",
    "local_currency": "本地币种。",
    "payment_channel": "支付渠道。",
    "payment_status": "支付状态。",
    "fail_reason": "失败原因。",
    "refund_reason": "退款原因。",
    "is_first_pay": "是否首笔支付。",
    "pay_sequence": "玩家第几笔支付。",
    "vip_level_after": "支付后VIP等级。",
    "revenue_tier": "收入档位。",
    "battle_id": "战斗ID。",
    "battle_uid": "战斗唯一ID。",
    "march_start_event_uid": "行军开始事件UID。",
    "march_finish_event_uid": "行军结束事件UID。",
    "battle_type": "战斗类型。",
    "target_type": "目标类型。",
    "target_player_id": "目标玩家ID。",
    "result": "战斗结果。",
    "troops_sent": "派出士兵数。",
    "troops_lost": "损失士兵数。",
    "wounded": "伤兵数。",
    "power_delta": "战力变化。",
    "resource_looted": "掠夺资源量。",
    "stamina_spent": "体力消耗。",
    "map_x": "地图X坐标。",
    "map_y": "地图Y坐标。",
    "trans_id": "资源流水ID。",
    "business_event_uid": "触发资源流水的业务事件UID。",
    "resource_type": "资源类型。",
    "change_amount": "资源变化量。",
    "balance_after": "变化后余额。",
    "source_sink": "资源流向：gain或sink。",
    "reason": "资源变化原因。",
    "is_paid_related": "是否付费相关。",
    "upgrade_id": "建筑升级明细ID。",
    "research_id": "科技研究明细ID。",
    "training_id": "训练明细ID。",
    "task_id": "任务ID。",
    "finish_event_uid": "完成事件UID。",
    "start_time": "任务开始时间。",
    "finish_time": "任务完成时间。",
    "claim_time": "玩家领取或确认完成时间。",
    "start_session_id": "开始任务的会话ID。",
    "finish_session_id": "完成任务的会话ID。",
    "building_type": "建筑类型。",
    "research_type": "科技类型。",
    "troop_type": "兵种。",
    "troop_tier": "士兵阶级。",
    "troop_count": "士兵数量。",
    "from_level": "升级前等级。",
    "to_level": "升级后等级。",
    "speedup_seconds": "加速秒数。",
    "finish_reason": "完成原因。",
    "power_gain": "战力增益。",
    "cost_json": "资源消耗JSON。",
    "table_name": "表名。",
    "column_name": "字段名。",
    "object_type": "对象类型。",
    "example_sql": "示例SQL。",
}


@dataclass
class Player:
    player_id: int
    account_id: str
    role_id: str
    device_id: str
    register_time: datetime
    install_date: date
    country: str
    language: str
    platform: str
    channel: str
    campaign: str
    device_tier: str
    device_model: str
    os_version: str
    server_id: int
    activity_segment: str
    payer_segment: str
    propensity: float
    alliance_propensity: float
    tutorial_target: int
    level: int = 1
    vip_level: int = 0
    power: int = 1200
    city_level: int = 1
    alliance_id: int | None = None
    first_pay_time: datetime | None = None
    total_pay_amount: Decimal = Decimal("0.00")
    pay_count: int = 0
    last_active_date: date | None = None
    tutorial_step: int = 0
    active_days: int = 0
    pending_tasks: list[dict] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a production-grade SLG tracking mock database.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--admin-db", default="slg_config")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="111111")
    parser.add_argument("--db-name", default="slg_bi_mock")
    parser.add_argument("--players", type=int, default=8000)
    parser.add_argument("--start-date", default="2026-04-14")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260613)
    parser.add_argument("--recreate", action="store_true")
    return parser.parse_args()


def weighted_choice(items: list[tuple[object, float]]):
    values = [item[0] for item in items]
    weights = [item[1] for item in items]
    return random.choices(values, weights=weights, k=1)[0]


def weighted_pair(items: list[tuple[str, str, float]]) -> tuple[str, str]:
    values = [(item[0], item[1]) for item in items]
    weights = [item[2] for item in items]
    return random.choices(values, weights=weights, k=1)[0]


def day_dt(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=TZ)


def date_range(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


def choose_platform() -> str:
    return str(weighted_choice([("android", 0.62), ("ios", 0.36), ("pc_emulator", 0.02)]))


def choose_device(platform: str) -> tuple[str, str, str]:
    if platform == "ios":
        tier = str(weighted_choice([("mid", 0.36), ("high", 0.56), ("ultra", 0.08)]))
        return tier, random.choice(IOS_MODELS), f"iOS {random.choice(['17.5', '18.0', '18.1', '18.2'])}"
    if platform == "pc_emulator":
        return "high", str(weighted_choice([("LDPlayer", 0.45), ("BlueStacks", 0.35), ("MuMu", 0.20)])), "Android 12"
    tier = str(weighted_choice([("low", 0.20), ("mid", 0.54), ("high", 0.23), ("ultra", 0.03)]))
    return tier, random.choice(ANDROID_MODELS), f"Android {random.choice(['12', '13', '14', '15'])}"


def choose_campaign(channel: str, install_index: int) -> str:
    if channel == "organic":
        return "organic"
    season = "launch" if install_index < 14 else "midgame" if install_index < 40 else "kingdom_war"
    return f"{channel}_{season}_{random.randint(1, 8):02d}"


def log_interp_retention(lifecycle_day: int) -> float:
    curve = {
        0: 1.0,
        1: 0.42,
        2: 0.32,
        3: 0.26,
        4: 0.22,
        5: 0.19,
        6: 0.17,
        7: 0.145,
        10: 0.115,
        14: 0.090,
        21: 0.070,
        30: 0.050,
        45: 0.038,
        60: 0.032,
    }
    if lifecycle_day in curve:
        return curve[lifecycle_day]
    keys = sorted(curve)
    left = max(k for k in keys if k < lifecycle_day)
    right = min(k for k in keys if k > lifecycle_day)
    lval = math.log(curve[left])
    rval = math.log(curve[right])
    return math.exp(lval + (rval - lval) * ((lifecycle_day - left) / (right - left)))


def active_probability(player: Player, lifecycle_day: int, current_day: date) -> float:
    segment_factor = {"casual": 0.66, "regular": 1.00, "engaged": 1.35, "social": 1.50, "hardcore": 1.85}[player.activity_segment]
    payer_factor = {"non_spender": 1.0, "minnow": 1.25, "dolphin": 1.65, "whale": 2.20}[player.payer_segment]
    weekend = 1.10 if current_day.weekday() >= 5 else 1.0
    p = log_interp_retention(lifecycle_day) * segment_factor * payer_factor * player.propensity * weekend
    if lifecycle_day == 0:
        return 1.0
    if player.last_active_date and (current_day - player.last_active_date).days >= 10:
        p *= 0.55
    return min(0.97, max(0.004, p))


def session_count(player: Player, lifecycle_day: int) -> int:
    dist = {
        "casual": [(1, 0.76), (2, 0.20), (3, 0.04)],
        "regular": [(1, 0.40), (2, 0.36), (3, 0.17), (4, 0.07)],
        "engaged": [(1, 0.17), (2, 0.32), (3, 0.27), (4, 0.16), (5, 0.08)],
        "social": [(1, 0.12), (2, 0.28), (3, 0.27), (4, 0.19), (5, 0.10), (6, 0.04)],
        "hardcore": [(2, 0.18), (3, 0.27), (4, 0.24), (5, 0.18), (6, 0.09), (7, 0.04)],
    }[player.activity_segment]
    n = int(weighted_choice(dist))
    if player.payer_segment in {"dolphin", "whale"} and random.random() < 0.35:
        n += 1
    if lifecycle_day == 0:
        n = max(1, min(n, 3))
    return n


def session_start_times(current_day: date, count: int) -> list[datetime]:
    windows = [((7, 10), 0.15), ((11, 14), 0.18), ((17, 19), 0.16), ((19, 23), 0.42), ((23, 24), 0.06), ((0, 2), 0.03)]
    starts = []
    for _ in range(count):
        start_h, end_h = weighted_choice(windows)
        starts.append(day_dt(current_day, random.randint(start_h, end_h - 1), random.randint(0, 59), random.randint(0, 45)))
    return sorted(starts)


def session_duration_seconds(player: Player) -> int:
    center = {"casual": 10, "regular": 18, "engaged": 30, "social": 34, "hardcore": 48}[player.activity_segment]
    if player.payer_segment == "whale":
        center *= 1.35
    elif player.payer_segment == "dolphin":
        center *= 1.15
    return int(min(max(3, random.lognormvariate(math.log(center), 0.48)), 150) * 60)


def app_version_for_day(day_index: int) -> tuple[str, int, str, str]:
    if day_index < 20:
        return "1.0.3", 100030, "slg-sdk-3.8.1", "slg_event_v3"
    if day_index < 42:
        return "1.1.0", 101000, "slg-sdk-3.9.0", "slg_event_v3"
    return "1.2.0", 102000, "slg-sdk-4.0.2", "slg_event_v4"


def vip_level(total_paid: Decimal) -> int:
    thresholds = [0, 1, 5, 20, 50, 100, 250, 500, 1000, 2000, 5000]
    amount = float(total_paid)
    level = 0
    for index, threshold in enumerate(thresholds):
        if amount >= threshold:
            level = index
    return level


def should_attempt_pay(player: Player, lifecycle_day: int) -> bool:
    if player.payer_segment == "non_spender":
        return random.random() < (0.0012 if lifecycle_day <= 7 else 0.00035)
    if player.payer_segment == "minnow":
        if player.pay_count == 0:
            return random.random() < (0.18 if lifecycle_day <= 1 else 0.030)
        return random.random() < 0.013
    if player.payer_segment == "dolphin":
        if player.pay_count == 0:
            return random.random() < (0.36 if lifecycle_day <= 2 else 0.070)
        return random.random() < (0.082 if lifecycle_day <= 21 else 0.052)
    if player.pay_count == 0:
        return random.random() < (0.65 if lifecycle_day <= 2 else 0.20)
    return random.random() < (0.32 if lifecycle_day <= 30 else 0.22)


def choose_product(player: Player) -> tuple[str, str, Decimal]:
    by_id = {item[0]: item for item in PRODUCTS}
    if player.pay_count == 0 and random.random() < 0.62:
        pid = str(weighted_choice([("first_recharge_099", 0.52), ("starter_pack_499", 0.48)]))
    elif player.payer_segment == "minnow":
        pid = str(weighted_choice([("starter_pack_499", 0.28), ("monthly_card_499", 0.24), ("speedup_pack_999", 0.18), ("vip_points_999", 0.16), ("first_recharge_099", 0.14)]))
    elif player.payer_segment == "dolphin":
        pid = str(weighted_choice([("monthly_card_499", 0.13), ("builder_queue_999", 0.12), ("speedup_pack_999", 0.23), ("resource_pack_1999", 0.22), ("growth_fund_1999", 0.14), ("war_pack_4999", 0.16)]))
    else:
        pid = str(weighted_choice([("speedup_pack_999", 0.10), ("resource_pack_1999", 0.18), ("war_pack_4999", 0.31), ("legend_pack_9999", 0.30), ("growth_fund_1999", 0.06), ("vip_points_999", 0.05)]))
    p = by_id[pid]
    return p[0], p[1], p[3]


def ensure_database(args: argparse.Namespace) -> None:
    conn = psycopg.connect(host=args.host, port=args.port, dbname=args.admin_db, user=args.user, password=args.password, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("select 1 from pg_database where datname = %s", (args.db_name,))
        exists = cur.fetchone() is not None
        if exists and not args.recreate:
            raise SystemExit(f"Database {args.db_name!r} already exists. Rerun with --recreate to replace it.")
        if exists:
            cur.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname = %s and pid <> pg_backend_pid()", (args.db_name,))
            cur.execute(sql.SQL("drop database {}").format(sql.Identifier(args.db_name)))
        cur.execute(sql.SQL("create database {} owner {} encoding 'UTF8'").format(sql.Identifier(args.db_name), sql.Identifier(args.user)))
    conn.close()


def create_schema(conn: psycopg.Connection) -> None:
    ddl = """
    create table dim_server (
        server_id integer primary key,
        server_code text not null unique,
        server_name text not null,
        open_date date not null,
        region text not null,
        timezone text not null
    );
    create table dim_alliance (
        alliance_id integer primary key,
        server_id integer not null references dim_server(server_id),
        alliance_tag text not null,
        alliance_name text not null,
        language text not null,
        tier text not null,
        create_time timestamptz not null,
        max_members integer not null,
        member_count integer not null,
        active_member_7d integer not null,
        total_power bigint not null,
        leader_player_id integer
    );
    create table dim_product (
        product_id text primary key,
        product_name text not null,
        product_type text not null,
        price_usd numeric(10,2) not null,
        limit_type text not null,
        unlock_level integer not null,
        is_first_pay_pack boolean not null
    );
    create table dim_event_name (
        event_name text primary key,
        event_category text not null,
        event_cn_name text not null,
        description text not null,
        required_attrs jsonb not null
    );
    create table dim_player (
        player_id integer primary key,
        account_id text not null unique,
        role_id text not null unique,
        device_id text not null,
        register_time timestamptz not null,
        install_date date not null,
        country text not null,
        language text not null,
        platform text not null,
        channel text not null,
        campaign text not null,
        device_tier text not null,
        device_model text not null,
        os_version text not null,
        register_server_id integer not null references dim_server(server_id),
        activity_segment text not null,
        payer_segment text not null,
        current_level integer not null,
        current_vip_level integer not null,
        current_power bigint not null,
        current_city_level integer not null,
        current_alliance_id integer references dim_alliance(alliance_id),
        first_pay_time timestamptz,
        total_pay_amount numeric(12,2) not null,
        last_active_date date
    );
    create table fact_sessions (
        session_id bigint primary key,
        session_uid text not null unique,
        player_id integer not null references dim_player(player_id),
        account_id text not null,
        role_id text not null,
        device_id text not null,
        server_id integer not null references dim_server(server_id),
        session_start timestamptz not null,
        session_end timestamptz not null,
        duration_seconds integer not null,
        lifecycle_day integer not null,
        player_level_start integer not null,
        player_level_end integer not null,
        power_start bigint not null,
        power_end bigint not null,
        platform text not null,
        channel text not null,
        campaign text not null,
        client_version text not null,
        app_build integer not null,
        sdk_version text not null,
        device_tier text not null,
        device_model text not null,
        os_version text not null,
        network_type text not null,
        country text not null,
        ip_country text not null
    );
    create table fact_events (
        event_id bigserial primary key,
        event_uid text not null unique,
        client_event_id text not null,
        trace_id text not null,
        event_time timestamptz not null,
        client_time timestamptz not null,
        server_receive_time timestamptz not null,
        ingest_time timestamptz not null,
        event_date date not null,
        player_id integer not null references dim_player(player_id),
        account_id text not null,
        role_id text not null,
        device_id text not null,
        server_id integer not null references dim_server(server_id),
        session_id bigint not null references fact_sessions(session_id),
        event_name text not null references dim_event_name(event_name),
        event_category text not null,
        lifecycle_day integer not null,
        player_level integer not null,
        vip_level integer not null,
        power bigint not null,
        alliance_id integer,
        client_version text not null,
        app_build integer not null,
        sdk_version text not null,
        event_schema_version text not null,
        platform text not null,
        channel text not null,
        campaign text not null,
        country text not null,
        ip_country text not null,
        language text not null,
        device_model text not null,
        os_version text not null,
        device_tier text not null,
        network_type text not null,
        event_source text not null,
        sequence_in_session integer not null,
        attributes jsonb not null
    );
    create table fact_payments (
        order_id text primary key,
        start_event_uid text not null references fact_events(event_uid),
        final_event_uid text not null references fact_events(event_uid),
        event_time timestamptz not null,
        event_date date not null,
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        session_id bigint not null references fact_sessions(session_id),
        product_id text not null references dim_product(product_id),
        product_name text not null,
        amount_usd numeric(10,2) not null,
        gross_revenue_usd numeric(10,2) not null,
        refund_amount_usd numeric(10,2) not null,
        net_revenue_usd numeric(10,2) not null,
        local_currency text not null,
        payment_channel text not null,
        payment_status text not null,
        fail_reason text,
        refund_reason text,
        is_first_pay boolean not null,
        pay_sequence integer not null,
        lifecycle_day integer not null,
        vip_level_after integer not null,
        player_level integer not null,
        revenue_tier text not null,
        attributes jsonb not null
    );
    create table fact_battles (
        battle_id bigint primary key,
        battle_uid text not null unique,
        event_uid text not null references fact_events(event_uid),
        march_start_event_uid text not null references fact_events(event_uid),
        march_finish_event_uid text not null references fact_events(event_uid),
        event_time timestamptz not null,
        event_date date not null,
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        session_id bigint not null references fact_sessions(session_id),
        battle_type text not null,
        target_type text not null,
        target_player_id integer,
        result text not null,
        troops_sent integer not null,
        troops_lost integer not null,
        wounded integer not null,
        power_delta integer not null,
        resource_looted integer not null,
        stamina_spent integer not null,
        map_x integer not null,
        map_y integer not null,
        attributes jsonb not null
    );
    create table fact_resource_transactions (
        trans_id bigint primary key,
        event_uid text not null references fact_events(event_uid),
        business_event_uid text,
        event_time timestamptz not null,
        event_date date not null,
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        session_id bigint not null references fact_sessions(session_id),
        resource_type text not null,
        change_amount bigint not null,
        balance_after bigint not null,
        source_sink text not null,
        reason text not null,
        is_paid_related boolean not null,
        attributes jsonb not null
    );
    create table fact_building_upgrades (
        upgrade_id bigint primary key,
        task_id text not null unique,
        start_event_uid text not null references fact_events(event_uid),
        finish_event_uid text not null references fact_events(event_uid),
        start_time timestamptz not null,
        finish_time timestamptz not null,
        claim_time timestamptz not null,
        start_session_id bigint not null references fact_sessions(session_id),
        finish_session_id bigint not null references fact_sessions(session_id),
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        building_type text not null,
        from_level integer not null,
        to_level integer not null,
        duration_seconds integer not null,
        speedup_seconds integer not null,
        finish_reason text not null,
        power_gain integer not null,
        cost_json jsonb not null
    );
    create table fact_research (
        research_id bigint primary key,
        task_id text not null unique,
        start_event_uid text not null references fact_events(event_uid),
        finish_event_uid text not null references fact_events(event_uid),
        start_time timestamptz not null,
        finish_time timestamptz not null,
        claim_time timestamptz not null,
        start_session_id bigint not null references fact_sessions(session_id),
        finish_session_id bigint not null references fact_sessions(session_id),
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        research_type text not null,
        from_level integer not null,
        to_level integer not null,
        duration_seconds integer not null,
        speedup_seconds integer not null,
        finish_reason text not null,
        power_gain integer not null,
        cost_json jsonb not null
    );
    create table fact_army_training (
        training_id bigint primary key,
        task_id text not null unique,
        start_event_uid text not null references fact_events(event_uid),
        finish_event_uid text not null references fact_events(event_uid),
        start_time timestamptz not null,
        finish_time timestamptz not null,
        claim_time timestamptz not null,
        start_session_id bigint not null references fact_sessions(session_id),
        finish_session_id bigint not null references fact_sessions(session_id),
        player_id integer not null references dim_player(player_id),
        server_id integer not null references dim_server(server_id),
        troop_type text not null,
        troop_tier integer not null,
        troop_count integer not null,
        duration_seconds integer not null,
        speedup_seconds integer not null,
        finish_reason text not null,
        power_gain integer not null,
        cost_json jsonb not null
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()
    apply_data_dictionary(conn)


def copy_rows(conn: psycopg.Connection, table: str, columns: list[str], rows: list[tuple]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
    conn.commit()


def apply_data_dictionary(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists meta_data_dictionary (
                table_name text not null,
                column_name text not null default '',
                object_type text not null check (object_type in ('table', 'column')),
                description text not null,
                example_sql text not null default '',
                primary key (table_name, object_type, column_name)
            )
            """
        )
        cur.execute(
            """
            select table_name, column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = any(%s)
            order by table_name, ordinal_position
            """,
            (list(TABLE_DESCRIPTIONS.keys()),),
        )
        columns = cur.fetchall()

    rows: list[tuple[str, str, str, str, str]] = []
    for table_name, description in TABLE_DESCRIPTIONS.items():
        rows.append((table_name, "", "table", description, f"select * from {table_name} limit 20;"))
    for table_name, column_name in columns:
        description = (
            COLUMN_DESCRIPTIONS.get(table_name, {}).get(column_name)
            or GENERIC_COLUMN_DESCRIPTIONS.get(column_name)
            or f"{table_name}.{column_name}字段。"
        )
        rows.append((table_name, column_name, "column", description, ""))

    with conn.cursor() as cur:
        cur.execute("truncate table meta_data_dictionary")
        with cur.copy("COPY meta_data_dictionary (table_name, column_name, object_type, description, example_sql) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        for table_name, description in TABLE_DESCRIPTIONS.items():
            cur.execute(sql.SQL("comment on table {} is {}").format(sql.Identifier(table_name), sql.Literal(description)))
            for row_table, column_name, _, column_description, _ in rows:
                if row_table != table_name or not column_name:
                    continue
                cur.execute(sql.SQL("comment on column {}.{} is {}").format(sql.Identifier(table_name), sql.Identifier(column_name), sql.Literal(column_description)))
    conn.commit()


def generate(args: argparse.Namespace) -> dict[str, int]:
    random.seed(args.seed)
    start = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    days = date_range(start, args.days)
    end = days[-1]

    servers = []
    for idx in range(6):
        open_day = start + timedelta(days=idx * 10)
        servers.append((101 + idx, f"K{101 + idx}", f"王国{101 + idx}", open_day, "APAC" if idx < 4 else "GLOBAL", "Asia/Shanghai"))
    server_dicts = [{"server_id": row[0], "open_date": row[3], "server_code": row[1]} for row in servers]

    alliances: list[dict] = []
    alliances_by_server: dict[int, list[dict]] = defaultdict(list)
    names = ["龙庭", "北境", "星火", "破晓", "赤焰", "银月", "风暴", "铁壁", "远征", "苍穹"]
    alliance_id = 10001
    for s in server_dicts:
        for n in range(32):
            tier = "top" if n < 3 else "mid" if n < 14 else "casual"
            row = {
                "alliance_id": alliance_id,
                "server_id": s["server_id"],
                "alliance_tag": f"K{s['server_id']}{n + 1:02d}",
                "alliance_name": f"K{s['server_id']}-{names[n % len(names)]}{n + 1:02d}",
                "language": str(weighted_choice([("zh-CN", 0.64), ("zh-TW", 0.10), ("en", 0.12), ("ja", 0.06), ("ko", 0.05), ("th", 0.03)])),
                "tier": tier,
                "create_time": day_dt(s["open_date"], random.randint(9, 22), random.randint(0, 59)),
                "max_members": 100 if tier == "top" else 80 if tier == "mid" else 55,
                "member_count": 0,
                "active_member_7d": 0,
                "total_power": 0,
                "leader_player_id": None,
            }
            alliances.append(row)
            alliances_by_server[s["server_id"]].append(row)
            alliance_id += 1

    install_weights = []
    for i, current_day in enumerate(days):
        base = 250 * math.exp(-i / 34) + 65
        if current_day.weekday() >= 5:
            base *= 1.22
        for spike_start, spike_len, uplift in [(0, 4, 1.8), (14, 5, 1.55), (35, 4, 1.45)]:
            if spike_start <= i < spike_start + spike_len:
                base *= uplift
        install_weights.append(base)
    install_indices = sorted(random.choices(range(args.days), weights=install_weights, k=args.players))

    def choose_server(install_day: date) -> int:
        candidates = [s for s in server_dicts if s["open_date"] <= install_day]
        return int(weighted_choice([(s["server_id"], math.exp(-(install_day - s["open_date"]).days / 8.0) + 0.08) for s in candidates]))

    players: list[Player] = []
    players_by_server: dict[int, list[int]] = defaultdict(list)
    for idx, install_index in enumerate(install_indices, start=1):
        install_day = days[install_index]
        hour = int(weighted_choice([(9, 0.10), (10, 0.08), (12, 0.14), (14, 0.10), (18, 0.16), (20, 0.24), (22, 0.13), (1, 0.05)]))
        register_time = day_dt(install_day, hour, random.randint(0, 59), random.randint(0, 59))
        channel = str(weighted_choice(CHANNELS))
        country, language = weighted_pair(COUNTRIES)
        platform = choose_platform()
        device_tier, device_model, os_version = choose_device(platform)
        payer_segment = str(weighted_choice([("non_spender", 0.915), ("minnow", 0.055), ("dolphin", 0.025), ("whale", 0.005)]))
        activity_segment = str(weighted_choice([("casual", 0.50), ("regular", 0.29), ("engaged", 0.14), ("social", 0.05), ("hardcore", 0.02)]))
        if payer_segment in {"dolphin", "whale"} and activity_segment == "casual":
            activity_segment = str(weighted_choice([("regular", 0.45), ("engaged", 0.35), ("social", 0.14), ("hardcore", 0.06)]))
        server_id = choose_server(install_day)
        tutorial_target = int(weighted_choice([(1, 0.004), (2, 0.006), (3, 0.010), (4, 0.020), (5, 0.030), (6, 0.050), (7, 0.065), (8, 0.075), (9, 0.080), (10, 0.090), (11, 0.110), (12, 0.460)]))
        player = Player(
            player_id=idx,
            account_id=f"acc_{idx:08d}",
            role_id=f"role_{server_id}_{idx:08d}",
            device_id=f"dev_{random.getrandbits(64):016x}",
            register_time=register_time,
            install_date=install_day,
            country=country,
            language=language,
            platform=platform,
            channel=channel,
            campaign=choose_campaign(channel, install_index),
            device_tier=device_tier,
            device_model=device_model,
            os_version=os_version,
            server_id=server_id,
            activity_segment=activity_segment,
            payer_segment=payer_segment,
            propensity=random.lognormvariate(0, 0.22),
            alliance_propensity={"casual": 0.45, "regular": 0.62, "engaged": 0.76, "social": 0.90, "hardcore": 0.95}[activity_segment],
            tutorial_target=tutorial_target,
            power=random.randint(900, 1500),
        )
        players.append(player)
        players_by_server[server_id].append(player.player_id)

    event_rows: list[tuple] = []
    session_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    battle_rows: list[tuple] = []
    resource_rows: list[tuple] = []
    building_rows: list[tuple] = []
    research_rows: list[tuple] = []
    training_rows: list[tuple] = []
    resource_balances: dict[int, dict[str, int]] = defaultdict(lambda: {"food": 15000, "wood": 15000, "stone": 8000, "iron": 5000, "gold": 350})
    building_levels: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(lambda: 1))
    research_levels: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    product_by_id = {p[0]: p for p in PRODUCTS}

    session_id = 1
    event_seq = 1
    order_seq = 1
    trans_id = 1
    battle_id = 1
    upgrade_id = 1
    research_id = 1
    training_id = 1
    task_seq = 1

    def next_event_uid() -> str:
        nonlocal event_seq
        value = f"evt_{event_seq:012d}"
        event_seq += 1
        return value

    def next_task_id(prefix: str, player_id: int) -> str:
        nonlocal task_seq
        value = f"{prefix}_{player_id}_{task_seq:012d}"
        task_seq += 1
        return value

    def choose_alliance(server_id: int) -> int:
        weights = []
        for alliance in alliances_by_server[server_id]:
            tier_weight = {"top": 6.0, "mid": 2.5, "casual": 1.0}[alliance["tier"]]
            saturation = max(0.12, 1.0 - alliance["member_count"] / alliance["max_members"])
            weights.append((alliance["alliance_id"], tier_weight * saturation))
        return int(weighted_choice(weights))

    def add_event(
        player: Player,
        event_time: datetime,
        sid: int,
        name: str,
        lifecycle_day: int,
        sequence: int,
        attrs: dict,
        client_version: str,
        app_build: int,
        sdk_version: str,
        schema_version: str,
        network_type: str,
        event_source: str = "client",
        trace_id: str | None = None,
    ) -> str:
        event_uid = next_event_uid()
        client_jitter = random.randint(-2, 2)
        receive_lag_ms = random.randint(80, 6200)
        ingest_lag_ms = receive_lag_ms + random.randint(50, 1800)
        event_rows.append(
            (
                event_uid,
                f"cli_{player.device_id}_{event_uid}",
                trace_id or f"trace_{sid}_{sequence:03d}",
                event_time,
                event_time + timedelta(seconds=client_jitter),
                event_time + timedelta(milliseconds=receive_lag_ms),
                event_time + timedelta(milliseconds=ingest_lag_ms),
                event_time.date(),
                player.player_id,
                player.account_id,
                player.role_id,
                player.device_id,
                player.server_id,
                sid,
                name,
                EVENTS[name][0],
                lifecycle_day,
                player.level,
                player.vip_level,
                player.power,
                player.alliance_id,
                client_version,
                app_build,
                sdk_version,
                schema_version,
                player.platform,
                player.channel,
                player.campaign,
                player.country,
                player.country if random.random() < 0.97 else str(weighted_choice([(c[0], c[2]) for c in COUNTRIES])),
                player.language,
                player.device_model,
                player.os_version,
                player.device_tier,
                network_type,
                event_source,
                sequence,
                json.dumps(attrs, ensure_ascii=False),
            )
        )
        return event_uid

    def add_resource(
        player: Player,
        event_time: datetime,
        sid: int,
        lifecycle_day: int,
        sequence: int,
        resource_type: str,
        amount: int,
        reason: str,
        paid: bool,
        client_version: str,
        app_build: int,
        sdk_version: str,
        schema_version: str,
        network_type: str,
        business_event_uid: str | None,
        attrs: dict | None = None,
    ) -> tuple[str, int]:
        nonlocal trans_id
        balance = max(0, resource_balances[player.player_id][resource_type] + amount)
        resource_balances[player.player_id][resource_type] = balance
        payload = {
            "resource_type": resource_type,
            "change_amount": amount,
            "balance_after": balance,
            "reason": reason,
            "is_paid_related": paid,
            **(attrs or {}),
        }
        event_uid = add_event(player, event_time, sid, "resource_change", lifecycle_day, sequence, payload, client_version, app_build, sdk_version, schema_version, network_type, "server")
        resource_rows.append(
            (
                trans_id,
                event_uid,
                business_event_uid,
                event_time,
                event_time.date(),
                player.player_id,
                player.server_id,
                sid,
                resource_type,
                amount,
                balance,
                "gain" if amount >= 0 else "sink",
                reason,
                paid,
                json.dumps(attrs or {}, ensure_ascii=False),
            )
        )
        trans_id += 1
        return event_uid, sequence + 1

    def schedule_task(player: Player, task: dict) -> None:
        player.pending_tasks.append(task)

    def task_duration(base_level: int, kind: str) -> int:
        if kind == "building":
            return int((base_level ** 2.35) * random.randint(260, 520))
        if kind == "research":
            return int(((base_level + 1) ** 2.25) * random.randint(320, 620))
        return int(max(300, random.randint(160, 280) * base_level))

    def maybe_speedup(player: Player, duration: int) -> int:
        weights = [(0.0, 0.46), (0.10, 0.18), (0.25, 0.16), (0.50, 0.12), (0.80, 0.08)]
        if player.payer_segment in {"dolphin", "whale"}:
            weights = [(0.0, 0.22), (0.20, 0.20), (0.45, 0.22), (0.70, 0.20), (0.90, 0.16)]
        return int(duration * float(weighted_choice(weights)))

    def process_due_tasks(player: Player, sid: int, session_start: datetime, session_end: datetime, lifecycle_day: int, seq: int, tick, version_info: tuple[str, int, str, str], network: str) -> int:
        nonlocal upgrade_id, research_id, training_id
        client_version, app_build, sdk_version, schema_version = version_info
        due = [t for t in player.pending_tasks if t["finish_time"] <= session_end]
        for task in sorted(due, key=lambda t: t["finish_time"])[:8]:
            if task not in player.pending_tasks:
                continue
            player.pending_tasks.remove(task)
            claim_time = tick(3, 30)
            if task["kind"] == "building":
                player.power += task["power_gain"]
                building_levels[player.player_id][task["building_type"]] = task["to_level"]
                if task["building_type"] == "main_city":
                    player.city_level = max(player.city_level, task["to_level"])
                finish_uid = add_event(player, claim_time, sid, "building_upgrade_finish", lifecycle_day, seq, {"task_id": task["task_id"], "building_type": task["building_type"], "to_level": task["to_level"], "power_gain": task["power_gain"], "finish_reason": "normal"}, client_version, app_build, sdk_version, schema_version, network, "server")
                seq += 1
                building_rows.append((upgrade_id, task["task_id"], task["start_event_uid"], finish_uid, task["start_time"], task["finish_time"], claim_time, task["start_session_id"], sid, player.player_id, player.server_id, task["building_type"], task["from_level"], task["to_level"], task["duration_seconds"], task["speedup_seconds"], "normal", task["power_gain"], json.dumps(task["cost"], ensure_ascii=False)))
                upgrade_id += 1
            elif task["kind"] == "research":
                player.power += task["power_gain"]
                research_levels[player.player_id][task["research_type"]] = task["to_level"]
                finish_uid = add_event(player, claim_time, sid, "research_finish", lifecycle_day, seq, {"task_id": task["task_id"], "research_type": task["research_type"], "to_level": task["to_level"], "power_gain": task["power_gain"], "finish_reason": "normal"}, client_version, app_build, sdk_version, schema_version, network, "server")
                seq += 1
                research_rows.append((research_id, task["task_id"], task["start_event_uid"], finish_uid, task["start_time"], task["finish_time"], claim_time, task["start_session_id"], sid, player.player_id, player.server_id, task["research_type"], task["from_level"], task["to_level"], task["duration_seconds"], task["speedup_seconds"], "normal", task["power_gain"], json.dumps(task["cost"], ensure_ascii=False)))
                research_id += 1
            else:
                player.power += task["power_gain"]
                finish_uid = add_event(player, claim_time, sid, "troop_train_finish", lifecycle_day, seq, {"task_id": task["task_id"], "troop_type": task["troop_type"], "troop_tier": task["troop_tier"], "troop_count": task["troop_count"], "power_gain": task["power_gain"]}, client_version, app_build, sdk_version, schema_version, network, "server")
                seq += 1
                training_rows.append((training_id, task["task_id"], task["start_event_uid"], finish_uid, task["start_time"], task["finish_time"], claim_time, task["start_session_id"], sid, player.player_id, player.server_id, task["troop_type"], task["troop_tier"], task["troop_count"], task["duration_seconds"], task["speedup_seconds"], "normal", task["power_gain"], json.dumps(task["cost"], ensure_ascii=False)))
                training_id += 1
            if player.level < min(60, player.city_level * 2 + player.active_days // 2 + 2) and random.random() < 0.22:
                old_level = player.level
                player.level += 1
                add_event(player, tick(2, 18), sid, "level_up", lifecycle_day, seq, {"from_level": old_level, "to_level": player.level}, client_version, app_build, sdk_version, schema_version, network, "server")
                seq += 1
        return seq

    for player in players:
        install_index = (player.install_date - start).days
        for day_index in range(install_index, args.days):
            current_day = days[day_index]
            lifecycle_day = day_index - install_index
            is_active = random.random() < active_probability(player, lifecycle_day, current_day)
            daily_sessions = 0
            if not is_active:
                continue
            previous_active = player.last_active_date
            player.last_active_date = current_day
            player.active_days += 1
            version_info = app_version_for_day(day_index)
            client_version, app_build, sdk_version, schema_version = version_info
            for start_time in session_start_times(current_day, session_count(player, lifecycle_day)):
                sid = session_id
                session_id += 1
                session_uid = f"sess_{sid:012d}"
                duration = session_duration_seconds(player)
                end_time = min(start_time + timedelta(seconds=duration), day_dt(current_day, 23, 59, 59))
                duration = max(1, int((end_time - start_time).total_seconds()))
                level_start = player.level
                power_start = player.power
                daily_sessions += 1
                seq = 1
                offset = 0

                def tick(min_step: int = 4, max_step: int = 65) -> datetime:
                    nonlocal offset
                    offset += random.randint(min_step, max_step)
                    return min(start_time + timedelta(seconds=offset), end_time - timedelta(seconds=1))

                network = str(weighted_choice([("wifi", 0.58), ("5g", 0.22), ("4g", 0.17), ("unknown", 0.03)]))
                ip_country = player.country if random.random() < 0.97 else str(weighted_choice([(c[0], c[2]) for c in COUNTRIES]))
                if lifecycle_day > 0 and daily_sessions == 1 and random.random() < 0.10:
                    add_event(player, tick(1, 3), sid, "push_open", lifecycle_day, seq, {"push_type": str(weighted_choice([("building_complete", 0.35), ("troop_complete", 0.20), ("alliance_help", 0.20), ("limited_pack", 0.25)]))}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                add_event(player, tick(1, 3), sid, "app_start", lifecycle_day, seq, {"network_type": network}, client_version, app_build, sdk_version, schema_version, network)
                seq += 1
                add_event(player, tick(), sid, "login", lifecycle_day, seq, {"login_day": lifecycle_day}, client_version, app_build, sdk_version, schema_version, network)
                seq += 1

                if lifecycle_day == 0 and daily_sessions == 1:
                    add_event(player, tick(), sid, "device_register", lifecycle_day, seq, {"device_id": player.device_id, "app_instance_id": f"inst_{player.device_id}"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                    if player.channel not in {"organic", "app_store_search"}:
                        add_event(player, tick(), sid, "ad_impression", lifecycle_day, seq, {"ad_network": player.channel, "campaign_id": player.campaign, "creative_id": f"cr_{random.randint(1, 80):03d}"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                        seq += 1
                        if random.random() < 0.72:
                            add_event(player, tick(), sid, "ad_click", lifecycle_day, seq, {"ad_network": player.channel, "campaign_id": player.campaign, "creative_id": f"cr_{random.randint(1, 80):03d}"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                            seq += 1
                    add_event(player, tick(), sid, "install", lifecycle_day, seq, {"campaign_id": player.campaign, "ad_channel": player.channel}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                    add_event(player, tick(), sid, "register", lifecycle_day, seq, {"server_id": player.server_id, "role_id": player.role_id, "country": player.country}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    add_event(player, tick(), sid, "server_select", lifecycle_day, seq, {"server_code": f"K{player.server_id}"}, client_version, app_build, sdk_version, schema_version, network)
                    seq += 1

                if previous_active and daily_sessions == 1:
                    offline_hours = max(1, int((current_day - previous_active).days * random.uniform(14, 24)))
                    if offline_hours >= 8 and random.random() < 0.42:
                        uid = add_event(player, tick(), sid, "offline_reward_claim", lifecycle_day, seq, {"offline_hours": offline_hours}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                        for res in random.sample(RESOURCE_TYPES[:4], k=random.randint(1, 2)):
                            seq_event_time = tick(1, 12)
                            _, seq = add_resource(player, seq_event_time, sid, lifecycle_day, seq, res, random.randint(800, 4200) * max(1, player.city_level), "offline_reward", False, client_version, app_build, sdk_version, schema_version, network, uid, {"offline_hours": offline_hours})

                seq = process_due_tasks(player, sid, start_time, end_time, lifecycle_day, seq, tick, version_info, network)

                tutorial_steps_this_session = random.randint(5, 9) if lifecycle_day == 0 else random.randint(3, 6) if lifecycle_day == 1 else random.randint(0, 3)
                for _ in range(tutorial_steps_this_session):
                    if player.tutorial_step >= player.tutorial_target or player.tutorial_step >= 12:
                        break
                    if lifecycle_day > 0 and random.random() > 0.88:
                        break
                    player.tutorial_step += 1
                    add_event(player, tick(8, 60), sid, "tutorial_step", lifecycle_day, seq, {"step": player.tutorial_step, "chapter": math.ceil(player.tutorial_step / 4)}, client_version, app_build, sdk_version, schema_version, network)
                    seq += 1
                    if player.tutorial_step in {3, 7, 12}:
                        uid = add_event(player, tick(), sid, "quest_complete", lifecycle_day, seq, {"quest_type": "tutorial", "quest_id": f"tutorial_{player.tutorial_step:02d}"}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                        player.level += 1
                        player.power += random.randint(120, 320)
                        _, seq = add_resource(player, tick(), sid, lifecycle_day, seq, "food", random.randint(1200, 3600), "tutorial_reward", False, client_version, app_build, sdk_version, schema_version, network, uid, {"step": player.tutorial_step})

                if player.alliance_id is None and lifecycle_day >= 1 and random.random() < min(0.55, player.alliance_propensity * 0.18 + lifecycle_day * 0.003):
                    player.alliance_id = choose_alliance(player.server_id)
                    alliance = next(a for a in alliances if a["alliance_id"] == player.alliance_id)
                    alliance["member_count"] = min(alliance["max_members"], alliance["member_count"] + 1)
                    if alliance["leader_player_id"] is None and alliance["member_count"] <= 3:
                        alliance["leader_player_id"] = player.player_id
                    add_event(player, tick(), sid, "alliance_join", lifecycle_day, seq, {"alliance_id": player.alliance_id, "alliance_tier": alliance["tier"]}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1

                quest_count = random.randint(1, 4 if lifecycle_day < 10 else 3)
                for _ in range(quest_count):
                    uid = add_event(player, tick(), sid, "quest_complete", lifecycle_day, seq, {"quest_type": str(weighted_choice([("main", 0.32), ("daily", 0.46), ("alliance", 0.22)])), "quest_level": player.level}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    reward = random.randint(700, 2600) * max(1, player.level // 2)
                    res = str(weighted_choice([(r, 1.0) for r in RESOURCE_TYPES[:4]]))
                    _, seq = add_resource(player, tick(1, 10), sid, lifecycle_day, seq, res, reward, "quest_reward", False, client_version, app_build, sdk_version, schema_version, network, uid, {"quest_level": player.level})

                building_queue_limit = 1 + (1 if player.payer_segment in {"dolphin", "whale"} or player.city_level >= 5 else 0)
                building_pending = sum(1 for t in player.pending_tasks if t["kind"] == "building")
                for _ in range(max(0, building_queue_limit - building_pending)):
                    if random.random() > (0.92 if player.active_days <= 7 else 0.68):
                        continue
                    b_type = "main_city" if random.random() < 0.36 else random.choice(BUILDINGS[1:])
                    from_level = building_levels[player.player_id][b_type]
                    max_allowed = min(30, 2 + player.active_days + lifecycle_day // 4)
                    if b_type != "main_city":
                        max_allowed = min(30, max(player.city_level + 1, 3))
                    if from_level >= max_allowed:
                        continue
                    to_level = from_level + 1
                    duration_base = task_duration(to_level, "building")
                    speedup = maybe_speedup(player, duration_base)
                    effective_duration = max(60, duration_base - speedup)
                    et = tick()
                    task_id = next_task_id("build", player.player_id)
                    start_uid = add_event(player, et, sid, "building_upgrade_start", lifecycle_day, seq, {"task_id": task_id, "building_type": b_type, "from_level": from_level, "to_level": to_level, "duration_seconds": duration_base}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    cost = {"food": int(to_level ** 2 * random.randint(220, 420)), "wood": int(to_level ** 2 * random.randint(250, 470)), "stone": int(to_level ** 2 * random.randint(100, 260)), "iron": int(to_level ** 2 * random.randint(60, 150))}
                    for res, amount in cost.items():
                        _, seq = add_resource(player, tick(1, 8), sid, lifecycle_day, seq, res, -amount, "building_upgrade", False, client_version, app_build, sdk_version, schema_version, network, start_uid, {"task_id": task_id, "building_type": b_type})
                    if speedup > 0:
                        item_uid = add_event(player, tick(), sid, "item_use", lifecycle_day, seq, {"item_type": "speedup", "target": "building", "task_id": task_id}, client_version, app_build, sdk_version, schema_version, network)
                        seq += 1
                        add_event(player, tick(), sid, "speedup_use", lifecycle_day, seq, {"target": "building", "task_id": task_id, "speedup_seconds": speedup, "item_event_uid": item_uid}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    schedule_task(player, {"kind": "building", "task_id": task_id, "start_event_uid": start_uid, "start_time": et, "finish_time": et + timedelta(seconds=effective_duration), "start_session_id": sid, "building_type": b_type, "from_level": from_level, "to_level": to_level, "duration_seconds": duration_base, "speedup_seconds": speedup, "cost": cost, "power_gain": int(to_level ** 1.85 * random.randint(45, 95) * (1.9 if b_type == "main_city" else 1.0))})

                if player.city_level >= 3 and sum(1 for t in player.pending_tasks if t["kind"] == "research") == 0 and random.random() < (0.68 if player.active_days <= 12 else 0.46):
                    r_type = random.choice(RESEARCH_TYPES)
                    from_level = research_levels[player.player_id][r_type]
                    to_level = from_level + 1
                    duration_base = task_duration(to_level, "research")
                    speedup = maybe_speedup(player, duration_base)
                    et = tick()
                    task_id = next_task_id("research", player.player_id)
                    start_uid = add_event(player, et, sid, "research_start", lifecycle_day, seq, {"task_id": task_id, "research_type": r_type, "from_level": from_level, "to_level": to_level, "duration_seconds": duration_base}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    cost = {"food": int((to_level + 1) ** 2 * random.randint(160, 360)), "wood": int((to_level + 1) ** 2 * random.randint(150, 340)), "stone": int((to_level + 1) ** 2 * random.randint(80, 180))}
                    for res, amount in cost.items():
                        _, seq = add_resource(player, tick(1, 8), sid, lifecycle_day, seq, res, -amount, "research", False, client_version, app_build, sdk_version, schema_version, network, start_uid, {"task_id": task_id, "research_type": r_type})
                    if speedup > 0:
                        item_uid = add_event(player, tick(), sid, "item_use", lifecycle_day, seq, {"item_type": "speedup", "target": "research", "task_id": task_id}, client_version, app_build, sdk_version, schema_version, network)
                        seq += 1
                        add_event(player, tick(), sid, "speedup_use", lifecycle_day, seq, {"target": "research", "task_id": task_id, "speedup_seconds": speedup, "item_event_uid": item_uid}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    schedule_task(player, {"kind": "research", "task_id": task_id, "start_event_uid": start_uid, "start_time": et, "finish_time": et + timedelta(seconds=max(60, duration_base - speedup)), "start_session_id": sid, "research_type": r_type, "from_level": from_level, "to_level": to_level, "duration_seconds": duration_base, "speedup_seconds": speedup, "cost": cost, "power_gain": int((to_level + 1) ** 1.8 * random.randint(55, 110))})

                if player.city_level >= 2 and sum(1 for t in player.pending_tasks if t["kind"] == "training") < 2 and random.random() < 0.74:
                    troop_type = random.choice(TROOP_TYPES)
                    troop_tier = min(6, max(1, player.city_level // 4 + 1))
                    count = random.randint(90, 300) * troop_tier * (2 if player.activity_segment in {"hardcore", "social"} else 1)
                    duration_base = task_duration(count * troop_tier, "training")
                    speedup = maybe_speedup(player, duration_base)
                    et = tick()
                    task_id = next_task_id("train", player.player_id)
                    start_uid = add_event(player, et, sid, "troop_train_start", lifecycle_day, seq, {"task_id": task_id, "troop_type": troop_type, "troop_tier": troop_tier, "troop_count": count}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    cost = {"food": count * troop_tier * 4, "wood": count * troop_tier * 3, "iron": count * troop_tier}
                    for res, amount in cost.items():
                        _, seq = add_resource(player, tick(1, 8), sid, lifecycle_day, seq, res, -amount, "troop_training", False, client_version, app_build, sdk_version, schema_version, network, start_uid, {"task_id": task_id, "troop_type": troop_type})
                    if speedup > 0:
                        item_uid = add_event(player, tick(), sid, "item_use", lifecycle_day, seq, {"item_type": "speedup", "target": "troop_training", "task_id": task_id}, client_version, app_build, sdk_version, schema_version, network)
                        seq += 1
                        add_event(player, tick(), sid, "speedup_use", lifecycle_day, seq, {"target": "troop_training", "task_id": task_id, "speedup_seconds": speedup, "item_event_uid": item_uid}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    schedule_task(player, {"kind": "training", "task_id": task_id, "start_event_uid": start_uid, "start_time": et, "finish_time": et + timedelta(seconds=max(60, duration_base - speedup)), "start_session_id": sid, "troop_type": troop_type, "troop_tier": troop_tier, "troop_count": count, "duration_seconds": duration_base, "speedup_seconds": speedup, "cost": cost, "power_gain": count * troop_tier * random.randint(2, 5)})

                battle_base = 1 if player.city_level < 4 else 2
                if player.activity_segment in {"engaged", "social", "hardcore"}:
                    battle_base += 1
                for _ in range(random.randint(0, battle_base + (2 if lifecycle_day < 7 else 1))):
                    is_pvp = player.city_level >= 5 and random.random() < (0.12 if player.activity_segment in {"casual", "regular"} else 0.26 if player.activity_segment in {"engaged", "social"} else 0.38)
                    b_type = "pvp" if is_pvp else str(weighted_choice([("pve_chapter", 0.44), ("world_monster", 0.38), ("resource_tile", 0.18)]))
                    target_type = "player" if is_pvp else ("monster" if b_type == "world_monster" else "npc")
                    target_id = None
                    if is_pvp and len(players_by_server[player.server_id]) > 1:
                        target_id = random.choice(players_by_server[player.server_id])
                        if target_id == player.player_id:
                            target_id = None
                    battle_uid = f"battle_{battle_id:010d}"
                    march_uid = add_event(player, tick(), sid, "march_start", lifecycle_day, seq, {"battle_uid": battle_uid, "march_type": b_type, "target_type": target_type}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    win_rate = 0.73 if not is_pvp else 0.50 + min(0.18, math.log(max(player.power, 1), 10) / 55)
                    result = "win" if random.random() < win_rate else "lose"
                    troops_sent = random.randint(800, 8500) * max(1, player.city_level // 4)
                    loss_ratio = random.uniform(0.01, 0.05) if result == "win" else random.uniform(0.06, 0.17)
                    troops_lost = int(troops_sent * loss_ratio)
                    wounded = int(troops_sent * loss_ratio * random.uniform(1.2, 2.8))
                    power_delta = -int(troops_lost * random.uniform(1.6, 3.4))
                    loot = int(random.randint(500, 6500) * (player.city_level / 2.5)) if result == "win" else 0
                    event_name = "pvp_battle_result" if is_pvp else "world_monster_attack" if b_type == "world_monster" else "pve_battle_result"
                    result_uid = add_event(player, tick(), sid, event_name, lifecycle_day, seq, {"battle_uid": battle_uid, "battle_type": b_type, "result": result, "resource_looted": loot}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    finish_uid = add_event(player, tick(), sid, "march_finish", lifecycle_day, seq, {"battle_uid": battle_uid, "march_type": b_type, "result": result}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1
                    battle_rows.append((battle_id, battle_uid, result_uid, march_uid, finish_uid, tick(1, 2), current_day, player.player_id, player.server_id, sid, b_type, target_type, target_id, result, troops_sent, troops_lost, wounded, power_delta, loot, 10 if is_pvp else 6, random.randint(1, 1200), random.randint(1, 1200), json.dumps({"city_level": player.city_level, "attacker_power": player.power}, ensure_ascii=False)))
                    battle_id += 1
                    player.power = max(800, player.power + power_delta + (random.randint(30, 160) if result == "win" else 0))
                    if loot:
                        res = str(weighted_choice([(r, 1.0) for r in RESOURCE_TYPES[:4]]))
                        _, seq = add_resource(player, tick(), sid, lifecycle_day, seq, res, loot, "battle_loot", False, client_version, app_build, sdk_version, schema_version, network, result_uid, {"battle_uid": battle_uid, "battle_type": b_type})

                if player.alliance_id is not None:
                    help_count = random.randint(0, 8 if player.activity_segment in {"social", "hardcore"} else 4)
                    if help_count:
                        add_event(player, tick(), sid, "alliance_help", lifecycle_day, seq, {"help_count": help_count}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    if random.random() < (0.34 if player.activity_segment in {"social", "hardcore"} else 0.14):
                        add_event(player, tick(), sid, "alliance_donate", lifecycle_day, seq, {"donate_type": str(weighted_choice([("wood", 0.35), ("food", 0.34), ("stone", 0.22), ("gold", 0.09)]))}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    if player.city_level >= 6 and random.random() < (0.18 if player.activity_segment in {"social", "hardcore"} else 0.08):
                        add_event(player, tick(), sid, "rally_join", lifecycle_day, seq, {"rally_type": str(weighted_choice([("monster", 0.58), ("fortress", 0.25), ("kingdom_war", 0.17)]))}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    if random.random() < (0.36 if player.activity_segment == "social" else 0.11 if player.activity_segment in {"engaged", "hardcore"} else 0.04):
                        add_event(player, tick(), sid, "chat_send", lifecycle_day, seq, {"chat_channel": "alliance" if random.random() < 0.76 else "world"}, client_version, app_build, sdk_version, schema_version, network)
                        seq += 1

                if random.random() < 0.24:
                    add_event(player, tick(), sid, "mail_read", lifecycle_day, seq, {"mail_type": str(weighted_choice([("system", 0.30), ("battle_report", 0.44), ("alliance", 0.26)]))}, client_version, app_build, sdk_version, schema_version, network)
                    seq += 1

                if random.random() < (0.20 if player.payer_segment == "non_spender" else 0.66):
                    add_event(player, tick(), sid, "shop_view", lifecycle_day, seq, {"shop_tab": str(weighted_choice([("daily_pack", 0.34), ("limited", 0.28), ("vip", 0.14), ("resource", 0.12), ("war", 0.12)]))}, client_version, app_build, sdk_version, schema_version, network)
                    seq += 1

                if should_attempt_pay(player, lifecycle_day):
                    product_id, product_name, amount = choose_product(player)
                    order_id = f"ORD{current_day.strftime('%Y%m%d')}{order_seq:08d}"
                    order_seq += 1
                    start_uid = add_event(player, tick(), sid, "purchase_start", lifecycle_day, seq, {"order_id": order_id, "product_id": product_id, "price_usd": str(amount)}, client_version, app_build, sdk_version, schema_version, network)
                    seq += 1
                    outcome = str(weighted_choice([("success", 0.885), ("failed", 0.075), ("cancelled", 0.040)]))
                    fail_reason = None
                    refund_reason = None
                    refund_amount = Decimal("0.00")
                    gross = Decimal("0.00")
                    net = Decimal("0.00")
                    is_first = player.pay_count == 0
                    if outcome == "success":
                        player.pay_count += 1
                        gross = amount
                        net = amount
                        if random.random() < 0.018:
                            outcome = "refunded"
                            refund_amount = amount
                            net = Decimal("0.00")
                            refund_reason = str(weighted_choice([("chargeback", 0.45), ("customer_service", 0.35), ("fraud_risk", 0.20)]))
                        else:
                            player.total_pay_amount += amount
                            player.vip_level = vip_level(player.total_pay_amount)
                            if is_first:
                                player.first_pay_time = tick()
                        final_event = "refund" if outcome == "refunded" else "purchase_success"
                        attrs = {"order_id": order_id, "product_id": product_id, "amount_usd": str(amount), "is_first_pay": is_first}
                        if outcome == "refunded":
                            attrs["refund_reason"] = refund_reason
                            attrs["refund_amount_usd"] = str(refund_amount)
                        final_uid = add_event(player, tick(), sid, final_event, lifecycle_day, seq, attrs, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                        if outcome == "success":
                            _, seq = add_resource(player, tick(), sid, lifecycle_day, seq, "gold", max(60, int(float(amount) * 120)), "payment_grant", True, client_version, app_build, sdk_version, schema_version, network, final_uid, {"order_id": order_id, "product_id": product_id})
                            grant = int(float(amount) * random.randint(1800, 3600))
                            _, seq = add_resource(player, tick(), sid, lifecycle_day, seq, str(weighted_choice([(r, 1.0) for r in RESOURCE_TYPES[:4]])), grant, "payment_grant", True, client_version, app_build, sdk_version, schema_version, network, final_uid, {"order_id": order_id, "product_id": product_id})
                    elif outcome == "failed":
                        fail_reason = str(weighted_choice([("insufficient_funds", 0.28), ("sdk_timeout", 0.24), ("payment_declined", 0.24), ("risk_control", 0.14), ("unknown", 0.10)]))
                        final_uid = add_event(player, tick(), sid, "payment_fail", lifecycle_day, seq, {"order_id": order_id, "product_id": product_id, "fail_reason": fail_reason}, client_version, app_build, sdk_version, schema_version, network, "server")
                        seq += 1
                    else:
                        final_uid = add_event(player, tick(), sid, "purchase_cancel", lifecycle_day, seq, {"order_id": order_id, "product_id": product_id}, client_version, app_build, sdk_version, schema_version, network)
                        seq += 1
                    revenue_tier = "whale" if amount >= Decimal("49.99") else "mid" if amount >= Decimal("9.99") else "low"
                    local_currency = "CNY" if player.country in {"CN", "TW", "HK"} else "USD"
                    pay_channel = "app_store" if player.platform == "ios" else str(weighted_choice([("google_play", 0.46), ("third_party", 0.32), ("web_pay", 0.22)]))
                    payment_rows.append((order_id, start_uid, final_uid, tick(1, 2), current_day, player.player_id, player.server_id, sid, product_id, product_name, amount, gross, refund_amount, net, local_currency, pay_channel, outcome, fail_reason, refund_reason, is_first, player.pay_count, lifecycle_day, player.vip_level, player.level, revenue_tier, json.dumps({"campaign": player.campaign, "payer_segment": player.payer_segment}, ensure_ascii=False)))

                if random.random() < 0.010:
                    add_event(player, tick(), sid, "network_error", lifecycle_day, seq, {"api": str(weighted_choice([("/battle/start", 0.25), ("/shop/buy", 0.15), ("/alliance/help", 0.20), ("/mail/list", 0.15), ("/resource/sync", 0.25)])), "error_code": "timeout"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                if random.random() < 0.004:
                    add_event(player, tick(), sid, "client_error", lifecycle_day, seq, {"error_code": f"E{random.randint(1000, 9999)}", "scene": "battle" if random.random() < 0.45 else "ui"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                if random.random() < (0.0018 if player.device_tier in {"low", "mid"} else 0.0008):
                    add_event(player, tick(), sid, "crash", lifecycle_day, seq, {"crash_type": str(weighted_choice([("native", 0.45), ("unity", 0.35), ("oom", 0.20)])), "scene": "world_map"}, client_version, app_build, sdk_version, schema_version, network, "sdk")
                    seq += 1
                if random.random() < 0.0008:
                    add_event(player, tick(), sid, "anti_cheat_flag", lifecycle_day, seq, {"rule_id": str(weighted_choice([("speedhack_001", 0.45), ("memory_patch_003", 0.20), ("payment_risk_002", 0.20), ("bot_pattern_004", 0.15)])), "risk_score": random.randint(40, 95)}, client_version, app_build, sdk_version, schema_version, network, "server")
                    seq += 1

                seq = process_due_tasks(player, sid, start_time, end_time, lifecycle_day, seq, tick, version_info, network)

                add_event(player, end_time, sid, "logout", lifecycle_day, seq, {"duration_seconds": duration}, client_version, app_build, sdk_version, schema_version, network)
                session_rows.append((sid, session_uid, player.player_id, player.account_id, player.role_id, player.device_id, player.server_id, start_time, end_time, duration, lifecycle_day, level_start, player.level, power_start, player.power, player.platform, player.channel, player.campaign, client_version, app_build, sdk_version, player.device_tier, player.device_model, player.os_version, network, player.country, ip_country))

    recent_cutoff = end - timedelta(days=6)
    alliance_by_id = {a["alliance_id"]: a for a in alliances}
    player_rows = []
    for p in players:
        player_rows.append((p.player_id, p.account_id, p.role_id, p.device_id, p.register_time, p.install_date, p.country, p.language, p.platform, p.channel, p.campaign, p.device_tier, p.device_model, p.os_version, p.server_id, p.activity_segment, p.payer_segment, p.level, p.vip_level, p.power, p.city_level, p.alliance_id, p.first_pay_time, p.total_pay_amount, p.last_active_date))
        if p.alliance_id is not None:
            alliance_by_id[p.alliance_id]["total_power"] += p.power
            if p.last_active_date and p.last_active_date >= recent_cutoff:
                alliance_by_id[p.alliance_id]["active_member_7d"] += 1
    alliance_rows = [(a["alliance_id"], a["server_id"], a["alliance_tag"], a["alliance_name"], a["language"], a["tier"], a["create_time"], a["max_members"], a["member_count"], a["active_member_7d"], a["total_power"], a["leader_player_id"]) for a in alliances]
    event_name_rows = [(name, meta[0], meta[1], meta[2], json.dumps(meta[3], ensure_ascii=False)) for name, meta in EVENTS.items()]

    conn = psycopg.connect(host=args.host, port=args.port, dbname=args.db_name, user=args.user, password=args.password)
    create_schema(conn)
    copy_rows(conn, "dim_server", ["server_id", "server_code", "server_name", "open_date", "region", "timezone"], servers)
    copy_rows(conn, "dim_alliance", ["alliance_id", "server_id", "alliance_tag", "alliance_name", "language", "tier", "create_time", "max_members", "member_count", "active_member_7d", "total_power", "leader_player_id"], alliance_rows)
    copy_rows(conn, "dim_product", ["product_id", "product_name", "product_type", "price_usd", "limit_type", "unlock_level", "is_first_pay_pack"], PRODUCTS)
    copy_rows(conn, "dim_event_name", ["event_name", "event_category", "event_cn_name", "description", "required_attrs"], event_name_rows)
    copy_rows(conn, "dim_player", ["player_id", "account_id", "role_id", "device_id", "register_time", "install_date", "country", "language", "platform", "channel", "campaign", "device_tier", "device_model", "os_version", "register_server_id", "activity_segment", "payer_segment", "current_level", "current_vip_level", "current_power", "current_city_level", "current_alliance_id", "first_pay_time", "total_pay_amount", "last_active_date"], player_rows)
    copy_rows(conn, "fact_sessions", ["session_id", "session_uid", "player_id", "account_id", "role_id", "device_id", "server_id", "session_start", "session_end", "duration_seconds", "lifecycle_day", "player_level_start", "player_level_end", "power_start", "power_end", "platform", "channel", "campaign", "client_version", "app_build", "sdk_version", "device_tier", "device_model", "os_version", "network_type", "country", "ip_country"], session_rows)
    copy_rows(conn, "fact_events", ["event_uid", "client_event_id", "trace_id", "event_time", "client_time", "server_receive_time", "ingest_time", "event_date", "player_id", "account_id", "role_id", "device_id", "server_id", "session_id", "event_name", "event_category", "lifecycle_day", "player_level", "vip_level", "power", "alliance_id", "client_version", "app_build", "sdk_version", "event_schema_version", "platform", "channel", "campaign", "country", "ip_country", "language", "device_model", "os_version", "device_tier", "network_type", "event_source", "sequence_in_session", "attributes"], event_rows)
    copy_rows(conn, "fact_payments", ["order_id", "start_event_uid", "final_event_uid", "event_time", "event_date", "player_id", "server_id", "session_id", "product_id", "product_name", "amount_usd", "gross_revenue_usd", "refund_amount_usd", "net_revenue_usd", "local_currency", "payment_channel", "payment_status", "fail_reason", "refund_reason", "is_first_pay", "pay_sequence", "lifecycle_day", "vip_level_after", "player_level", "revenue_tier", "attributes"], payment_rows)
    copy_rows(conn, "fact_battles", ["battle_id", "battle_uid", "event_uid", "march_start_event_uid", "march_finish_event_uid", "event_time", "event_date", "player_id", "server_id", "session_id", "battle_type", "target_type", "target_player_id", "result", "troops_sent", "troops_lost", "wounded", "power_delta", "resource_looted", "stamina_spent", "map_x", "map_y", "attributes"], battle_rows)
    copy_rows(conn, "fact_resource_transactions", ["trans_id", "event_uid", "business_event_uid", "event_time", "event_date", "player_id", "server_id", "session_id", "resource_type", "change_amount", "balance_after", "source_sink", "reason", "is_paid_related", "attributes"], resource_rows)
    copy_rows(conn, "fact_building_upgrades", ["upgrade_id", "task_id", "start_event_uid", "finish_event_uid", "start_time", "finish_time", "claim_time", "start_session_id", "finish_session_id", "player_id", "server_id", "building_type", "from_level", "to_level", "duration_seconds", "speedup_seconds", "finish_reason", "power_gain", "cost_json"], building_rows)
    copy_rows(conn, "fact_research", ["research_id", "task_id", "start_event_uid", "finish_event_uid", "start_time", "finish_time", "claim_time", "start_session_id", "finish_session_id", "player_id", "server_id", "research_type", "from_level", "to_level", "duration_seconds", "speedup_seconds", "finish_reason", "power_gain", "cost_json"], research_rows)
    copy_rows(conn, "fact_army_training", ["training_id", "task_id", "start_event_uid", "finish_event_uid", "start_time", "finish_time", "claim_time", "start_session_id", "finish_session_id", "player_id", "server_id", "troop_type", "troop_tier", "troop_count", "duration_seconds", "speedup_seconds", "finish_reason", "power_gain", "cost_json"], training_rows)
    with conn.cursor() as cur:
        cur.execute(
            """
            create index idx_fact_events_date_name on fact_events(event_date, event_name);
            create index idx_fact_events_uid on fact_events(event_uid);
            create index idx_fact_events_player_time on fact_events(player_id, event_time);
            create index idx_fact_events_session on fact_events(session_id);
            create index idx_fact_events_attrs_gin on fact_events using gin(attributes);
            create index idx_sessions_start_server on fact_sessions(session_start, server_id);
            create index idx_payments_status_date on fact_payments(payment_status, event_date);
            create index idx_battles_date_type on fact_battles(event_date, battle_type);
            create index idx_resource_date_reason on fact_resource_transactions(event_date, reason);
            create index idx_building_task_time on fact_building_upgrades(start_time, finish_time);
            create index idx_research_task_time on fact_research(start_time, finish_time);
            create index idx_training_task_time on fact_army_training(start_time, finish_time);
            analyze;
            """
        )
    conn.commit()
    conn.close()
    return {
        "servers": len(servers),
        "alliances": len(alliance_rows),
        "players": len(player_rows),
        "sessions": len(session_rows),
        "events": len(event_rows),
        "payment_orders": len(payment_rows),
        "battles": len(battle_rows),
        "resource_transactions": len(resource_rows),
        "building_upgrades": len(building_rows),
        "research": len(research_rows),
        "army_training": len(training_rows),
    }


def main() -> None:
    args = parse_args()
    ensure_database(args)
    counts = generate(args)
    print(json.dumps({"database": args.db_name, "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
