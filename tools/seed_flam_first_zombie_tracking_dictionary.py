# -*- coding: utf-8 -*-
"""Seed flam workspace tracking/event dictionary metadata."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from core_system_db import core_system_db_config
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
DB = core_system_db_config()
UPDATE_BY = 1

LOGIN_EVENTS = [
    "UserActive",
]

PAY_EVENTS = [
    "PayBuyRet",
    "PayBuyRetBenifit",
    "PayBuyRetSandBox",
    "PayFinish",
    "ServerPayLog",
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
    "event_name_mappings": [
        {"metric": "active_user", "events": LOGIN_EVENTS, "description": "DAU/WAU/MAU/活跃拆分使用 UserActive 归一化活跃事件"},
        {"metric": "payment_event", "events": PAY_EVENTS, "description": "充值次数、充值用户、实时付费事件使用的付费事件集合"},
        {"metric": "ccu", "events": ["CCU"], "description": "实时在线人数事件；在线人数读取 ext.ed_ccu"},
        {"metric": "onboarding_funnel", "events": ONBOARDING_EVENTS, "description": "新手引导漏斗事件集合；默认起点仍为 user 注册 cohort，不是全量登录用户"},
        {"metric": "activity_participation", "events": ACTIVITY_EVENTS, "description": "活动参与率、人均参与次数、活动参与频次和活动后续质量使用的活动事件集合"},
        {"metric": "expedition_drill", "events": EXPEDITION_EVENTS, "description": "出征、竞技场、荣耀远征、世界 Boss、联盟 Boss 和演习类看板使用的事件集合"},
        {"metric": "army_upgrade", "events": ARMY_EVENTS, "description": "兵种升级、兵种招募和兵种相关主城成长指标使用的事件"},
        {"metric": "gold_economy", "events": GOLD_EVENTS, "description": "钻石获取、消耗和存量变化使用 GoldChange，并读取 ext.ed_changeFree/ed_changePaid"},
        {"metric": "city_building_upgrade", "events": BUILDING_EVENTS, "description": "主城/建筑升级类指标使用的建筑升级事件集合"},
        {"metric": "technology_upgrade", "events": TECH_EVENTS, "description": "科技升级类指标只使用个人科技升级事件 TechnologyDonation"},
        {"metric": "hero_growth", "events": HERO_EVENTS, "description": "英雄获取、升级、升星、技能升级和招募相关养成指标使用的事件集合"},
    ],
    "sql_rules": "\n".join(
        [
            "flam 近月趋势、成熟 cohort 和当前快照类看板优先用 CURDATE() 生成固定 dt 分区窗口，并过滤 prod=110000038；避免对 ADS 大视图先做 MAX(dt)。",
            "event.time 为毫秒时间戳；实时业务日按 UTC+8 转换，历史离线看板优先使用 dt 分区。",
            "JSON 子字段使用 JSON_UNQUOTE(JSON_EXTRACT(field, '$.path')) 提取，空字符串需要 NULLIF 后再 COALESCE。",
            "活跃用户必须过滤 UserActive 归一化活跃事件后按 uid 去重，不使用 event 全事件去重，也不直接用 user 快照行数代替。",
            "核心看板新手引导漏斗默认以 user 注册日 cohort 为起点，后续步骤按 cohort 内 uid 去重统计。",
            "礼包购买结构使用付费事件集合，并从 ext.payId/rechargeId/productId/goodsId 提取礼包或商品标识。",
            "新增 cohort 使用 user 注册日快照 userinfo.regdate = dt；新增首日付费固定取注册日快照 pay.pay1，不从后续快照取 MAX(pay1)。",
            "留存标记 remain1/remain3/remain7 必须在注册后精确第 1/3/7 日快照读取；未成熟 cohort 不按 0 处理。",
            "付费用户周累充分布必须先按自然周取每个 uid 的最新 user 快照，再按 pay.paytotal 分段，避免多日快照重复计数。",
            "活动参与率分母是同日 UserActive DAU，分子是活动事件 uid 去重；活动后续留存/付费必须先固定参与 cohort。",
            "钻石经济使用 GoldChange，变化量为 ext.ed_changeFree + ext.ed_changePaid；正数计获取，负数绝对值计消耗。",
            "出征和演习胜率分母是出征/竞技事件行，胜利结果读取 ext.battleResult 或 ext.expeditionDungeonResult。",
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
        "ai_notes": "查询特定行为必须先过滤 event，再解析 ext/userinfo/deviceinfo/adinfo/lastinfo 等 JSON 子字段。",
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
        "field_comment": "事件名称/埋点名称；活跃、付费、活动、建筑等指标必须先筛选对应事件集合。",
        "field_role": "event_name",
        "semantic_type": "category",
        "aliases": ["事件名", "埋点名", "行为类型"],
        "value_mappings": TRACKING_CONFIG["event_name_mappings"],
        "required": True,
    },
    {
        "table_name": "event",
        "field_name": "dt",
        "field_comment": "事件业务日期分区，格式 yyyyMMdd。flam 持久历史看板优先用 CURDATE() 派生固定 dt 窗口，避免先扫 event 做 MAX(dt)。",
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
        "field_name": "ext",
        "field_comment": "事件参数 JSON；不同 event 有不同参数结构，必须先按 event 过滤后再解析 ext 子字段。",
        "field_role": "event_params_json",
        "semantic_type": "json",
        "aliases": ["事件参数", "扩展参数"],
        "example_values": [
            "payId",
            "rechargeId",
            "productId",
            "goodsId",
            "ed_ccu",
            "ed_changeFree",
            "ed_changePaid",
            "ed_route",
            "ed_detailReason",
            "ed_mainBuildingLevel",
            "ed_buildingId",
            "ed_metaId",
            "ed_heroId",
            "captainId",
            "ed_currentLevel",
            "ed_heroLevel",
            "ed_heroStar",
            "ed_newStar",
            "ed_newArmyId",
            "ed_oldArmyId",
            "ed_count",
            "battleResult",
            "expeditionDungeonResult",
        ],
        "ai_notes": "礼包购买结构优先用 payId，其次 rechargeId/productId/goodsId；实时在线人数使用 CCU.ext.ed_ccu；钻石经济、出征、主城、英雄和兵种指标都需要先按对应 event 过滤后再解析 ext 子路径。",
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_ccu",
        "field_comment": "CCU 事件中的实时在线人数值；实时在线人数取该字段最大值或最新值，不按 CCU 事件条数统计。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["在线人数", "CCU人数"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_ccu'))",
        "example_values": ["1234"],
        "ai_notes": "仅在 event='CCU' 时作为在线人数使用；没有该字段时应提示数据缺失。",
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_changeFree",
        "field_comment": "GoldChange 事件中的免费钻石变化量；需与 ed_changePaid 相加后判断获取或消耗。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["免费钻石变化", "免费钻石增减"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_changeFree'))",
        "example_values": ["100", "-50"],
        "ai_notes": "钻石经济口径不能只使用该字段，必须和 ed_changePaid 合并。",
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_changePaid",
        "field_comment": "GoldChange 事件中的付费钻石变化量；需与 ed_changeFree 相加后判断获取或消耗。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["付费钻石变化", "付费钻石增减"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_changePaid'))",
        "example_values": ["100", "-50"],
        "ai_notes": "钻石经济口径不能只使用该字段，必须和 ed_changeFree 合并。",
    },
    {
        "table_name": "event",
        "field_name": "ext.ed_route",
        "field_comment": "资源变化、加速或功能行为的入口/路径；钻石获取消耗途径优先使用该字段。",
        "field_role": "json_path_dimension",
        "semantic_type": "category",
        "aliases": ["路径", "来源途径", "消耗途径"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(ext, '$.ed_route'))",
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
        "field_comment": "用户快照业务日期，格式 yyyyMMdd。flam 持久看板优先用 CURDATE() 派生固定 dt 窗口，当前快照默认取当前日前一完整分区。",
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
        "field_comment": "用户付费累计与付费次数 JSON；paytotal 为截至 dt 的累计付费快照，pay1/pay2/pay3/pay7 为注册第 1/2/3/7 个自然日累计付费窗口，注册日算第 1 日。",
        "field_role": "payment_json",
        "semantic_type": "json",
        "aliases": ["付费信息", "累计付费"],
        "example_values": ["paytotal", "pay1", "pay2", "pay3", "pay7", "firstpaytime", "lastpaytime"],
        "ai_notes": "新增 LTV 按成熟快照读取：pay1 读注册日(+0)，pay3 读注册后第 2 天(+2)，pay7 读注册后第 6 天(+6)；不要把字段数字当 DATE_ADD 偏移。日付费金额用 paytotal 相邻快照差分。",
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
        "aliases": ["首日付费", "当日LTV", "1日LTV", "D1 LTV"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay1'))",
        "example_values": ["0", "9.99"],
        "ai_notes": "用于首日/1 日 LTV 时，快照条件必须是 s.dt = cohort_dt；不要写 DATE_ADD(cohort_dt, INTERVAL 1 DAY)，也不要从后续快照 MAX(pay1) 推导首日付费。",
    },
    {
        "table_name": "user",
        "field_name": "pay.pay2",
        "field_comment": "注册第 2 个自然日累计付费窗口字段；如需 2 日 LTV，读取注册后第 1 天快照该字段。",
        "field_role": "json_path_metric",
        "semantic_type": "number",
        "aliases": ["2日LTV", "D2累计付费"],
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(pay, '$.pay2'))",
        "example_values": ["0", "19.99"],
        "ai_notes": "pay2 是 2 日累计窗口，不是常见报表里的首日/1 日 LTV；读取快照偏移为 cohort_dt + 1。",
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


def _snowflake_id() -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from common.utils.snowflake import snowflake

    return int(snowflake.generate_id())


def upsert_config(cur, now: int) -> None:
    cur.execute(
        """
        INSERT INTO public.sys_tenant_tracking_config (
            id, tenant_id, enabled, default_event_table, default_subject_field,
            default_event_name_field, default_event_time_field, field_role_mappings,
            event_name_mappings, sql_rules, notes, create_by, update_by, create_time, update_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            default_event_table = EXCLUDED.default_event_table,
            default_subject_field = EXCLUDED.default_subject_field,
            default_event_name_field = EXCLUDED.default_event_name_field,
            default_event_time_field = EXCLUDED.default_event_time_field,
            field_role_mappings = EXCLUDED.field_role_mappings,
            event_name_mappings = EXCLUDED.event_name_mappings,
            sql_rules = EXCLUDED.sql_rules,
            notes = EXCLUDED.notes,
            update_by = EXCLUDED.update_by,
            update_time = EXCLUDED.update_time
        """,
        (
            _snowflake_id(),
            TENANT_ID,
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


def upsert_tables(cur, now: int) -> None:
    for item in TABLES:
        cur.execute(
            """
            INSERT INTO public.sys_tenant_tracking_table (
                id, tenant_id, table_name, table_comment, table_role, aliases,
                ai_notes, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, table_name) DO UPDATE SET
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
                id, tenant_id, table_name, field_name, field_comment, field_role,
                semantic_type, aliases, value_mappings, expression, required,
                example_values, ai_notes, create_by, update_by, create_time, update_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, table_name, field_name) DO UPDATE SET
                field_comment = EXCLUDED.field_comment,
                field_role = EXCLUDED.field_role,
                semantic_type = EXCLUDED.semantic_type,
                aliases = EXCLUDED.aliases,
                value_mappings = EXCLUDED.value_mappings,
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
                item["table_name"],
                item["field_name"],
                item.get("field_comment"),
                item.get("field_role"),
                item.get("semantic_type"),
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


def main() -> None:
    now = int(time.time())
    schema_tables = 0
    schema_fields = 0
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            upsert_config(cur, now)
            upsert_tables(cur, now)
            upsert_fields(cur, now)
            schema_tables, schema_fields = upsert_schema_comments(cur, now)
        conn.commit()
    print(
        json.dumps(
            {
                "tracking_config": 1,
                "tables": len(TABLES),
                "fields": len(FIELDS),
                "schema_tables": schema_tables,
                "schema_fields": schema_fields,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
