"""
脚本说明：验证 Redis client 按事件循环隔离，防止连接跨事件循环复用。
"""
from __future__ import annotations

import asyncio

from common.core import redis_client


def test_get_redis_client_reuses_client_within_same_loop() -> None:
    """
    是什么：同一个事件循环内应复用同一个 client 和连接池。
    """

    async def get_twice():
        return redis_client.get_redis_client(), redis_client.get_redis_client()

    first, second = asyncio.run(get_twice())
    assert first is second


def test_get_redis_client_is_isolated_between_loops() -> None:
    """
    是什么：不同事件循环必须拿到各自独立的 client，避免
    "Future attached to a different loop" / "Event loop is closed"。
    """

    async def get_client():
        return redis_client.get_redis_client()

    client_in_loop_a = asyncio.run(get_client())
    client_in_loop_b = asyncio.run(get_client())
    assert client_in_loop_a is not client_in_loop_b


def test_get_redis_client_requires_running_loop() -> None:
    """
    是什么：没有运行中事件循环时应显式报错，而不是悄悄创建无循环归属的连接。
    """
    try:
        redis_client.get_redis_client()
    except RuntimeError:
        return
    raise AssertionError("get_redis_client should require a running event loop")
