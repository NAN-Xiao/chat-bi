"""
脚本说明：验证 smart_qa 任务用线程池驱动同步生成器，阻塞段不卡事件循环。
"""
from __future__ import annotations

import asyncio
import time

from apps.chat.tasks import _iter_sync_generator


def test_iter_sync_generator_yields_all_chunks() -> None:
    """
    是什么：线程池驱动的迭代必须完整保序地产出所有 chunk。
    """

    def generator():
        yield from ["a", "b", "c"]

    async def collect():
        return [chunk async for chunk in _iter_sync_generator(generator())]

    assert asyncio.run(collect()) == ["a", "b", "c"]


def test_iter_sync_generator_does_not_block_event_loop() -> None:
    """
    是什么：生成器内部的同步阻塞（如 LLM/SQL 等待）不得卡住事件循环，
    否则同循环上其他任务的 Redis 等待会超时。
    """

    def blocking_generator():
        for i in range(3):
            time.sleep(0.15)
            yield i

    ticks = {"count": 0}

    async def ticker(stop: asyncio.Event):
        while not stop.is_set():
            ticks["count"] += 1
            await asyncio.sleep(0.02)

    async def scenario():
        stop = asyncio.Event()
        ticker_task = asyncio.create_task(ticker(stop))
        chunks = [chunk async for chunk in _iter_sync_generator(blocking_generator())]
        stop.set()
        await ticker_task
        return chunks

    chunks = asyncio.run(scenario())
    assert chunks == [0, 1, 2]
    # 生成器共阻塞约 0.45 秒；若事件循环被卡住，ticker 几乎不会走动。
    assert ticks["count"] >= 10
