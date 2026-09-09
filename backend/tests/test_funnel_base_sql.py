from apps.dashboard.crud.funnel_base_sql import build_funnel_base_sql, normalize_funnel_builder_context


def _context():
    return {
        "time": {"field": {"value": "event.dt", "table": "event", "field": "dt"}},
        "funnel": {
            "entityField": {"value": "event.uid", "table": "event", "field": "uid"},
            "steps": [
                {"event": {"kind": "tracking-event", "eventTable": "event", "eventNameField": "event", "eventName": "EPSDKLogin"}, "alias": "登录"},
                {"event": {"kind": "tracking-event", "eventTable": "event", "eventNameField": "event", "eventName": "EnterGame"}, "alias": "进入游戏"},
            ],
        },
        "filters": {"logic": "and", "rules": [{"field": {"value": "event.prod", "table": "event", "field": "prod"}, "operator": "eq", "value": 110000039}]},
        "groups": [{"value": "event.channel", "table": "event", "field": "channel"}],
    }


def test_build_funnel_base_sql_from_config():
    plan = build_funnel_base_sql(_context())
    assert plan.tables == ["event"]
    assert "e.`uid` AS entity_id" in plan.sql
    assert "e.`event` IN ('EPSDKLogin', 'EnterGame')" in plan.sql
    assert "e.`dt` >= b.start_dt" in plan.sql
    assert "e.`time` AS event_time" in plan.sql
    assert "e.`dt` AS event_date_key" in plan.sql
    assert "e.`channel` AS `group_1`" in plan.sql
    assert "e.`prod` = 110000039" in plan.sql
    assert plan.steps[1]["alias"] == "进入游戏"


def test_build_funnel_base_sql_rejects_multiple_event_tables():
    context = _context()
    context["funnel"]["steps"][1]["event"]["eventTable"] = "other_event"
    try:
        build_funnel_base_sql(context)
    except ValueError as exc:
        assert "同一事件表" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_build_funnel_base_sql_accepts_saved_tracking_event_values():
    context = _context()
    context["funnel"]["steps"] = [
        {"event": "tracking-event:event.event:EPSDKLogin", "alias": "登录"},
        {"event": "tracking-event:event.event:EnterGame", "alias": "进入"},
    ]
    plan = build_funnel_base_sql(context)
    assert "'EPSDKLogin', 'EnterGame'" in plan.sql


def test_saved_builder_context_is_normalized_for_generation():
    context = normalize_funnel_builder_context({
        "timeField": "dt",
        "funnel": {
            "entityField": "event.uid",
            "steps": [
                {"event": "tracking-event:event.event:EPSDKLogin"},
            ],
        },
        "globalFilters": [],
        "groups": [],
    })
    assert context["time"]["field"] == "dt"
    assert context["funnel"]["entityField"] == "event.uid"


def test_build_funnel_base_sql_preserves_authorized_json_expression():
    context = _context()
    context["groups"] = [{
        "table": "event",
        "field": "userinfo",
        "expression": "JSON_UNQUOTE(JSON_EXTRACT(`event`.`userinfo`, '$.channel'))",
    }]
    plan = build_funnel_base_sql(context)
    assert "JSON_EXTRACT(e.`userinfo`" in plan.sql
