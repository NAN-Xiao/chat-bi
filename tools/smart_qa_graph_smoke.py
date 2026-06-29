from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import threading
import time
import urllib.parse
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import MetaData, Table, delete, insert
from sqlmodel import Session, create_engine, text

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_SYSTEM_DB_URL = "postgresql+psycopg://root:Password123%40pg@127.0.0.1:15432/zhishu_bi"
DEFAULT_OUTPUT_DIR = Path(".codex-runtime/smart-qa-graph-smoke")
DEFAULT_CASES: list[dict[str, Any]] = [
    {"name": "line", "source_record_id": 181},
    {"name": "funnel", "source_record_id": 183},
    {"name": "column", "source_record_id": 134},
    {"name": "pie", "source_record_id": 133},
    {"name": "heatmap", "source_record_id": 34},
]
FINISH_STEPS = {
    "generate_sql": 1,
    "query_data": 2,
    "generate_chart": 3,
}
PERMISSION_DENIED_ERROR_TYPE = "permission_denied"
GRAPH_PERMISSION_FIXTURE_FIELD = "net_revenue_usd"
GRAPH_PERMISSION_FIXTURE_TABLE = "fact_payments"
PERMISSION_FIXTURE_COLUMN_DENY = "column_deny"
PERMISSION_FIXTURE_ROW_INVALID = "row_invalid"
PERMISSION_FIXTURES = (
    PERMISSION_FIXTURE_COLUMN_DENY,
    PERMISSION_FIXTURE_ROW_INVALID,
)
DYNAMIC_ASSISTANT_DATASOURCE_ID = 910001
DYNAMIC_ASSISTANT_DATASOURCE_TABLE = "fact_payments"
DYNAMIC_ASSISTANT_DEFAULT_QUESTION = "统计 fact_payments 表的订单数"


def _sse_events(chunk: str):
    for match in re.finditer(r"data:(\{.*?\})(?:\r?\n\r?\n|$)", chunk, flags=re.S):
        try:
            yield json.loads(match.group(1))
        except json.JSONDecodeError:
            continue


def _load_cases(
    system_db_url: str,
    selected_case_names: set[str] | None,
    *,
    datasource: int | None = None,
    question: str | None = None,
) -> list[dict[str, Any]]:
    if question:
        if datasource is None:
            raise ValueError("--datasource is required when --question is provided")
        return [{
            "name": "custom",
            "source_record_id": None,
            "question": question,
            "datasource": datasource,
        }]

    cases = [
        case.copy()
        for case in DEFAULT_CASES
        if selected_case_names is None or case["name"] in selected_case_names
    ]
    if not cases:
        raise ValueError(f"No smoke cases selected. Available cases: {', '.join(case['name'] for case in DEFAULT_CASES)}")

    engine = create_engine(system_db_url)
    with Session(engine) as session:
        for case in cases:
            row = session.exec(
                text(
                    """
                    select question, datasource
                    from chat_record
                    where id = :record_id
                    """
                ),
                params={"record_id": case["source_record_id"]},
            ).first()
            if not row:
                raise RuntimeError(f"source record not found: {case['source_record_id']}")
            case["question"], case["datasource"] = row
    return cases


