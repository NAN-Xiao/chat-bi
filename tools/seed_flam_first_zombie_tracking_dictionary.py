# -*- coding: utf-8 -*-
"""Seed flam workspace tracking/event dictionary metadata."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import psycopg
from core_system_db import core_system_db_config
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DB = core_system_db_config()
UPDATE_BY = 1

LOGIN_EVENTS = [
    "UserActive",
]

REGISTER_EVENTS = [
    "UserRegister",
]

TRANSACTION_EVENTS = [
    "ServerPayLog",
]

PAYMENT_PROCESS_EVENTS = [
    "PayBuyRet",
    "PayBuyRetBenifit",
    "PayBuyRetSandBox",
    "PayFinish",
    "ep_pay_purchase_finish",
    "ep_pay_update_db_finish",
]

ONBOARDING_EVENTS = [
    "EnterGame",
    "Login",
    "UserLogin",
    "NewUserGuideStart",
    "DialogueStart",
    "NewUserGuide",
    "DialogueEnd",
    "ChapterTaskReward",
    "TaskReward",
]

ACTIVITY_EVENTS = [
    "ActivityAllianceBossBattleRet",
    "ActivityAllianceBossChoose",
    "ActivityAllianceBossDonation",
    "ActivityAllianceBossReward",
    "ActivityArmsRaceBoxOpen",
    "ActivityArmsRaceGoalPoint",
    "ActivityArmsRaceTask",
    "ActivityChestCount",
    "ActivityCommanderTask",
    "ActivityWheelCount",
    "ActivityWorldBoss",
    "AllianceDuelAlliancePoint",
    "AllianceDuelPersonalPoint",
    "AllianceDuelBoxOpen",
]

EXPEDITION_EVENTS = [
    "WorldMarch",
    "WorldMarchRet",
    "ActivityWorldBoss",
    "ActivityAllianceBossBattleRet",
    "honorExpedition",
    "ArenaResults",
    "TrainingArenaResults",
    "multipleArena",
]

BUILDING_EVENTS = ["BuildingUpgrade", "BuildingIdleUpgrade"]
TECH_EVENTS = ["TechnologyDonation"]
HERO_EVENTS = ["HeroAcquisition", "HeroLevelUp", "HeroStarUp", "HeroSkillUpgrade", "HeroRecruit"]
ARMY_EVENTS = ["ArmyUpgrade"]
GOLD_EVENTS = ["GoldChange"]


EVENT_GROUPS = [
    {
        "group_key": "new_user_registration",
        "group_name": "新增用户注册",
        "description": "新增用户/注册 cohort 使用 UserRegister 归一化注册事件；需要快照字段时再回连 user 注册日快照",
        "event_names": REGISTER_EVENTS,
        "sort_order": 10,
    },
    {
        "group_key": "active_user",
        "group_name": "活跃用户",
        "description": "DAU/WAU/MAU/活跃拆分使用 UserActive 归一化活跃事件",
        "event_names": LOGIN_EVENTS,
        "sort_order": 20,
    },
    {
        "group_key": "payment_transaction",
        "group_name": "真实充值交易",
        "description": "充值金额、订单、付费人数、ARPU/ARPPU 和首付只使用 ServerPayLog.personal。",
        "event_names": TRANSACTION_EVENTS,
        "sort_order": 30,
    },
    {
        "group_key": "payment_process_event",
        "group_name": "支付流程事件",
        "description": "支付流程事件量，不得作为充值金额、真实订单数或付费人数。",
        "event_names": PAYMENT_PROCESS_EVENTS,
        "sort_order": 40,
    },
    {
        "group_key": "ccu",
        "group_name": "实时在线人数",
        "description": "实时在线人数事件；在线人数读取 personal.ed_ccu。",
        "event_names": ["CCU"],
        "sort_order": 50,
    },
    {
        "group_key": "onboarding_funnel",
        "group_name": "新手引导漏斗",
        "description": "新手引导漏斗事件集合；默认起点仍为 user 注册 cohort，不是全量登录用户",
        "event_names": ONBOARDING_EVENTS,
        "sort_order": 60,
    },
    {
        "group_key": "activity_participation",
        "group_name": "活动参与",
        "description": "活动参与率、人均参与次数、活动参与频次和活动后续质量使用的活动事件集合",
        "event_names": ACTIVITY_EVENTS,
        "sort_order": 70,
    },
    {
        "group_key": "expedition_drill",
        "group_name": "出征与演习",
        "description": "出征、竞技场、荣耀远征、世界 Boss、联盟 Boss 和演习类看板使用的事件集合",
        "event_names": EXPEDITION_EVENTS,
        "sort_order": 80,
    },
    {
        "group_key": "army_upgrade",
        "group_name": "兵种升级",
        "description": "兵种升级、兵种招募和兵种相关主城成长指标使用的事件",
        "event_names": ARMY_EVENTS,
        "sort_order": 90,
    },
    {
        "group_key": "gold_economy",
        "group_name": "钻石经济",
        "description": "钻石获取、消耗和存量变化使用 GoldChange，并读取 personal.ed_changeFree/personal.ed_changePaid",
        "event_names": GOLD_EVENTS,
        "sort_order": 100,
    },
    {
        "group_key": "city_building_upgrade",
        "group_name": "主城建筑升级",
        "description": "主城/建筑升级类指标使用的建筑升级事件集合",
        "event_names": BUILDING_EVENTS,
        "sort_order": 110,
    },
    {
        "group_key": "technology_upgrade",
        "group_name": "科技升级",
        "description": "科技升级类指标只使用个人科技升级事件 TechnologyDonation",
        "event_names": TECH_EVENTS,
        "sort_order": 120,
    },
    {
        "group_key": "hero_growth",
        "group_name": "英雄养成",
        "description": "英雄获取、升级、升星、技能升级和招募相关养成指标使用的事件集合",
        "event_names": HERO_EVENTS,
        "sort_order": 130,
    },
]


TRACKING_CONFIG = {
    "enabled": True,
    "default_event_table": "event",
    "default_subject_field": "uid",
    "default_event_name_field": "event",
    "default_event_time_field": "time",
    "field_role_mappings": [
        {"role": "subject_id", "table": "event", "field": "uid", "description": "事件主体用户 ID"},
        {"role": "event_name", "table": "event", "field": "event", "description": "业务事件名"},
        {"role": "event_time", "table": "event", "field": "time", "description": "毫秒时间戳，实时口径需转 UTC+8"},
        {"role": "partition_date", "table": "event", "field": "dt", "description": "业务日期分区 yyyyMMdd"},
        {"role": "snapshot_date", "table": "user", "field": "dt", "description": "用户快照日期 yyyyMMdd"},
    ],
    "event_name_mappings": [],
    "sql_rules": "\n".join(
        [
            "flam 历史趋势、成熟 cohort 和当前快照类看板以 CURDATE() 的前一日作为最近完整业务日，并过滤 prod=110000038；避免对 ADS 大视图先做 MAX(dt)。",
            "event.time 为毫秒时间戳；实时业务日按 UTC+8 转换，历史离线看板优先使用 dt 分区。",
            "JSON 子字段使用 JSON_UNQUOTE(JSON_EXTRACT(field, '$.path')) 提取，空字符串需要 NULLIF 后再 COALESCE。",
            "活跃用户必须过滤 UserActive 归一化活跃事件后按 uid 去重，不使用 event 全事件去重，也不直接用 user 快照行数代替。",
            "核心看板新手引导漏斗默认以 user 注册日 cohort 为起点，后续步骤按 cohort 内 uid 去重统计。",
            "真实交易只使用 ServerPayLog：金额为 personal.money，订单为 personal.orderId，礼包/商品 ID 为 personal.productid；支付流程事件只可按 event 名称统计流程量。",
            "日新增充值用户使用 user.pay.firstpaytime 转换的首付业务日，不得使用分析窗口内 MIN(event.dt) 代替。",
            "user.pay.firstpaytime 是毫秒时间戳；历史首付日使用 DATE_FORMAT(FROM_UNIXTIME(firstpaytime / 1000), '%Y%m%d')，采样已与 ServerPayLog.dt 对齐，不额外套用实时 UTC+8 转换。",
            "新增 cohort 可使用 UserRegister 注册事件按 uid 去重；需要读取 pay、remain、当前等级等快照字段时，再回连 user 注册日或成熟生命周期日快照。",
            "新增首日付费固定取注册日快照 pay.pay1，不从后续快照取 MAX(pay1)。",
            "新增 cohort LTV 中，首日/1日 LTV 使用 pay.pay1；次日/2日 LTV 使用 pay.pay2；3日/7日/14日/30日 LTV 分别使用 pay.pay3/pay7/pay14/pay30。不要把“次日 LTV”写成 pay1；目标日期超过最近完整日的未成熟 cohort 返回 NULL。",
            "留存标记 remain1/remain3/remain7 必须在注册后精确第 1/3/7 日快照读取；未成熟 cohort 返回 NULL，不按 0 处理。",
            "付费用户周累充分布必须先按自然周取每个 uid 的最新 user 快照，再按 pay.paytotal 分段，避免多日快照重复计数。",
            "活动参与率分母是同日 UserActive DAU，分子是活动事件 uid 去重；活动后续留存/付费必须先固定参与 cohort。",
            "钻石经济使用 GoldChange，变化字段在 personal.ed_changeFree 与 personal.ed_changePaid；正数计获取，负数绝对值计消耗。",
            "出征和演习胜率分母是出征/竞技事件行；已验证字段使用对应 personal JSON 路径，未验证字段不得从 ext 猜测回退。",
            "CCU 使用 personal.ed_ccu；建筑 ID/主城等级和出征战力使用对应 personal JSON 路径。加速类型暂无已验证字段映射，必须显示待补充字段映射状态。",
            "当前主城等级和主城升级漏斗使用 user 最新快照 lastinfo.blevel；不要用历史升级事件次数替代当前玩家数。",
            "英雄当前等级分布需要先按 uid 与英雄 ID 取最近一条养成事件，再统计人数；不要把升级事件次数当等级分布。",
        ]
    ),
    "notes": f"flam / first_zombie 工作空间字典，datasource_id={DATASOURCE_ID}。业务库核心表为 event 事件明细表和 user 用户日快照表。",
}

TABLES = [
    {
        "table_name": "event",
        "table_comment": "事件明细表。每行是一条用户行为或系统事件记录，核心字段为 uid、event、time、dt、prod，多个属性列为 JSON 文本。",
        "table_role": "event_fact",
        "aliases": ["事件表", "埋点表", "行为明细"],
        "ai_notes": "查询特定行为必须先过滤 event；已验证交易、CCU、建筑和出征字段从 personal 解析，userinfo/deviceinfo/adinfo/lastinfo 按各自 JSON 字段解析。未经采样验证的 ext 子字段不得作为指标口径。",
    },
    {
        "table_name": "user",
        "table_comment": "用户画像/用户日快照表。每行描述一个用户在某个业务日期分区下的属性快照。",
        "table_role": "daily_user_snapshot",
        "aliases": ["用户表", "用户快照", "用户画像"],
        "ai_notes": "新增、留存、LTV、累计付费和当前分布等快照类指标优先使用 user 表；新增 cohort 用 userinfo.regdate = dt。",
    },
]

FIELDS = [
    {
        "table_name": "event",
        "field_name": "uid",
        "field_comment": "用户唯一 ID；事件人数、活跃人数和参与人数按 uid 去重。",
        "field_role": "subject_id",
        "semantic_type": "identifier",
        "aliases": ["用户ID", "账号ID", "玩家ID"],
        "required": True,
    },
    {
        "table_name": "event",
        "field_name": "event",
        "field_comment": "事件名称/埋点名称；活跃、付费、活动、建筑等指标必须先筛选对应事件集合。如果该列在某些项目中承载 JSON 文本，子字段应另配为 source_field=event、json_path=$.xxx 的字典字段。",
        "field_role": "event_name",
        "semantic_type": "category",
        "aliases": ["事件名", "埋点名", "行为类型"],
        "value_mappings": TRACKING_CONFIG["event_name_mappings"],
        "required": True,
    },
    {
        "table_name": "event",
        "field_name": "dt",
        "field_comment": "事件业务日期分区，格式 yyyyMMdd。flam 持久历史看板以 CURDATE() 前一日派生最近完整 dt 窗口，避免先扫 event 做 MAX(dt)。",
        "field_role": "partition_date",
        "semantic_type": "date",
        "aliases": ["事件日期", "分区日期", "业务日期"],
        "required": True,
    },
    {
        "table_name": "event",
        "field_name": "time",
        "field_comment": "事件发生毫秒时间戳。实时看板需要 DATE_ADD(FROM_UNIXTIME(time/1000), INTERVAL 8 HOUR) 转业务时间。",
        "field_role": "event_time",
        "semantic_type": "timestamp_ms",
        "aliases": ["事件时间", "毫秒时间戳"],
    },
    {
        "table_name": "event",
        "field_name": "adinfo",
        "field_comment": "广告归因 JSON；活跃渠道优先取 mediaSource，其次 campaignName。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["广告归因", "渠道信息"],
        "expression": "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(adinfo, '$.campaignName')), ''), '未知')",
        "example_values": ["mediaSource", "campaignName"],
    },
    {
        "table_name": "event",
        "field_name": "deviceinfo",
        "field_comment": "设备信息 JSON；活跃系统优先取 _platform。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["设备信息", "系统信息"],
        "expression": "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(deviceinfo, '$._platform')), ''), '未知')",
        "example_values": ["_platform", "_osVersion", "_model"],
    },
    {
        "table_name": "event",
        "field_name": "userinfo.country",
        "field_comment": "事件用户国家/地区代码；活跃、付费和 ARPU/ARPPU 按国家拆分时优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "country_code",
        "aliases": ["国家", "地区", "国家地区"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.country'))",
        "example_values": ["US", "BR", "GB", "HK"],
        "ai_notes": "按国家分析事件类指标时，从同日事件行 userinfo.country 取归属；缺失时归为未知。",
    },
    {
        "table_name": "event",
        "field_name": "lastinfo",
        "field_comment": "事件发生时最近用户状态 JSON；事件分析可读取 level、blevel、regnday 等即时状态。",
        "field_role": "state_json",
        "semantic_type": "json",
        "aliases": ["最近状态", "用户状态"],
        "example_values": ["level", "blevel", "regnday"],
    },
    {
        "table_name": "event",
        "field_name": "allianceinfo",
        "field_comment": "联盟信息 JSON 文本；联盟维度分析的具体子字段需按 source_field=allianceinfo、json_path=$.xxx 维护。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["联盟信息"],
        "example_values": ["allianceId", "allianceName", "allianceLevel"],
    },
    {
        "table_name": "event",
        "field_name": "abtest",
        "field_comment": "AB 实验信息 JSON 文本；实验分组分析的具体子字段需按 source_field=abtest、json_path=$.xxx 维护。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["AB实验", "实验分组"],
        "example_values": ["group", "experimentId"],
    },
    {
        "table_name": "event",
        "field_name": "remain",
        "field_comment": "事件行中的留存相关 JSON 文本；具体留存标记子字段需按 source_field=remain、json_path=$.xxx 维护。",
        "field_role": "retention_json",
        "semantic_type": "json",
        "aliases": ["留存信息"],
        "example_values": ["remain1", "remain3", "remain7"],
    },
    {
        "table_name": "event",
        "field_name": "level",
        "field_comment": "事件行中的等级相关 JSON 文本；等级拆分子字段需按 source_field=level、json_path=$.xxx 维护。",
        "field_role": "state_json",
        "semantic_type": "json",
        "aliases": ["等级信息"],
        "example_values": ["level", "blevel"],
    },
    {
        "table_name": "event",
        "field_name": "pay",
        "field_comment": "事件行中的付费相关 JSON 文本；付费金额、订单、商品等子字段需按 source_field=pay、json_path=$.xxx 维护。",
        "field_role": "payment_json",
        "semantic_type": "json",
        "aliases": ["付费信息"],
        "example_values": ["paytotal", "pay1", "orderId", "productId"],
    },
    {
        "table_name": "event",
        "field_name": "currentinfo",
        "field_comment": "事件发生时当前状态 JSON 文本；当前等级、战力、资源等子字段需按 source_field=currentinfo、json_path=$.xxx 维护。",
        "field_role": "state_json",
        "semantic_type": "json",
        "aliases": ["当前状态"],
        "example_values": ["level", "power", "resource"],
    },
    {
        "table_name": "event",
        "field_name": "sdkinfo",
        "field_comment": "SDK/客户端上下文 JSON 文本；渠道、平台、版本等子字段需按 source_field=sdkinfo、json_path=$.xxx 维护。",
        "field_role": "dimension_json",
        "semantic_type": "json",
        "aliases": ["SDK信息"],
        "example_values": ["platform", "channel", "version"],
    },
    {
        "table_name": "event",
        "field_name": "personal",
        "field_comment": "事件业务载荷 JSON 文本；交易、CCU、建筑与出征的已验证子字段都在 personal。",
        "field_role": "event_params_json",
        "semantic_type": "json",
        "aliases": ["个人参数", "个人信息"],
        "example_values": ["money", "orderId", "productid", "ed_ccu", "ed_buildingId", "ed_mainBuildingLevel", "ed_myTeamBattlePower", "ed_changeFree", "ed_changePaid"],
    },
    {
        "table_name": "event",
        "field_name": "ext",
        "field_comment": "扩展参数 JSON；当前采样未验证可用于交易、CCU、建筑、出征或加速指标的 ext 子字段。",
        "field_role": "event_params_json",
        "semantic_type": "json",
        "aliases": ["事件参数", "扩展参数"],
        "example_values": [],
        "ai_notes": "不要把 ext 子字段作为当前已验证交易、CCU、建筑、出征或加速口径；需要新字段时先按事件抽样并配置对应路径。",
    },
    {
        "table_name": "event",
        "field_name": "personal.ed_ccu",
        "field_comment": "CCU 事件中的实时在线人数值；实时在线人数取该字段最大值或最新值，不按 CCU 事件条数统计。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["在线人数", "CCU人数"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_ccu'))",
        "example_values": ["1234"],
        "ai_notes": "仅在 event='CCU' 时作为在线人数使用；没有该字段时应提示数据缺失。",
    },
    {
        "table_name": "event",
        "field_name": "personal.ed_changeFree",
        "field_comment": "GoldChange 事件中的免费钻石变化量；正数计免费钻石获取，负数取绝对值计免费钻石消耗。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["免费钻石变化", "免费钻石增减"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_changeFree'))",
        "example_values": ["100", "-50"],
        "ai_notes": "钻石消耗获取情况需要与付费钻石分列展示，不要从 ext.ed_changeFree 读取。",
    },
    {
        "table_name": "event",
        "field_name": "personal.ed_changePaid",
        "field_comment": "GoldChange 事件中的付费钻石变化量；正数计付费钻石获取，负数取绝对值计付费钻石消耗。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["付费钻石变化", "付费钻石增减"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_changePaid'))",
        "example_values": ["100", "-50"],
        "ai_notes": "钻石消耗获取情况需要与免费钻石分列展示，不要从 ext.ed_changePaid 读取。",
    },
    {
        "table_name": "event",
        "field_name": "personal.ed_route",
        "field_comment": "资源变化或功能行为的入口/路径；钻石获取消耗途径优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["路径", "来源途径", "消耗途径"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_route'))",
        "example_values": ["shop", "task", "building"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_detailReason",
        "field_comment": "资源变化或加速使用的详细原因；当 ed_route 缺失时可作为途径/加速类型的回退维度。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["详细原因", "原因", "加速类型"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_detailReason'))",
        "example_values": ["speedup", "reward", "consume"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_mainBuildingLevel",
        "field_comment": "事件发生时的主城等级；活动等级段、出征胜率和主城等级相关事件拆分使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "number",
        "aliases": ["主城等级", "基地等级", "建筑主等级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_mainBuildingLevel'))",
        "example_values": ["1", "10", "20"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_buildingId",
        "field_comment": "建筑升级事件中的建筑 ID；各建筑升级次数优先使用该字段拆分。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["建筑ID", "建筑"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_buildingId'))",
        "example_values": ["main_city", "barrack"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_metaId",
        "field_comment": "事件中的配置 ID；建筑 ID 缺失时作为建筑或配置对象的回退标识。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["配置ID", "MetaID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_metaId'))",
        "example_values": ["building_001"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_heroId",
        "field_comment": "英雄/将领 ID；英雄养成和将领出征指标优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["英雄ID", "将领ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_heroId'))",
        "example_values": ["hero_1001"],
    },
    {
        "table_name": "event",
        "field_name": "ext.captainId",
        "field_comment": "出征/战斗事件中的队长或将领 ID；ed_heroId 缺失时作为将领 ID 回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["队长ID", "将领ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.captainId'))",
        "example_values": ["hero_1001"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_currentLevel",
        "field_comment": "英雄养成事件中的当前等级；SSR 英雄等级分布优先读取该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["当前英雄等级", "英雄当前等级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_currentLevel'))",
        "example_values": ["10", "20"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_heroLevel",
        "field_comment": "英雄等级字段；当 ed_currentLevel 缺失时作为英雄等级回退字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["英雄等级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_heroLevel'))",
        "example_values": ["10", "20"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_heroStar",
        "field_comment": "英雄当前星级；SSR 英雄等级分布和升星分析优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["英雄星级", "将领星级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_heroStar'))",
        "example_values": ["SSR", "5"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_newStar",
        "field_comment": "英雄升星后的新星级；ed_heroStar 缺失时作为英雄星级回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["新星级", "升星后星级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_newStar'))",
        "example_values": ["5", "6"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_newArmyId",
        "field_comment": "兵种升级后的兵种 ID；兵种升级、招募和兵种分布优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["新兵种ID", "兵种"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_newArmyId'))",
        "example_values": ["army_1"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_oldArmyId",
        "field_comment": "兵种升级前的兵种 ID；ed_newArmyId 缺失时作为兵种回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["旧兵种ID", "兵种"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_oldArmyId'))",
        "example_values": ["army_0"],
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_count",
        "field_comment": "兵种招募或升级相关数量；各兵种招募总数量使用该字段求和。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["数量", "招募数量"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_count'))",
        "example_values": ["10", "100"],
    },
    {
        "table_name": "event",
        "field_name": "ext.battleResult",
        "field_comment": "战斗结果字段；出征/竞技胜率优先读取该字段，win/success/1/胜利 计为胜利。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["战斗结果", "胜负结果"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.battleResult'))",
        "example_values": ["win", "lose", "success", "1", "胜利"],
        "ai_notes": "用于胜率时分母是出征/竞技事件行，不是参与用户数。",
    },
    {
        "table_name": "event",
        "field_name": "ext.expeditionDungeonResult",
        "field_comment": "远征/副本结果字段；battleResult 缺失时作为出征胜率回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["远征结果", "副本结果"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.expeditionDungeonResult'))",
        "example_values": ["win", "lose", "success", "1", "胜利"],
    },
    {
        "table_name": "event",
        "field_name": "ext.combatPower",
        "field_comment": "出征/竞技事件中的战力；平均战力优先读取该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["战力", "出征战力"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.combatPower'))",
        "example_values": ["123456"],
    },
    {
        "table_name": "event",
        "field_name": "ext.captainPower",
        "field_comment": "出征/竞技事件中的队长战力；combatPower 缺失时作为平均战力回退字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["队长战力", "将领战力"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.captainPower'))",
        "example_values": ["123456"],
    },
    {
        "table_name": "event",
        "field_name": "ext.payId",
        "field_comment": "付费事件中的商品/礼包 ID；礼包购买结构和商品分布优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["商品ID", "礼包ID", "付费ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.payId'))",
        "example_values": ["starter_pack", "month_card"],
    },
    {
        "table_name": "event",
        "field_name": "ext.rechargeId",
        "field_comment": "付费事件中的充值配置 ID；payId 缺失时作为商品/礼包标识回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["充值ID", "商品ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.rechargeId'))",
        "example_values": ["recharge_001"],
    },
    {
        "table_name": "event",
        "field_name": "ext.productId",
        "field_comment": "付费事件中的产品 ID；payId/rechargeId 缺失时作为商品/礼包标识回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["产品ID", "商品ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.productId'))",
        "example_values": ["product_001"],
    },
    {
        "table_name": "event",
        "field_name": "ext.goodsId",
        "field_comment": "付费事件中的商品 ID；作为商品/礼包标识的末级回退字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "identifier",
        "aliases": ["货品ID", "商品ID"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.goodsId'))",
        "example_values": ["goods_001"],
    },
    {
        "table_name": "user",
        "field_name": "uid",
        "field_comment": "用户唯一 ID；用户快照表内的用户主体。",
        "field_role": "subject_id",
        "semantic_type": "identifier",
        "aliases": ["用户ID", "账号ID", "玩家ID"],
        "required": True,
    },
    {
        "table_name": "user",
        "field_name": "dt",
        "field_comment": "用户快照业务日期，格式 yyyyMMdd。flam 持久看板以 CURDATE() 前一日派生最近完整 dt 窗口，当前快照默认取最近完整分区。",
        "field_role": "snapshot_date",
        "semantic_type": "date",
        "aliases": ["快照日期", "业务日期"],
        "required": True,
    },
    {
        "table_name": "user",
        "field_name": "userinfo",
        "field_comment": "用户基础信息 JSON；新增 cohort 使用 userinfo.regdate。",
        "field_role": "profile_json",
        "semantic_type": "json",
        "aliases": ["用户信息", "注册信息"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.regdate'))",
        "example_values": ["regdate", "regtime", "_platformType", "_serverId"],
    },
    {
        "table_name": "user",
        "field_name": "userinfo.country",
        "field_comment": "用户快照中的国家/地区代码；新增 cohort、用户快照和累计状态按国家拆分时使用。",
        "field_role": "json_path_dimension",
        "semantic_type": "country_code",
        "aliases": ["国家", "地区", "国家地区"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(userinfo, '$.country'))",
        "example_values": ["US", "BR", "GB", "HK"],
        "ai_notes": "快照类指标可从 user.userinfo.country 取国家；事件类指标优先使用 event.userinfo.country。",
    },
    {
        "table_name": "user",
        "field_name": "lastinfo",
        "field_comment": "用户最近状态 JSON；当前等级、主城等级、注册天数等快照状态从这里读取。",
        "field_role": "snapshot_state_json",
        "semantic_type": "json",
        "aliases": ["最近状态", "用户状态"],
        "example_values": ["level", "blevel", "regnday", "lastlogin"],
        "ai_notes": "当前态分布和主城升级漏斗使用最新快照的 lastinfo.level/blevel，不要合并最近 30 天快照。",
    },
    {
        "table_name": "user",
        "field_name": "lastinfo.level",
        "field_comment": "用户最新角色等级；当前等级分布使用最新 user.dt 快照的该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "number",
        "aliases": ["角色等级", "当前等级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(lastinfo, '$.level'))",
        "example_values": ["1", "10", "20"],
        "ai_notes": "当前等级分布只取当前日前一完整 user.dt 分区并过滤 prod=110000038，不要把多天快照合并，也不要先扫大表取 MAX(dt)。",
    },
    {
        "table_name": "user",
        "field_name": "lastinfo.blevel",
        "field_comment": "用户最新主城等级；主城平均等级、主城等级分布和主城升级漏斗使用最新 user.dt 快照的该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "number",
        "aliases": ["主城等级", "基地等级"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(lastinfo, '$.blevel'))",
        "example_values": ["1", "5", "10", "20"],
        "ai_notes": "主城当前态指标必须使用最新快照，不要用升级事件次数替代玩家数。",
    },
    {
        "table_name": "user",
        "field_name": "lastinfo.regnday",
        "field_comment": "用户注册后天数；活跃生命周期分层使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "number",
        "aliases": ["注册天数", "生命周期天数"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(lastinfo, '$.regnday'))",
        "example_values": ["1", "7", "30"],
    },
    {
        "table_name": "user",
        "field_name": "pay",
        "field_comment": "用户付费累计与付费次数 JSON；paytotal 为截至 dt 的累计付费快照，pay1/pay2/pay3/pay7/pay14/pay30 为注册第 1/2/3/7/14/30 个自然日累计付费窗口，注册日算第 1 日。",
        "field_role": "payment_json",
        "semantic_type": "json",
        "aliases": ["付费信息", "累计付费"],
        "example_values": ["paytotal", "pay1", "pay2", "pay3", "pay7", "pay14", "pay30", "firstpaytime", "lastpaytime"],
        "ai_notes": "新增 LTV 按成熟快照读取：pay1 读注册日(+0)，pay2 读注册后第 1 天(+1)，pay3 读注册后第 2 天(+2)，pay7 读注册后第 6 天(+6)，pay14 读注册后第 13 天(+13)，pay30 读注册后第 29 天(+29)；首日/1日 LTV 才是 pay1，次日/2日 LTV 是 pay2。不要把字段数字当 DATE_ADD 偏移。日付费金额用 paytotal 相邻快照差分。",
    },
    {
        "table_name": "user",
        "field_name": "pay.paytotal",
        "field_comment": "用户截至当前快照 dt 的累计付费金额；累计付费、周累充分布和最新累计分布使用该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["累计付费金额", "总付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.paytotal'))",
        "example_values": ["0", "99.99", "1000"],
        "ai_notes": "日付费金额不能直接按日汇总 paytotal，应按 uid 相邻快照差分；周累充分布先取周内用户最新快照。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay1",
        "field_comment": "注册第 1 个自然日（注册日/首日）累计付费窗口字段；新增首日或 1 日 LTV 固定取注册日快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["首日付费", "当日LTV", "首日LTV", "1日LTV", "D0 LTV"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay1'))",
        "example_values": ["0", "9.99"],
        "ai_notes": "用于首日/1 日 LTV 时，快照条件必须是 s.dt = cohort_dt；不要写 DATE_ADD(cohort_dt, INTERVAL 1 DAY)，也不要从后续快照 MAX(pay1) 推导首日付费。用户说“次日 LTV”时不要用 pay1，应使用 pay2。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay2",
        "field_comment": "注册第 2 个自然日累计付费窗口字段；次日/2 日 LTV 读取注册后第 1 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["次日LTV", "2日LTV", "D1 LTV", "D2累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay2'))",
        "example_values": ["0", "19.99"],
        "ai_notes": "pay2 是注册第 2 个自然日累计窗口；用于次日 LTV / 2 日 LTV，读取快照偏移为 cohort_dt + 1。不要把“次日 LTV”错绑到 pay1。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay3",
        "field_comment": "注册第 3 个自然日累计付费窗口字段；3 日 LTV 读取注册后第 2 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["3日LTV", "D3累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay3'))",
        "example_values": ["0", "29.99"],
        "ai_notes": "用于 3 日 LTV 时，快照偏移必须是 cohort_dt + 2；不要写 DATE_ADD(cohort_dt, INTERVAL 3 DAY)。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay7",
        "field_comment": "注册第 7 个自然日累计付费窗口字段；7 日 LTV 和渠道 7 日累计付费读取注册后第 6 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["7日LTV", "D7累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay7'))",
        "example_values": ["0", "49.99"],
        "ai_notes": "用于 7 日 LTV 时，快照偏移必须是 cohort_dt + 6；不要写 DATE_ADD(cohort_dt, INTERVAL 7 DAY)。只展示 D7 已成熟 cohort，不要把未成熟 cohort 当 0。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay14",
        "field_comment": "注册第 14 个自然日累计付费窗口字段；14 日 LTV 读取注册后第 13 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["14日LTV", "D14累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay14'))",
        "example_values": ["0", "79.99"],
        "ai_notes": "用于 14 日 LTV 时，快照偏移必须是 cohort_dt + 13；不要写 DATE_ADD(cohort_dt, INTERVAL 14 DAY)。只展示 D14 已成熟 cohort，不要把未成熟 cohort 当 0。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay30",
        "field_comment": "注册第 30 个自然日累计付费窗口字段；30 日 LTV 读取注册后第 29 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["30日LTV", "D30累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay30'))",
        "example_values": ["0", "129.99"],
        "ai_notes": "用于 30 日 LTV 时，快照偏移必须是 cohort_dt + 29；不要写 DATE_ADD(cohort_dt, INTERVAL 30 DAY)。只展示 D30 已成熟 cohort，不要把未成熟 cohort 当 0。",
    },
    {
        "table_name": "user",
        "field_name": "remain",
        "field_comment": "用户留存标记 JSON；remain1/remain3/remain7 表示对应注册后第 N 日留存状态，需在注册后精确第 N 日快照读取。",
        "field_role": "retention_json",
        "semantic_type": "json",
        "aliases": ["留存", "留存标记"],
        "example_values": ["remain1", "remain3", "remain7", "remain30"],
        "ai_notes": "D1 留存分母是注册日 cohort，分子在注册后第 1 日快照读取 remain1='1'；不要读取注册日 remain1，也不要跨多天 MAX(remain1)。",
    },
    {
        "table_name": "user",
        "field_name": "remain.remain1",
        "field_comment": "注册后第 1 日留存标记；D1 留存分子必须在注册日 +1 的精确快照读取 remain1='1'。",
        "field_role": "json_path_flag",
        "semantic_type": "boolean_flag",
        "aliases": ["次日留存", "D1留存"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(remain, '$.remain1'))",
        "example_values": ["0", "1"],
    },
    {
        "table_name": "user",
        "field_name": "remain.remain3",
        "field_comment": "注册后第 3 日留存标记；D3 留存分子必须在注册日 +3 的精确快照读取 remain3='1'。",
        "field_role": "json_path_flag",
        "semantic_type": "boolean_flag",
        "aliases": ["3日留存", "D3留存"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(remain, '$.remain3'))",
        "example_values": ["0", "1"],
    },
    {
        "table_name": "user",
        "field_name": "remain.remain7",
        "field_comment": "注册后第 7 日留存标记；D7 留存分子必须在注册日 +7 的精确快照读取 remain7='1'。",
        "field_role": "json_path_flag",
        "semantic_type": "boolean_flag",
        "aliases": ["7日留存", "D7留存"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(remain, '$.remain7'))",
        "example_values": ["0", "1"],
        "ai_notes": "D7 留存只展示已成熟 cohort。",
    },
    {
        "table_name": "user",
        "field_name": "adinfo",
        "field_comment": "用户注册归因 JSON；新增和 cohort 归因优先取注册日行的 mediaSource，其次 campaignName。",
        "field_role": "attribution_json",
        "semantic_type": "json",
        "aliases": ["注册渠道", "广告归因"],
        "expression": "COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(adinfo, '$.mediaSource')), ''), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(adinfo, '$.campaignName')), ''), '未知')",
        "example_values": ["mediaSource", "campaignName"],
    },
]


# These historical ext mappings were sampled empty for their target events.
# Keep the literal declarations above only so old seed revisions remain easy to
# identify; remove them before every upsert and delete them from the tenant.
LEGACY_UNVERIFIED_EXT_FIELDS = frozenset(
    {
        "ext.ed_changeFree",
        "ext.ed_changePaid",
        "ext.ed_route",
        "ext.ed_ccu",
        "ext.ed_detailReason",
        "ext.ed_mainBuildingLevel",
        "ext.ed_buildingId",
        "ext.ed_metaId",
        "ext.ed_heroId",
        "ext.captainId",
        "ext.ed_currentLevel",
        "ext.ed_heroLevel",
        "ext.ed_heroStar",
        "ext.ed_newStar",
        "ext.ed_newArmyId",
        "ext.ed_oldArmyId",
        "ext.ed_count",
        "ext.battleResult",
        "ext.expeditionDungeonResult",
        "ext.combatPower",
        "ext.captainPower",
        "ext.payId",
        "ext.rechargeId",
        "ext.productId",
        "ext.goodsId",
    }
)

FIELDS = [item for item in FIELDS if item["field_name"] not in LEGACY_UNVERIFIED_EXT_FIELDS]
FIELDS.extend(
    [
        {
            "table_name": "event",
            "field_name": "personal.money",
            "field_comment": "ServerPayLog 的真实充值金额；金额单位/币种待业务确认，不可未经确认称为净收入。",
            "field_role": "json_path_metric",
            "semantic_type": "number",
            "aliases": ["充值金额", "付费金额", "交易金额"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.money'))",
            "example_values": ["0.99", "9.99", "99.99"],
            "ai_notes": "仅在 event='ServerPayLog' 时使用；日充值金额、ARPU、ARPPU 和付费率都以此字段为交易分子。",
        },
        {
            "table_name": "event",
            "field_name": "personal.orderId",
            "field_comment": "ServerPayLog 的真实交易订单 ID；充值次数可按该字段去重。",
            "field_role": "json_path_dimension",
            "semantic_type": "identifier",
            "aliases": ["订单ID", "交易订单", "充值订单"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.orderId'))",
            "ai_notes": "仅在 event='ServerPayLog' 时作为真实订单使用；不同支付流程事件的同名字段不能直接关联。",
        },
        {
            "table_name": "event",
            "field_name": "personal.productid",
            "field_comment": "ServerPayLog 的礼包/商品 ID；礼包购买结构只使用该字段。",
            "field_role": "json_path_dimension",
            "semantic_type": "identifier",
            "aliases": ["商品ID", "礼包ID", "充值商品"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.productid'))",
            "ai_notes": "只适用于 ServerPayLog；未验证支付流程事件的商品字段不做回退映射。",
        },
        {
            "table_name": "event",
            "field_name": "personal.ed_mainBuildingLevel",
            "field_comment": "建筑和出征事件中的主城等级。",
            "field_role": "json_path_dimension",
            "semantic_type": "number",
            "aliases": ["主城等级", "基地等级", "建筑主等级"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_mainBuildingLevel'))",
            "example_values": ["1", "10", "20"],
        },
        {
            "table_name": "event",
            "field_name": "personal.ed_buildingId",
            "field_comment": "BuildingUpgrade 事件中的建筑 ID。",
            "field_role": "json_path_dimension",
            "semantic_type": "identifier",
            "aliases": ["建筑ID", "建筑"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_buildingId'))",
        },
        {
            "table_name": "event",
            "field_name": "personal.ed_metaId",
            "field_comment": "建筑事件中的配置 ID；建筑 ID 缺失时的已验证回退标识。",
            "field_role": "json_path_dimension",
            "semantic_type": "identifier",
            "aliases": ["配置ID", "MetaID"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_metaId'))",
        },
        {
            "table_name": "event",
            "field_name": "personal.ed_myTeamBattlePower",
            "field_comment": "WorldMarch/WorldMarchRet 中的出征队伍战力。",
            "field_role": "json_path_metric",
            "semantic_type": "number",
            "aliases": ["战力", "出征战力", "队伍战力"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(personal, '$.ed_myTeamBattlePower'))",
        },
        {
            "table_name": "user",
            "field_name": "pay.firstpaytime",
            "field_comment": "用户首付毫秒时间戳；日新增充值用户按该字段转换的首付业务日统计。",
            "field_role": "json_path_timestamp_ms",
            "semantic_type": "timestamp_ms",
            "aliases": ["首付时间", "首次充值时间", "新增付费日期"],
            "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.firstpaytime'))",
            "ai_notes": "首付用户使用 firstpaytime > 0；不能用分析窗口内最小支付事件日期替代。",
        },
    ]
)


def _json_path_expr(table_name: str, field_name: str) -> str | None:
    if "." not in field_name:
        return None
    source_field, json_path = field_name.split(".", 1)
    return f"JSON_UNQUOTE(JSON_EXTRACT(`{table_name}`.`{source_field}`, '$.{json_path}'))"


def _apply_json_source_metadata(item: dict) -> None:
    field_name = item["field_name"]
    if "." not in field_name:
        return
    source_field, json_path = field_name.split(".", 1)
    item.setdefault("source_field", source_field)
    item.setdefault("json_path", f"$.{json_path}")


def _dt_date_expr(table_name: str) -> str:
    return f"STR_TO_DATE(CAST(`{table_name}`.`dt` AS CHAR), '%Y%m%d')"


def apply_chart_builder_expressions() -> None:
    """Make tracking fields directly usable by the dashboard SQL builder."""
    for item in FIELDS:
        table_name = item["table_name"]
        field_name = item["field_name"]
        _apply_json_source_metadata(item)
        if field_name == "dt":
            item["expression"] = _dt_date_expr(table_name)
            continue
        if table_name == "event" and field_name == "time":
            item["expression"] = "DATE_ADD(FROM_UNIXTIME(`event`.`time` / 1000), INTERVAL 8 HOUR)"
            continue
        if table_name == "event" and field_name == "adinfo":
            item["expression"] = (
                "COALESCE("
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`event`.`adinfo`, '$.mediaSource')), ''), "
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`event`.`adinfo`, '$.campaignName')), ''), "
                "'未知')"
            )
            continue
        if table_name == "event" and field_name == "deviceinfo":
            item["expression"] = (
                "COALESCE("
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`event`.`deviceinfo`, '$._platform')), ''), "
                "'未知')"
            )
            continue
        if table_name == "user" and field_name == "userinfo":
            item["expression"] = "JSON_UNQUOTE(JSON_EXTRACT(`user`.`userinfo`, '$.regdate'))"
            continue
        if table_name == "user" and field_name == "adinfo":
            item["expression"] = (
                "COALESCE("
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`user`.`adinfo`, '$.mediaSource')), ''), "
                "NULLIF(JSON_UNQUOTE(JSON_EXTRACT(`user`.`adinfo`, '$.campaignName')), ''), "
                "'未知')"
            )
            continue
        json_expr = _json_path_expr(table_name, field_name)
        if json_expr:
            item["expression"] = json_expr


def _snowflake_id() -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from common.utils.snowflake import snowflake

    return int(snowflake.generate_id())


def upsert_config(cur, now: int) -> None:
    cur.execute(
        """
        INSERT INTO public.sys_tenant_tracking_config (
            id, tenant_id, datasource_id, enabled, default_event_table, default_subject_field,
            default_event_name_field, default_event_time_field, field_role_mappings,
            event_name_mappings, sql_rules, notes, create_by, update_by, create_time, update_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, datasource_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            default_event_table = EXCLUDED.default_event_table,
            default_subject_field = EXCLUDED.default_subject_field,
            default_event_name_field = EXCLUDED.default_event_name_field,
            default_event_time_field = EXCLUDED.default_event_time_field,
            field_role_mappings = EXCLUDED.field_role_mappings,
            sql_rules = EXCLUDED.sql_rules,
            notes = EXCLUDED.notes,
            update_by = EXCLUDED.update_by,
            update_time = EXCLUDED.update_time
        """,
        (
            _snowflake_id(),
            TENANT_ID,
            DATASOURCE_ID,
            TRACKING_CONFIG["enabled"],
            TRACKING_CONFIG["default_event_table"],
            TRACKING_CONFIG["default_subject_field"],
            TRACKING_CONFIG["default_event_name_field"],
            TRACKING_CONFIG["default_event_time_field"],
            Jsonb(TRACKING_CONFIG["field_role_mappings"]),
            Jsonb(TRACKING_CONFIG["event_name_mappings"]),
            TRACKING_CONFIG["sql_rules"],
            TRACKING_CONFIG["notes"],
            UPDATE_BY,
            UPDATE_BY,
            now,
            now,
        ),
    )


def validate_event_group_defaults(groups: list[dict], event_name_mappings: list[dict]) -> None:
    known_events: set[str] = set()
    for mapping in event_name_mappings or []:
        if not isinstance(mapping, dict):
            continue
        for key in ("event_name", "eventName", "name", "value"):
            value = str(mapping.get(key) or "").strip()
            if value:
                known_events.add(value)
        for value in mapping.get("events") or []:
            text = str(value or "").strip()
            if text:
                known_events.add(text)
    missing = {
        item["group_key"]: [name for name in item["event_names"] if name not in known_events]
        for item in groups
    }
    missing = {key: names for key, names in missing.items() if names}
    if missing:
        details = "；".join(f"{key}: {', '.join(names)}" for key, names in missing.items())
        raise RuntimeError(f"事件分组默认值引用了字典中不存在的事件：{details}")


def upsert_event_groups(cur, now: int) -> int:
    cur.execute(
        """
        SELECT event_name_mappings
        FROM public.sys_tenant_tracking_config
        WHERE tenant_id = %s AND datasource_id = %s
        """,
        (TENANT_ID, DATASOURCE_ID),
    )
    config_row = cur.fetchone()
    validate_event_group_defaults(EVENT_GROUPS, config_row[0] if config_row else [])
    cur.execute("SELECT to_regclass('public.sys_tenant_tracking_event_group')")
    if not cur.fetchone()[0]:
        raise RuntimeError("缺少事件分组表，请先执行 Alembic 迁移 142trackinggroups。")
    inserted = 0
    for item in EVENT_GROUPS:
        cur.execute(
            """
            INSERT INTO public.sys_tenant_tracking_event_group (
                id, tenant_id, datasource_id, group_key, group_name, description,
                event_names, sort_order, enabled, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, datasource_id, group_key) DO NOTHING
            """,
            (
                _snowflake_id(),
                TENANT_ID,
                DATASOURCE_ID,
                item["group_key"],
                item["group_name"],
                item.get("description"),
                Jsonb(item["event_names"]),
                int(item.get("sort_order", 0)),
                UPDATE_BY,
                UPDATE_BY,
                now,
                now,
            ),
        )
        inserted += int(cur.rowcount or 0)
    return inserted


def upsert_tables(cur, now: int) -> None:
    for item in TABLES:
        cur.execute(
            """
            INSERT INTO public.sys_tenant_tracking_table (
                id, tenant_id, datasource_id, table_name, table_comment, table_role, aliases,
                ai_notes, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, datasource_id, table_name) DO UPDATE SET
                table_comment = EXCLUDED.table_comment,
                table_role = EXCLUDED.table_role,
                aliases = EXCLUDED.aliases,
                ai_notes = EXCLUDED.ai_notes,
                update_by = EXCLUDED.update_by,
                update_time = EXCLUDED.update_time
            """,
            (
                _snowflake_id(),
                TENANT_ID,
                DATASOURCE_ID,
                item["table_name"],
                item["table_comment"],
                item["table_role"],
                Jsonb(item.get("aliases") or []),
                item["ai_notes"],
                UPDATE_BY,
                UPDATE_BY,
                now,
                now,
            ),
        )


def upsert_fields(cur, now: int) -> None:
    for item in FIELDS:
        cur.execute(
            """
            INSERT INTO public.sys_tenant_tracking_field (
                id, tenant_id, datasource_id, table_name, field_name, field_comment, field_role,
                semantic_type, source_field, json_path, aliases, value_mappings, expression, required,
                example_values, ai_notes, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, datasource_id, table_name, field_name) DO UPDATE SET
                field_comment = EXCLUDED.field_comment,
                field_role = EXCLUDED.field_role,
                semantic_type = EXCLUDED.semantic_type,
                source_field = EXCLUDED.source_field,
                json_path = EXCLUDED.json_path,
                aliases = EXCLUDED.aliases,
                expression = EXCLUDED.expression,
                required = EXCLUDED.required,
                example_values = EXCLUDED.example_values,
                ai_notes = EXCLUDED.ai_notes,
                update_by = EXCLUDED.update_by,
                update_time = EXCLUDED.update_time
            """,
            (
                _snowflake_id(),
                TENANT_ID,
                DATASOURCE_ID,
                item["table_name"],
                item["field_name"],
                item.get("field_comment"),
                item.get("field_role"),
                item.get("semantic_type"),
                item.get("source_field"),
                item.get("json_path"),
                Jsonb(item.get("aliases") or []),
                Jsonb(item.get("value_mappings")) if item.get("value_mappings") is not None else None,
                item.get("expression"),
                bool(item.get("required", False)),
                Jsonb(item.get("example_values") or []),
                item.get("ai_notes"),
                UPDATE_BY,
                UPDATE_BY,
                now,
                now,
            ),
        )


def delete_stale_fields(cur) -> int:
    cur.execute(
        """
        DELETE FROM public.sys_tenant_tracking_field
        WHERE tenant_id = %s
          AND datasource_id = %s
          AND table_name = 'event'
          AND field_name = ANY(%s)
        """,
        (TENANT_ID, DATASOURCE_ID, sorted(LEGACY_UNVERIFIED_EXT_FIELDS)),
    )
    return int(cur.rowcount or 0)


def upsert_schema_comments(cur, now: int) -> tuple[int, int]:
    table_count = 0
    field_count = 0
    for item in TABLES:
        cur.execute(
            """
            INSERT INTO public.sys_tenant_schema_table (
                id, tenant_id, table_name, table_comment, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, table_name) DO UPDATE SET
                table_comment = EXCLUDED.table_comment,
                update_by = EXCLUDED.update_by,
                update_time = EXCLUDED.update_time
            """,
            (
                _snowflake_id(),
                TENANT_ID,
                item["table_name"],
                item["table_comment"],
                UPDATE_BY,
                UPDATE_BY,
                now,
                now,
            ),
        )
        table_count += 1

    for item in FIELDS:
        field_name = item["field_name"]
        if "." in field_name:
            continue
        cur.execute(
            """
            INSERT INTO public.sys_tenant_schema_field (
                id, tenant_id, table_name, field_name, field_comment, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, table_name, field_name) DO UPDATE SET
                field_comment = EXCLUDED.field_comment,
                update_by = EXCLUDED.update_by,
                update_time = EXCLUDED.update_time
            """,
            (
                _snowflake_id(),
                TENANT_ID,
                item["table_name"],
                field_name,
                item.get("field_comment"),
                UPDATE_BY,
                UPDATE_BY,
                now,
                now,
            ),
        )
        field_count += 1
    return table_count, field_count


def main(*, seed_event_groups: bool = False) -> None:
    apply_chart_builder_expressions()
    now = int(time.time())
    schema_tables = 0
    schema_fields = 0
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            upsert_config(cur, now)
            inserted_event_groups = upsert_event_groups(cur, now) if seed_event_groups else 0
            upsert_tables(cur, now)
            upsert_fields(cur, now)
            deleted_stale_fields = delete_stale_fields(cur)
            schema_tables, schema_fields = upsert_schema_comments(cur, now)
        conn.commit()
    print(
        json.dumps(
            {
                "tracking_config": 1,
                "inserted_event_groups": inserted_event_groups,
                "tables": len(TABLES),
                "fields": len(FIELDS),
                "deleted_stale_fields": deleted_stale_fields,
                "schema_tables": schema_tables,
                "schema_fields": schema_fields,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化 First Zombie 工作空间 tracking 元数据。")
    parser.add_argument(
        "--seed-event-groups",
        action="store_true",
        help="显式校验当前事件字典后，仅创建缺失的默认事件分组。",
    )
    args = parser.parse_args()
    main(seed_event_groups=args.seed_event_groups)
