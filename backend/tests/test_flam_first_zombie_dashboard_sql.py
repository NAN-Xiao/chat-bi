"""First Zombie datasource SQL semantic regression tests."""
from __future__ import annotations

import sys
from pathlib import Path

from apps.knowledge_base.object_sql import extract_sql_object_paths

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_transaction_metrics_only_use_server_pay_log_personal_payload() -> None:
    import flam_first_zombie_dashboard_sql as dashboard

    for sql in (
        dashboard.SQL_DAILY_REVENUE_BASE,
        dashboard.SQL_ARPU_ARPPU,
        dashboard.SQL_PAYMENT_OVERVIEW,
        dashboard.SQL_DAILY_PAY_EVENT_COUNT,
        dashboard.SQL_DAILY_PAY_USERS,
        dashboard.SQL_7D_PAY_RANK,
        dashboard.SQL_CHANNEL_PAY_AMOUNT,
    ):
        assert "e.event = 'ServerPayLog'" in sql
        assert "e.event IN ({PAY_EVENTS})" not in sql

    assert "JSON_EXTRACT(e.personal, '$.money')" in dashboard.SQL_DAILY_REVENUE_BASE
    assert "JSON_EXTRACT(e.personal, '$.orderId')" in dashboard.SQL_DAILY_PAY_EVENT_COUNT
    assert "JSON_EXTRACT(u.pay, '$.firstpaytime')" in dashboard.SQL_DAILY_PAY_USERS
    assert "MIN(e.dt)" not in dashboard.SQL_DAILY_PAY_USERS


def test_ltv_and_retention_sql_excludes_unmature_cohorts() -> None:
    import flam_first_zombie_dashboard_sql as dashboard

    assert "maturity AS" in dashboard.SQL_LTV_7D
    assert "c.d7_dt <= b.data_end_dt" in dashboard.SQL_LTV_7D
    assert "CASE WHEN m.mature_7d" in dashboard.SQL_LTV_7D
    assert "end_dt" in dashboard.SQL_D1_RETENTION
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in dashboard.SQL_D1_RETENTION


def test_historical_sql_uses_complete_business_day_without_max_dt() -> None:
    import flam_first_zombie_active_dashboard_sql as active
    import flam_first_zombie_dashboard_sql as dashboard
    import flam_first_zombie_date_sql as dates
    import flam_first_zombie_remaining_dashboard_sql as remaining

    assert dates.complete_business_date_expr() == "DATE_SUB(CURDATE(), INTERVAL 1 DAY)"
    assert "MAX(dt)" not in dashboard.SQL_PAYMENT_OVERVIEW
    assert "MAX(dt)" not in active.SQL_DAU
    assert "MAX(dt)" not in remaining.SQL_BUILDING_BY_TYPE
    assert "DATE_SUB(CURDATE(), INTERVAL 1 DAY)" in dashboard.SQL_PAYMENT_OVERVIEW


def test_legacy_date_window_repair_cannot_reintroduce_max_dt_scan() -> None:
    repair_script = ROOT / "tools" / "repair_flam_first_zombie_dashboard_date_windows.py"
    content = repair_script.read_text(encoding="utf-8")

    assert "SELECT MAX(dt)" not in content
    assert "complete_business_dt_expr" in content


def test_remaining_views_only_use_verified_payloads_or_explicit_pending_state() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    assert "e.ext" not in remaining.SQL_BUILDING_BY_TYPE
    assert "e.ext" not in remaining.SQL_BUILDING_BY_CITY
    assert "e.ext" not in remaining.SQL_EXPEDITION_AVG_POWER
    assert "JSON_EXTRACT(e.personal, '$.ed_mainBuildingLevel')" in remaining.SQL_BUILDING_BY_CITY
    assert "JSON_EXTRACT(e.personal, '$.ed_myTeamBattlePower')" in remaining.SQL_EXPEDITION_AVG_POWER
    assert "combatPower" not in remaining.EXPEDITION_POWER
    assert "combatPower" not in remaining.SQL_EXPEDITION_AVG_POWER
    assert "待补充字段映射" in remaining.SQL_SPEEDUP
    assert "未验证可用于加速类型的字段" in remaining.SQL_SPEEDUP