def _login(base_url: str, username: str, password: str) -> dict[str, str]:
    response = requests.post(
        base_url + "/login/access-token",
        data={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["data"]["access_token"]
    return {"X-ZHISHU-TOKEN": f"Bearer {token}"}


def _load_current_user(system_db_url: str, username: str) -> dict[str, Any]:
    engine = create_engine(system_db_url)
    with Session(engine) as session:
        row = session.exec(
            text(
                """
                select id, account
                from sys_user
                where account = :username
                """
            ),
            params={"username": username},
        ).first()
        if not row:
            raise RuntimeError(f"user not found: {username}")
        return {"id": int(row[0]), "account": row[1]}


def _dynamic_assistant_datasource_payload(datasource_id: int) -> dict[str, Any]:
    return {
        "code": 0,
        "data": [
            {
                "id": int(datasource_id),
                "name": "Codex Dynamic Smoke Datasource",
                "description": "Temporary external datasource for Smart Q&A LangGraph smoke tests.",
                "comment": "Temporary external datasource for Smart Q&A LangGraph smoke tests.",
                "type": "pg",
                "host": "127.0.0.1",
                "port": 5432,
                "dataBase": "slg_bi_mock",
                "user": "postgres",
                "password": "111111",
                "db_schema": "public",
                "tables": [
                    {
                        "id": 1,
                        "name": DYNAMIC_ASSISTANT_DATASOURCE_TABLE,
                        "comment": "Payment order detail table.",
                        "sql": "SELECT order_id FROM fact_payments",
                        "fields": [
                            {"id": 1, "name": "order_id", "type": "bigint", "comment": "Order id."},
                        ],
                    }
                ],
            }
        ],
    }


def _assistant_certificate_header(certificate: list[dict[str, Any]] | None = None) -> str:
    quoted_json = urllib.parse.quote(json.dumps(certificate or [], ensure_ascii=False))
    return base64.b64encode(quoted_json.encode("utf-8")).decode("ascii")


def _table_values(table: Table, values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key in table.c}


@contextmanager
def _dynamic_assistant_datasource_server(datasource_id: int):
    payload = _dynamic_assistant_datasource_payload(datasource_id)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/datasources"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def _temporary_dynamic_assistant_fixture(
    system_db_url: str,
    *,
    base_url: str,
    tenant_id: int,
    user_id: int,
    datasource_id: int,
):
    engine = create_engine(system_db_url)
    metadata = MetaData()
    assistant_table = Table("sys_assistant", metadata, autoload_with=engine)
    assistant_id = int(time.time() * 1000) * 1000 + (int(user_id) % 1000)
    with _dynamic_assistant_datasource_server(datasource_id) as endpoint:
        configuration = {
            "endpoint": endpoint,
            "timeout": 10,
        }
        with engine.begin() as connection:
            connection.execute(
                insert(assistant_table).values(
                    **_table_values(
                        assistant_table,
                        {
                            "id": assistant_id,
                            "tenant_id": int(tenant_id),
                            "name": "codex dynamic assistant smoke",
                            "type": 1,
                            "domain": "http://127.0.0.1",
                            "description": "Temporary assistant created by tools/smart_qa_graph_smoke.py",
                            "configuration": json.dumps(configuration, ensure_ascii=False),
                            "create_time": int(time.time() * 1000),
                            "app_id": None,
                            "app_secret": None,
                            "enable_custom_model": False,
                            "custom_model": None,
                        },
                    )
                )
            )

        try:
            response = requests.get(
                base_url + "/system/assistant/validator",
                params={"id": assistant_id, "virtual": int(user_id)},
                timeout=30,
            )
            response.raise_for_status()
            token = response.json()["data"]["token"]
            yield {
                "X-ZHISHU-ASSISTANT-TOKEN": f"Assistant {token}",
                "X-ZHISHU-ASSISTANT-CERTIFICATE": _assistant_certificate_header(),
            }
        finally:
            with engine.begin() as connection:
                connection.execute(delete(assistant_table).where(assistant_table.c.id == assistant_id))


@contextmanager
def _temporary_graph_column_permission_fixture(
    system_db_url: str,
    *,
    datasource: int,
    tenant_id: int,
    user_id: int,
):
    engine = create_engine(system_db_url)
    metadata = MetaData()
    ds_permission = Table("ds_permission", metadata, autoload_with=engine)
    ds_rules = Table("ds_rules", metadata, autoload_with=engine)
    permission_id = None
    rule_id = None
    with engine.begin() as connection:
        table_row = connection.execute(
            text(
                """
                select t.id as table_id, f.id as field_id, f.field_name, f.field_comment
                from core_table t
                join core_field f on f.table_id = t.id
                where t.ds_id = :datasource
                  and t.table_name = :table_name
                  and f.field_name = :field_name
                """
            ),
            {
                "datasource": datasource,
                "table_name": GRAPH_PERMISSION_FIXTURE_TABLE,
                "field_name": GRAPH_PERMISSION_FIXTURE_FIELD,
            },
        ).mappings().first()
        if table_row is None:
            raise RuntimeError(
                f"Cannot create permission fixture: {GRAPH_PERMISSION_FIXTURE_TABLE}.{GRAPH_PERMISSION_FIXTURE_FIELD} "
                f"not found for datasource {datasource}"
            )

        permission_payload = [{
            "field_id": int(table_row["field_id"]),
            "field_name": table_row["field_name"],
            "field_comment": table_row["field_comment"] or "",
            "enable": False,
        }]
        permission_id = connection.execute(
            insert(ds_permission)
            .values(
                enable=True,
                auth_target_type="user",
                auth_target_id=None,
                type="column",
                ds_id=datasource,
                table_id=int(table_row["table_id"]),
                expression_tree="{}",
                permissions=json.dumps(permission_payload, ensure_ascii=False),
                white_list_user="[]",
                create_time=dt.datetime.now(),
                name="codex graph smoke deny net_revenue_usd",
            )
            .returning(ds_permission.c.id)
        ).scalar_one()
        rule_id = connection.execute(
            insert(ds_rules)
            .values(
                enable=True,
                name="codex graph smoke permission rule",
                description="Temporary rule created by tools/smart_qa_graph_smoke.py",
                permission_list=json.dumps([int(permission_id)], ensure_ascii=False),
                user_list=json.dumps([int(user_id)], ensure_ascii=False),
                white_list_user="[]",
                create_time=dt.datetime.now(),
                tenant_id=int(tenant_id),
                scope="TENANT",
            )
            .returning(ds_rules.c.id)
        ).scalar_one()
    try:
        yield {"permission_id": int(permission_id), "rule_id": int(rule_id)}
    finally:
        with engine.begin() as connection:
            if rule_id is not None:
                connection.execute(delete(ds_rules).where(ds_rules.c.id == int(rule_id)))
            if permission_id is not None:
                connection.execute(delete(ds_permission).where(ds_permission.c.id == int(permission_id)))


def _row_invalid_expression_tree(field_id: int) -> dict[str, Any]:
    return {
        "logic": "AND",
        "items": [
            {
                "type": "item",
                "field_id": int(field_id),
                "term": "__codex_invalid_row_permission_term__",
                "filter_type": "text",
                "value": "codex-smoke",
            }
        ],
    }


@contextmanager
def _temporary_graph_row_invalid_permission_fixture(
    system_db_url: str,
    *,
    datasource: int,
    tenant_id: int,
    user_id: int,
):
    engine = create_engine(system_db_url)
    metadata = MetaData()
    ds_permission = Table("ds_permission", metadata, autoload_with=engine)
    ds_rules = Table("ds_rules", metadata, autoload_with=engine)
    permission_id = None
    rule_id = None
    with engine.begin() as connection:
        table_row = connection.execute(
            text(
                """
                select t.id as table_id, f.id as field_id, f.field_name
                from core_table t
                join core_field f on f.table_id = t.id
                where t.ds_id = :datasource
                  and t.table_name = :table_name
                order by f.field_index asc, f.id asc
                limit 1
                """
            ),
            {
                "datasource": datasource,
                "table_name": GRAPH_PERMISSION_FIXTURE_TABLE,
            },
        ).mappings().first()
        if table_row is None:
            raise RuntimeError(
                f"Cannot create permission fixture: {GRAPH_PERMISSION_FIXTURE_TABLE} "
                f"not found for datasource {datasource}"
            )

        permission_id = connection.execute(
            insert(ds_permission)
            .values(
                enable=True,
                auth_target_type="user",
                auth_target_id=None,
                type="row",
                ds_id=datasource,
                table_id=int(table_row["table_id"]),
                expression_tree=json.dumps(
                    _row_invalid_expression_tree(int(table_row["field_id"])),
                    ensure_ascii=False,
                ),
                permissions="[]",
                white_list_user="[]",
                create_time=dt.datetime.now(),
                name="codex graph smoke invalid row permission",
            )
            .returning(ds_permission.c.id)
        ).scalar_one()
        rule_id = connection.execute(
            insert(ds_rules)
            .values(
                enable=True,
                name="codex graph smoke invalid row permission rule",
                description="Temporary rule created by tools/smart_qa_graph_smoke.py",
                permission_list=json.dumps([int(permission_id)], ensure_ascii=False),
                user_list=json.dumps([int(user_id)], ensure_ascii=False),
                white_list_user="[]",
                create_time=dt.datetime.now(),
                tenant_id=int(tenant_id),
                scope="TENANT",
            )
            .returning(ds_rules.c.id)
        ).scalar_one()
    try:
        yield {
            "permission_id": int(permission_id),
            "rule_id": int(rule_id),
            "fixture": PERMISSION_FIXTURE_ROW_INVALID,
            "table": GRAPH_PERMISSION_FIXTURE_TABLE,
            "field": table_row["field_name"],
        }
    finally:
        with engine.begin() as connection:
            if rule_id is not None:
                connection.execute(delete(ds_rules).where(ds_rules.c.id == int(rule_id)))
            if permission_id is not None:
                connection.execute(delete(ds_permission).where(ds_permission.c.id == int(permission_id)))


@contextmanager
def _temporary_graph_permission_fixture(
    system_db_url: str,
    *,
    datasource: int,
    tenant_id: int,
    user_id: int,
    fixture: str,
):
    if fixture == PERMISSION_FIXTURE_COLUMN_DENY:
        with _temporary_graph_column_permission_fixture(
            system_db_url,
            datasource=datasource,
            tenant_id=tenant_id,
            user_id=user_id,
        ) as context:
            yield {**context, "fixture": PERMISSION_FIXTURE_COLUMN_DENY}
        return

    if fixture == PERMISSION_FIXTURE_ROW_INVALID:
        with _temporary_graph_row_invalid_permission_fixture(
            system_db_url,
            datasource=datasource,
            tenant_id=tenant_id,
            user_id=user_id,
        ) as context:
            yield context
        return

    raise ValueError(f"Unsupported permission fixture: {fixture}")


def _normalize_permission_fixture(
    permission_fixture: str | None,
    with_graph_permission_fixture: bool,
) -> str | None:
    if permission_fixture:
        return permission_fixture
    if with_graph_permission_fixture:
        return PERMISSION_FIXTURE_COLUMN_DENY
    return None


def _run_case(
    base_url: str,
    headers: dict[str, str],
    case: dict[str, Any],
    output_dir: Path,
    finish_step: str,
    expect_error_type: str | None,
    *,
    assistant_mode: bool = False,
) -> dict[str, Any]:
    start_path = "/chat/assistant/start" if assistant_mode else "/chat/start"
    start_payload: dict[str, Any] = {"origin": 2 if assistant_mode else 0}
    if not assistant_mode and case["datasource"] is not None:
        start_payload["datasource"] = case["datasource"]
    chat = requests.post(
        base_url + start_path,
        headers=headers,
        json=start_payload,
        timeout=30,
    )
    if chat.status_code == 403 and expect_error_type == PERMISSION_DENIED_ERROR_TYPE:
        return {
            "case": case["name"],
            "finish_step": finish_step,
            "source_record_id": case["source_record_id"],
            "chat_id": None,
            "record_id": None,
            "expected_hint": case["name"],
            "chart_type": None,
            "finish": False,
            "error": chat.text,
            "error_type": PERMISSION_DENIED_ERROR_TYPE,
            "error_stage": "chat_start",
            "step_violation": None,
            "expectation_violation": None,
            "seconds": 0,
            "question": case["question"],
            "event_count": 0,
            "event_type_counts": {},
            "events_tail": [],
        }
    chat.raise_for_status()
    chat_id = chat.json()["data"]["id"]

    started = time.time()
    response = requests.post(
        base_url + "/chat/question",
        headers=headers,
        params={"finish_step": FINISH_STEPS[finish_step]},
        json={"chat_id": chat_id, "question": case["question"]},
        stream=True,
        timeout=240,
    )
    response.raise_for_status()

    content_parts: list[str] = []
    event_types: list[str | None] = []
    chart_type = None
    record_id = None
    error = None
    error_type = None
    saw_sql_data = False
    saw_chart = False
    for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        content_parts.append(chunk)
        for event in _sse_events(chunk):
            event_type = event.get("type")
            event_types.append(event_type)
            if event_type == "id":
                record_id = event.get("id")
            elif event_type == "sql-data":
                saw_sql_data = True
            elif event_type == "chart":
                saw_chart = True
                try:
                    chart = json.loads(event.get("content") or "{}")
                    chart_type = chart.get("type")
                except json.JSONDecodeError:
                    chart_type = "parse_error"
            elif event_type == "error":
                error = event.get("content")
                error_type = event.get("error_type")
            if event.get("error_type"):
                error_type = event.get("error_type")
        if '"type":"finish"' in chunk or '"type":"error"' in chunk:
            break

    content = "".join(content_parts)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{case['name']}-{finish_step}-{int(time.time())}.sse").write_text(content, encoding="utf-8")
    step_violation = None
    if finish_step == "generate_sql" and (saw_sql_data or saw_chart):
        step_violation = "generate_sql should stop before sql-data/chart events"
    elif finish_step == "query_data" and saw_chart:
        step_violation = "query_data should stop before chart events"
    expectation_violation = None
    if expect_error_type:
        if error_type != expect_error_type:
            expectation_violation = f"expected error_type={expect_error_type}, got {error_type or 'none'}"
    elif error:
        expectation_violation = "unexpected error event"

    return {
        "case": case["name"],
        "finish_step": finish_step,
        "source_record_id": case["source_record_id"],
        "chat_id": chat_id,
        "record_id": record_id,
        "expected_hint": case["name"],
        "chart_type": chart_type,
        "finish": '"type":"finish"' in content,
        "error": error,
        "error_type": error_type,
        "error_stage": "chat_question" if error else None,
        "step_violation": step_violation,
        "expectation_violation": expectation_violation,
        "seconds": round(time.time() - started, 1),
        "question": case["question"],
        "event_count": len(event_types),
        "event_type_counts": dict(Counter(event_types)),
        "events_tail": event_types[-10:],
    }


def _smoke_failed(result: dict[str, Any], expect_error_type: str | None) -> bool:
    return (
        (not result["finish"] and not expect_error_type)
        or bool(result["step_violation"])
        or bool(result["expectation_violation"])
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Smart Q&A LangGraph smoke cases against local API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--system-db-url", default=DEFAULT_SYSTEM_DB_URL)
    parser.add_argument("--username", default="xiaonan")
    parser.add_argument("--password", default="elex@123")
    parser.add_argument("--tenant-id", type=int, help="Optional X-ZHISHU-TENANT-ID header for workspace selection.")
    parser.add_argument("--case", action="append", choices=[case["name"] for case in DEFAULT_CASES])
    parser.add_argument("--datasource", type=int, help="Run one custom case against this datasource id.")
    parser.add_argument("--question", help="Run one custom case with this question.")
    parser.add_argument("--finish-step", choices=sorted(FINISH_STEPS), default="generate_chart")
    parser.add_argument("--expect-error-type", choices=[PERMISSION_DENIED_ERROR_TYPE])
    parser.add_argument(
        "--dynamic-assistant-fixture",
        action="store_true",
        help=(
            "Run through a temporary type=1 assistant with an external datasource-list endpoint. "
            "Defaults to datasource 910001 and a simple count question when not provided."
        ),
    )
    parser.add_argument(
        "--dynamic-assistant-datasource-id",
        type=int,
        default=DYNAMIC_ASSISTANT_DATASOURCE_ID,
        help="External datasource id exposed by --dynamic-assistant-fixture.",
    )
    parser.add_argument(
        "--permission-fixture",
        choices=PERMISSION_FIXTURES,
        help=(
            "Temporarily add a datasource permission rule for the current user. "
            "column_deny hides fact_payments.net_revenue_usd from schema; "
            "row_invalid keeps schema visible and triggers denial in the execute_sql graph node."
        ),
    )
    parser.add_argument(
        "--with-graph-permission-fixture",
        action="store_true",
        help=(
            "Deprecated alias for --permission-fixture column_deny. "
            "Use --permission-fixture row_invalid for graph-internal execute_sql denial smoke."
        ),
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    if args.dynamic_assistant_fixture:
        if not args.tenant_id:
            raise ValueError("--tenant-id is required with --dynamic-assistant-fixture")
        if args.case:
            raise ValueError("--dynamic-assistant-fixture runs a single custom case; do not pass --case")
        if args.datasource is None:
            args.datasource = int(args.dynamic_assistant_datasource_id)
        if not args.question:
            args.question = DYNAMIC_ASSISTANT_DEFAULT_QUESTION

    selected_case_names = set(args.case) if args.case else None
    output_dir = Path(args.output_dir)
    cases = _load_cases(
        args.system_db_url,
        selected_case_names,
        datasource=args.datasource,
        question=args.question,
    )
    summary = []
    failed = False
    current_user = _load_current_user(args.system_db_url, args.username)
    headers_context = contextmanager(lambda: (yield _login(args.base_url, args.username, args.password)))()
    if args.dynamic_assistant_fixture:
        headers_context = _temporary_dynamic_assistant_fixture(
            args.system_db_url,
            base_url=args.base_url,
            tenant_id=int(args.tenant_id),
            user_id=int(current_user["id"]),
            datasource_id=int(args.datasource),
        )

    permission_fixture = _normalize_permission_fixture(args.permission_fixture, args.with_graph_permission_fixture)
    fixture_context = contextmanager(lambda: (yield None))()
    if permission_fixture:
        if not args.tenant_id:
            raise ValueError("--tenant-id is required with --permission-fixture")
        if len(cases) != 1:
            raise ValueError("--permission-fixture must run a single case")
        fixture_context = _temporary_graph_permission_fixture(
            args.system_db_url,
            datasource=int(cases[0]["datasource"]),
            tenant_id=int(args.tenant_id),
            user_id=int(current_user["id"]),
            fixture=permission_fixture,
        )

    with headers_context as headers, fixture_context:
        if args.tenant_id is not None and not args.dynamic_assistant_fixture:
            headers["X-ZHISHU-TENANT-ID"] = str(args.tenant_id)
        for case in cases:
            result = _run_case(
                args.base_url,
                headers,
                case,
                output_dir,
                args.finish_step,
                args.expect_error_type,
                assistant_mode=bool(args.dynamic_assistant_fixture),
            )
            summary.append(result)
            failed = failed or _smoke_failed(result, args.expect_error_type)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
