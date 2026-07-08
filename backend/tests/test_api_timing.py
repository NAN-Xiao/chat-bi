from common.observability import api_timing


def test_log_api_timing_emits_endpoint_context(monkeypatch):
    """
    是什么：接口耗时日志必须包含接口名、租户、用户、业务标识、返回数量和耗时。
    """
    logs: list[str] = []

    monkeypatch.setattr(api_timing.AppLogUtil, "info", lambda message: logs.append(message))
    monkeypatch.setattr(api_timing.time, "perf_counter", lambda: 11.234)

    elapsed_ms = api_timing.log_api_timing(
        "Dashboard SQL preview",
        started_at=10.0,
        tenant_id=2001,
        user_id=1001,
        datasource_id=3,
        row_count=8,
        status="success",
    )

    assert elapsed_ms == 1234
    assert logs == [
        "Dashboard SQL preview finished: tenant_id=2001, user_id=1001, "
        "datasource_id=3, row_count=8, status=success, elapsed_ms=1234"
    ]