def test_expedition_power_is_world_march_only_and_labeled_consistently() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    view = remaining.REMAINING_VIEW_SQL["440303dfdf39408ba86ffb222f3334f2"]

    assert "e.event = 'WorldMarch'" in remaining.SQL_EXPEDITION_AVG_POWER
    assert "WorldMarchRet" not in remaining.SQL_EXPEDITION_AVG_POWER
    assert f"e.event IN ({remaining.EXPEDITION_EVENTS})" not in remaining.SQL_EXPEDITION_AVG_POWER
    assert "AS `出征平均战力`" in remaining.SQL_EXPEDITION_AVG_POWER
    assert view.title == "出征平均战力"
    assert view.fields == ("出征平均战力", "日环比", "周同比")
    assert view.y_axis == ("出征平均战力", "日环比", "周同比")


def test_hero_expedition_sql_uses_static_json_paths() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    for sql in (remaining.SQL_HERO_EXPEDITION_COUNT, remaining.SQL_HERO_WIN_RATE):
        assert "CONCAT('$.ed_myTeamHeroList['" not in sql
        assert "$.ed_myTeamHeroList[0].heroId" in sql
        assert "$.ed_myTeamHeroList[9].heroId" in sql
        extract_sql_object_paths([sql], dialect="mysql")


def test_festival_payment_rate_title_does_not_claim_retention() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    view = remaining.REMAINING_VIEW_SQL["095b1cf41cd64844b1f78f07ceccb7bf"]

    assert view.title == "参与节日活动用户的当日/D7付费率"
    assert "付费留存" not in view.title


def test_activity_retention_uses_daily_participation_cohorts_and_exact_events() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    newbie_sql = remaining.SQL_NEWBIE_ACTIVITY_RETENTION
    festival_sql = remaining.SQL_FESTIVAL_PAY_RETENTION
    mature_cohort_window = (
        f"e.dt BETWEEN {remaining._date_expr(35)} AND {remaining._date_expr(8)}"
    )

    for sql in (newbie_sql, festival_sql):
        assert "SELECT DISTINCT e.uid, e.dt AS participate_dt" in sql
        assert mature_cohort_window in sql
        assert "MIN(e.dt)" not in sql

    assert "e.event = 'UserActive'" in newbie_sql
    assert "a.dt = CAST(" in newbie_sql
    assert "INTERVAL 1 DAY" in newbie_sql
    assert "INTERVAL 7 DAY" in newbie_sql
    assert "`user`" not in newbie_sql
    assert "remain" not in newbie_sql

    assert "e.event = 'ServerPayLog'" in festival_sql
    assert "pay.dt = p.participate_dt" in festival_sql
    assert "INTERVAL 7 DAY" in festival_sql
    assert "`user`" not in festival_sql
    assert "pay1" not in festival_sql
    assert "pay7" not in festival_sql


def test_mature_cohort_windows_cover_the_full_observation_period() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    assert (
        f"WHERE s.first_buy_dt <= {remaining._date_expr(8)}"
        in remaining.SQL_STARTER_PACK_REPURCHASE
    )
    assert (
        f"WHERE s.first_buy_dt <= {remaining._date_expr(7)}"
        not in remaining.SQL_STARTER_PACK_REPURCHASE
    )
    assert (
        f"e.dt BETWEEN {remaining._date_expr(60)} AND {remaining._date_expr(31)}"
        in remaining.SQL_MONTH_CARD_RETENTION
    )
    assert (
        f"e.dt BETWEEN {remaining._date_expr(60)} AND {remaining._date_expr(30)}"
        not in remaining.SQL_MONTH_CARD_RETENTION
    )


def test_payment_process_distribution_is_not_labeled_as_transaction_product() -> None:
    import flam_first_zombie_remaining_dashboard_sql as remaining

    view = remaining.REMAINING_VIEW_SQL["fdb8f135e2644bcb80b7634882809f7e"]
    assert view.title == "支付流程事件分布"
    assert "支付流程事件" in view.fields
    assert f"e.event IN ({remaining.PAYMENT_FLOW_EVENTS})" in view.sql
    assert "JSON_EXTRACT(e.personal, '$.productid')" not in view.sql


def test_realtime_metrics_use_verified_ccu_and_transaction_payloads() -> None:
    from datetime import date

    import repair_flam_first_zombie_realtime_dashboard as realtime

    online_sql = realtime.build_online_sql(date(2026, 7, 10))
    pay_sql = realtime.build_hourly_pay_base_sql(date(2026, 7, 10))

    assert "JSON_EXTRACT(e.personal, '$.ed_ccu')" in online_sql
    assert "JSON_EXTRACT(e.ext, '$.ed_ccu')" not in online_sql
    assert "e.event = 'ServerPayLog'" in pay_sql
    assert "PayBuyRet" not in pay_sql
