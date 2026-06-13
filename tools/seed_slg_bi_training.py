"""Seed 统一业务口径（术语 + 数据训练 SQL 示例）into the SQLBot 系统库。

- 不修改任何应用代码，只向系统库 terminology / data_training 表插入配置数据。
- 幂等：重复运行不会产生重复记录。
- 目标数据源固定为 core_datasource 中的 'SLG BI Mock'（按名称自动定位 id/oid）。
- 所有 SQL 示例均为只读 SELECT，指标在查询时从明细表计算，符合仓库 AGENTS.md 约束。

运行：
    backend/.venv/Scripts/python.exe tools/seed_slg_bi_training.py
重启后端后即可在「设置 - 术语 / 数据训练」中看到这些记录。
"""
from __future__ import annotations

import datetime

import psycopg
from psycopg.types.json import Jsonb

DB = dict(host="127.0.0.1", port=15432, user="root", password="Password123@pg", dbname="sqlbot")
DATASOURCE_NAME = "SLG BI Mock"


# ---------------------------------------------------------------------------
# 术语口径：word 主词 / synonyms 同义词（用户问题里可能出现）/ description 统一口径定义
# ---------------------------------------------------------------------------
TERMS: list[tuple[str, list[str], str]] = [
    (
        "DAU",
        ["日活", "日活跃用户", "日活跃", "活跃用户数", "活跃用户"],
        "日活跃用户（DAU）口径：某一个自然日内有登录/会话行为的去重玩家数。"
        "标准算法：以 fact_sessions 按 session_start::date 分组，count(DISTINCT player_id)；"
        "观察基准日取 fact_sessions 的最大 session_start 日期，不要用系统当前日期。"
        "WAU/MAU 同口径，分别按最近 7 天 / 30 天去重活跃玩家计算。",
    ),
    (
        "新增用户",
        ["新增", "新注册用户", "新增玩家", "新增注册", "拉新"],
        "新增用户口径：按 dim_player.install_date 统计当日首次安装/注册的去重玩家数。"
        "“最近 N 天新增”指 install_date 落在 [最大 install_date - N + 1, 最大 install_date] 区间的玩家 cohort，"
        "是已经发生的历史新增，不是未来新增；不要和“新增用户的日活”混淆。",
    ),
    (
        "次日留存",
        ["次留", "D1留存", "1日留存", "次日留存率"],
        "次日留存（D1）口径：采用成熟 cohort。分母 = install_date <= 观察最大日期 - 1 的玩家；"
        "分子 = 这些玩家在 lifecycle_day = 1 时于 fact_sessions 有会话/登录行为的去重数。"
        "未满 1 天观察窗口的 cohort 不计入，也不能把缺失当作 0% 留存。",
    ),
    (
        "留存率",
        ["留存", "retention", "N日留存", "Dn留存", "7日留存", "次周留存", "月留存"],
        "Dn 留存口径：成熟 cohort。分母 = install_date <= 观察最大日期 - n 的玩家；"
        "分子 = 这些玩家在 lifecycle_day = n 于 fact_sessions 有活跃行为的去重数；"
        "留存率 = 分子 / 分母。D0 可视为 100% 安装基准，D1 及以后必须从 fact_sessions 行为计算，"
        "样本未成熟时输出“样本未成熟/暂不判断”，不要输出 0% 或全量流失。",
    ),
    (
        "流水",
        ["收入", "营收", "revenue", "付费金额", "充值", "付费收入", "GMV"],
        "收入/流水口径：默认使用净收入 net_revenue_usd（退款订单该字段为 0），从 fact_payments 明细 sum 计算；"
        "如需毛流水用 gross_revenue_usd，退款金额用 refund_amount_usd。"
        "统计收入时按 fact_payments.event_date 落在统计周期内汇总。",
    ),
    (
        "付费用户",
        ["付费玩家", "付费人数", "payer", "付费人群"],
        "付费用户口径：统计周期内在 fact_payments 中 net_revenue_usd > 0 的去重 player_id。"
        "首充用户可用 is_first_pay = true 或 dim_player.first_pay_time 落在周期内判定。",
    ),
    (
        "付费率",
        ["付费转化率", "付费渗透率", "payer rate", "付费占比"],
        "付费率口径：付费用户数 / 活跃（或新增）用户数 × 100%。必须明确分母是活跃用户还是新增用户，"
        "默认用同周期活跃用户（DAU 口径去重）。付费率是非累加比率指标，取值 0~100%，"
        "按维度对比时使用柱状图而非饼图。",
    ),
    (
        "ARPU",
        ["人均收入", "平均每用户收入", "每用户平均收入"],
        "ARPU 口径：统计周期净收入 sum(fact_payments.net_revenue_usd) / 活跃用户数（DAU 口径去重）。"
        "ARPU 为人均值、非累加指标，按维度对比用柱状图，不要用饼图，也不要用总收入替代。",
    ),
    (
        "ARPPU",
        ["付费用户人均收入", "每付费用户收入", "人均付费"],
        "ARPPU 口径：统计周期净收入 / 付费用户数（net_revenue_usd > 0 的去重 player_id）。"
        "ARPPU 为付费人群人均值、非累加指标，按维度对比用柱状图。",
    ),
    (
        "LTV",
        ["生命周期价值", "用户终身价值", "生命周期收入", "长期价值"],
        "LTV 口径：对同一 install cohort，LTV(n) = 该 cohort 截至 lifecycle_day <= n 的累计净收入 / cohort 人数。"
        "累计 LTV 必须随生命周期天数单调不下降；同一条曲线必须使用同一批 cohort 和同一个分母。"
        "若出现 D30 < D7 或增长倍率 < 1，说明口径错误需重写，不能解释为真实业务现象。"
        "需要展示总收入时字段须明确命名为 cumulative_revenue/total_revenue，不要把分组总收入命名为 LTV。",
    ),
    (
        "回流用户",
        ["回流", "流失回归", "召回用户", "回归玩家"],
        "回流用户口径：曾连续 N 天（通常 7 天）无任何 fact_sessions 活跃、随后又重新登录的玩家。"
        "基于 fact_sessions 相邻活跃日期间隔判定，与“新增用户”互斥。",
    ),
    (
        "活跃用户分层",
        ["活跃分层", "活跃度分层", "activity segment"],
        "活跃分层使用 dim_player.activity_segment；付费分层使用 dim_player.payer_segment。"
        "做人群结构分析时优先复用这两个已有分层字段，不要临时自定义阈值。",
    ),
]


