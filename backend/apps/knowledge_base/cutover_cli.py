"""Command-line adapter for knowledge-base cutover operations."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from apps.knowledge_base.cutover_service import (
    KnowledgeCutoverError,
    KnowledgeCutoverService,
)
from common.core.db import engine

ServiceFactory = Callable[..., KnowledgeCutoverService]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知识库 V2 迁移状态检查与切换")
    parser.add_argument(
        "action",
        choices=("status", "verify", "enter-barrier", "activate-v2", "return-legacy"),
    )
    parser.add_argument(
        "--worker",
        action="append",
        default=[],
        metavar="WORKER_ID@QUEUE",
        help="活动发布 Worker；可重复传入",
    )
    parser.add_argument(
        "--compatible-builds-confirmed",
        action="store_true",
        help="确认全部 API 和 Worker 已支持 phase 屏障协议",
    )
    parser.add_argument(
        "--confirm-phase",
        choices=("LEGACY_OPEN", "CUTOVER_BARRIER"),
        help="变更命令必须显式确认预期数据库阶段",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: ServiceFactory = KnowledgeCutoverService,
    session_factory: Callable[[], Session] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        consumers = tuple(_parse_worker(value) for value in args.worker)
        _require_confirmation(args.action, args.confirm_phase)
    except ValueError as exc:
        _print_error("KNOWLEDGE_CUTOVER_ARGUMENT_INVALID", str(exc))
        return 2

    factory = session_factory or (lambda: Session(engine))
    with factory() as session:
        service = service_factory(
            session,
            active_consumers=consumers,
            compatible_builds_confirmed=bool(args.compatible_builds_confirmed),
        )
        try:
            report = getattr(service, args.action.replace("-", "_"))()
        except KnowledgeCutoverError as exc:
            session.rollback()
            _print_error(exc.code, exc.message)
            return 2
        except ProgrammingError:
            session.rollback()
            _print_error(
                "KNOWLEDGE_MIGRATION_SCHEMA_MISSING",
                "数据库尚未执行知识库 V2 结构迁移，请先核对 Alembic 版本并完成备份。",
            )
            return 2
        except Exception:
            session.rollback()
            _print_error(
                "KNOWLEDGE_CUTOVER_FAILED",
                "知识库迁移检查失败，请查看服务端日志并确认数据库连接与迁移版本。",
            )
            return 1

    print(json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=True))
    if args.action == "verify" and not report.ready_for_cutover:
        return 2
    return 0


def _parse_worker(value: str) -> tuple[str, str]:
    worker_id, separator, queue_name = str(value or "").partition("@")
    if not separator or not worker_id.strip() or not queue_name.strip():
        raise ValueError("Worker 参数格式必须为 WORKER_ID@QUEUE。")
    return worker_id.strip(), queue_name.strip()


def _require_confirmation(action: str, confirm_phase: str | None) -> None:
    expected = {
        "enter-barrier": "LEGACY_OPEN",
        "activate-v2": "CUTOVER_BARRIER",
        "return-legacy": "CUTOVER_BARRIER",
    }.get(action)
    if expected and confirm_phase != expected:
        raise ValueError(f"{action} 必须传入 --confirm-phase {expected}。")


def _print_error(code: str, message: str) -> None:
    payload: dict[str, Any] = {
        "ok": False,
        "code": code,
        "message": message,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
