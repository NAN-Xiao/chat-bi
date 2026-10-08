"""Explicit, connection-local MySQL timezone control for analytical queries."""
from contextlib import contextmanager
from sqlalchemy import text


@contextmanager
def interval_mysql_time_zone(connection, zones, *, enforce_utc=True):
    if not enforce_utc:
        # Epoch arithmetic and explicit CONVERT_TZ expressions do not depend
        # on the session timezone. Some analytical engines cannot expose/set it.
        for zone in zones:
            converted = connection.execute(text("SELECT CONVERT_TZ('2026-01-01 00:00:00', '+00:00', :zone)"), {"zone": zone}).scalar()
            if converted is None:
                raise ValueError(f"分析查询缺少时区转换能力：{zone}。")
        yield
        return
    original = connection.execute(text("SELECT @@session.time_zone")).scalar()
    try:
        connection.execute(text("SET time_zone = '+00:00'"))
        if connection.execute(text("SELECT @@session.time_zone")).scalar() != "+00:00":
            raise ValueError("间隔查询无法固定数据库会话时区。")
        for zone in zones:
            converted = connection.execute(text("SELECT CONVERT_TZ('2026-01-01 00:00:00', '+00:00', :zone)"), {"zone": zone}).scalar()
            if converted is None:
                raise ValueError(f"间隔查询缺少时区转换能力：{zone}。")
        yield
    finally:
        try:
            connection.execute(text("SET time_zone = :zone"), {"zone": original})
        except Exception:
            connection.invalidate()
            raise