# ---------------------------------------------------------------------------
# 数据训练 SQL 示例：question 示例问法 / answer 口径说明 + 标准 SQL
# 全部为只读 SELECT，指标在查询时从明细表计算（符合 AGENTS.md）。
# ---------------------------------------------------------------------------
EXAMPLES: list[tuple[str, str]] = [
    (
        "最近30天每日DAU趋势",
        "DAU = 每个自然日 fact_sessions 去重活跃玩家。观察基准日取 fact_sessions 最大日期。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions)\n"
        "SELECT s.session_start::date AS stat_date,\n"
        "       count(DISTINCT s.player_id) AS dau\n"
        "FROM fact_sessions s CROSS JOIN obs\n"
        "WHERE s.session_start::date > obs.max_date - 30\n"
        "GROUP BY 1 ORDER BY 1;\n"
        "```",
    ),
    (
        "最近7天每日新增用户",
        "新增用户按 dim_player.install_date 统计，基准日取最大 install_date。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(install_date) AS max_date FROM dim_player)\n"
        "SELECT p.install_date AS stat_date,\n"
        "       count(*) AS new_users\n"
        "FROM dim_player p CROSS JOIN obs\n"
        "WHERE p.install_date > obs.max_date - 7\n"
        "GROUP BY 1 ORDER BY 1;\n"
        "```",
    ),
    (
        "新增用户的次日/3日/7日/14日/30日留存率",
        "成熟 cohort 留存：每个 Dn 的分母只含 install_date <= 观察最大日期 - n 的玩家，"
        "分子是这些玩家在 lifecycle_day = n 于 fact_sessions 活跃的去重数。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions),\n"
        "days(n) AS (VALUES (1),(3),(7),(14),(30)),\n"
        "base AS (\n"
        "  SELECT d.n,\n"
        "         count(DISTINCT p.player_id) AS cohort_size,\n"
        "         count(DISTINCT s.player_id) AS retained_users\n"
        "  FROM days d\n"
        "  CROSS JOIN obs\n"
        "  JOIN dim_player p ON p.install_date <= obs.max_date - d.n\n"
        "  LEFT JOIN fact_sessions s\n"
        "    ON s.player_id = p.player_id AND s.lifecycle_day = d.n\n"
        "  GROUP BY d.n\n"
        ")\n"
        "SELECT 'D' || n AS lifecycle_day, n AS day_index,\n"
        "       cohort_size, retained_users,\n"
        "       round(retained_users::numeric / nullif(cohort_size,0) * 100, 2) AS retention_pct\n"
        "FROM base ORDER BY n;\n"
        "```",
    ),
    (
        "最近30天总流水、ARPU、ARPPU和付费率",
        "收入用 net_revenue_usd；活跃用户用 fact_sessions 去重；付费用户用 net_revenue_usd>0 去重。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(session_start::date) AS max_date FROM fact_sessions),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "active AS (\n"
        "  SELECT count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s CROSS JOIN win\n"
        "  WHERE s.session_start::date BETWEEN win.start_date AND win.max_date\n"
        "),\n"
        "pay AS (\n"
        "  SELECT count(DISTINCT player_id) FILTER (WHERE net_revenue_usd > 0) AS payers,\n"
        "         coalesce(sum(net_revenue_usd), 0) AS revenue\n"
        "  FROM fact_payments p CROSS JOIN win\n"
        "  WHERE p.event_date BETWEEN win.start_date AND win.max_date\n"
        ")\n"
        "SELECT a.active_users, p.payers, round(p.revenue, 2) AS revenue,\n"
        "       round(p.revenue / nullif(a.active_users,0), 4) AS arpu,\n"
        "       round(p.revenue / nullif(p.payers,0), 4) AS arppu,\n"
        "       round(p.payers::numeric / nullif(a.active_users,0) * 100, 2) AS payer_rate_pct\n"
        "FROM active a CROSS JOIN pay p;\n"
        "```",
    ),
    (
        "最近30天各渠道的付费率、ARPPU和收入对比",
        "按 dim_player.channel 分组，活跃来自 fact_sessions，付费来自 fact_payments(net_revenue_usd>0)。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs),\n"
        "act AS (\n"
        "  SELECT p.channel, count(DISTINCT s.player_id) AS active_users\n"
        "  FROM fact_sessions s\n"
        "  JOIN dim_player p ON p.player_id = s.player_id\n"
        "  CROSS JOIN win\n"
        "  WHERE s.session_start::date BETWEEN win.start_date AND win.max_date\n"
        "  GROUP BY p.channel\n"
        "),\n"
        "pay AS (\n"
        "  SELECT p.channel,\n"
        "         count(DISTINCT pay.player_id) FILTER (WHERE pay.net_revenue_usd > 0) AS payers,\n"
        "         coalesce(sum(pay.net_revenue_usd), 0) AS revenue\n"
        "  FROM fact_payments pay\n"
        "  JOIN dim_player p ON p.player_id = pay.player_id\n"
        "  CROSS JOIN win\n"
        "  WHERE pay.event_date BETWEEN win.start_date AND win.max_date\n"
        "  GROUP BY p.channel\n"
        ")\n"
        "SELECT a.channel, a.active_users,\n"
        "       coalesce(pay.payers, 0) AS payers,\n"
        "       round(coalesce(pay.revenue, 0), 2) AS revenue,\n"
        "       round(coalesce(pay.revenue, 0) / nullif(pay.payers, 0), 4) AS arppu,\n"
        "       round(coalesce(pay.payers, 0)::numeric / nullif(a.active_users, 0) * 100, 2) AS payer_rate_pct\n"
        "FROM act a LEFT JOIN pay ON pay.channel = a.channel\n"
        "ORDER BY revenue DESC;\n"
        "```",
    ),
    (
        "最近30天新增用户的LTV生命周期曲线",
        "目标 cohort = 最近30天新增；LTV(n) = cohort 截至 lifecycle_day<=n 的累计净收入 / cohort 人数，累计单调不减。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "cohort AS (\n"
        "  SELECT p.player_id\n"
        "  FROM dim_player p CROSS JOIN obs\n"
        "  WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date\n"
        "),\n"
        "days(n) AS (VALUES (0),(1),(3),(7),(14),(30)),\n"
        "rev AS (\n"
        "  SELECT d.n,\n"
        "         (SELECT count(*) FROM cohort) AS cohort_size,\n"
        "         coalesce(sum(pay.net_revenue_usd), 0) AS cumulative_revenue\n"
        "  FROM days d\n"
        "  LEFT JOIN fact_payments pay\n"
        "    ON pay.player_id IN (SELECT player_id FROM cohort)\n"
        "   AND pay.lifecycle_day <= d.n\n"
        "  GROUP BY d.n\n"
        ")\n"
        "SELECT 'D' || n AS lifecycle_day, n AS day_index, cohort_size,\n"
        "       round(cumulative_revenue, 2) AS cumulative_revenue,\n"
        "       round(cumulative_revenue::numeric / nullif(cohort_size, 0), 4) AS cumulative_ltv\n"
        "FROM rev ORDER BY n;\n"
        "```",
    ),
    (
        "最近30天按付费档位的收入构成",
        "使用 fact_payments.revenue_tier 分组，收入用 net_revenue_usd，只统计真实付费订单。\n"
        "```sql\n"
        "WITH obs AS (SELECT max(event_date) AS max_date FROM fact_events),\n"
        "win AS (SELECT (max_date - 29) AS start_date, max_date FROM obs)\n"
        "SELECT p.revenue_tier,\n"
        "       count(*) AS orders,\n"
        "       count(DISTINCT p.player_id) AS payers,\n"
        "       round(sum(p.net_revenue_usd), 2) AS revenue\n"
        "FROM fact_payments p CROSS JOIN win\n"
        "WHERE p.event_date BETWEEN win.start_date AND win.max_date\n"
        "  AND p.net_revenue_usd > 0\n"
        "GROUP BY p.revenue_tier\n"
        "ORDER BY revenue DESC;\n"
        "```",
    ),
]


def main() -> None:
    now = datetime.datetime.now()
    with psycopg.connect(**DB) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, oid FROM core_datasource WHERE name = %s ORDER BY id LIMIT 1", (DATASOURCE_NAME,))
        row = cur.fetchone()
        if not row:
            raise SystemExit(f"未找到数据源 {DATASOURCE_NAME!r}，请确认 core_datasource 已存在该记录。")
        ds_id, oid = row[0], row[1]
        print(f"目标数据源: id={ds_id} oid={oid} name={DATASOURCE_NAME!r}")

        term_added = term_skipped = 0
        for word, synonyms, description in TERMS:
            cur.execute(
                "SELECT id FROM terminology WHERE oid = %s AND pid IS NULL AND word = %s",
                (oid, word),
            )
            if cur.fetchone():
                term_skipped += 1
                continue
            cur.execute(
                """
                INSERT INTO terminology (oid, pid, create_time, word, description, specific_ds, datasource_ids, enabled)
                VALUES (%s, NULL, %s, %s, %s, TRUE, %s, TRUE)
                RETURNING id
                """,
                (oid, now, word, description, Jsonb([ds_id])),
            )
            parent_id = cur.fetchone()[0]
            for syn in synonyms:
                syn = syn.strip()
                if not syn:
                    continue
                cur.execute(
                    """
                    INSERT INTO terminology (oid, pid, create_time, word, description, specific_ds, datasource_ids, enabled)
                    VALUES (%s, %s, %s, %s, NULL, TRUE, %s, TRUE)
                    """,
                    (oid, parent_id, now, syn, Jsonb([ds_id])),
                )
            term_added += 1

        ex_added = ex_skipped = 0
        for question, answer in EXAMPLES:
            cur.execute(
                "SELECT id FROM data_training WHERE oid = %s AND question = %s AND datasource = %s",
                (oid, question, ds_id),
            )
            if cur.fetchone():
                ex_skipped += 1
                continue
            cur.execute(
                """
                INSERT INTO data_training (oid, datasource, create_time, question, description, enabled)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                """,
                (oid, ds_id, now, question, answer),
            )
            ex_added += 1

        conn.commit()
        print(f"术语: 新增 {term_added} 组（含同义词子记录），跳过已存在 {term_skipped} 组")
        print(f"数据训练: 新增 {ex_added} 条，跳过已存在 {ex_skipped} 条")
        cur.execute("SELECT count(*) FROM terminology WHERE oid = %s", (oid,))
        print("terminology 总记录数:", cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM data_training WHERE oid = %s", (oid,))
        print("data_training 总记录数:", cur.fetchone()[0])


if __name__ == "__main__":
    main()
