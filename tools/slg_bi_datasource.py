"""Resolve the PostgreSQL datasource bound to an SLG BI dashboard."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg2.extras import RealDictCursor

from core_system_db import export_postgres_compat_env


DEFAULT_LOCAL_SECRET_KEY = "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s"
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"


@dataclass(frozen=True, slots=True)
class SlgBiDatasourceContext:
    tenant_id: int
    datasource_id: int
    connection: dict[str, Any]


def ensure_backend_decryption_env() -> None:
    os.environ.setdefault("SECRET_KEY", DEFAULT_LOCAL_SECRET_KEY)


def decrypt_datasource_settings(configuration: Any) -> dict[str, Any]:
    ensure_backend_decryption_env()
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from apps.datasource.utils.utils import aes_decrypt

    return json.loads(aes_decrypt(configuration))


def psycopg2_config_from_datasource_settings(settings: dict[str, Any]) -> dict[str, Any]:
    field_map = {
        "host": "host",
        "port": "port",
        "database": "dbname",
        "username": "user",
        "password": "password",
    }
    missing = [source for source in field_map if settings.get(source) in (None, "")]
    if missing:
        raise RuntimeError(
            "Datasource configuration is missing required fields: " + ", ".join(missing)
        )
    result = {target: settings[source] for source, target in field_map.items()}
    result["port"] = int(result["port"])
    return result


def resolve_slg_bi_datasource_context(
    system_conn: Any,
    dashboard_id: str,
    datasource_name: str = "SLG BI Mock",
) -> SlgBiDatasourceContext:
    with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tenant_id
            FROM public.core_dashboard
            WHERE id = %s AND delete_flag = 0
            """,
            (dashboard_id,),
        )
        dashboard = cur.fetchone()
        if not dashboard:
            raise RuntimeError(f"Dashboard not found: {dashboard_id}")

        tenant_id = int(dashboard["tenant_id"])
        cur.execute(
            """
            SELECT datasource.id AS datasource_id,
                   datasource.type,
                   datasource.configuration
            FROM public.core_datasource_tenant_binding AS binding
            JOIN public.core_datasource AS datasource
              ON datasource.id = binding.datasource_id
            WHERE binding.tenant_id = %s
              AND datasource.name = %s
            LIMIT 1
            """,
            (tenant_id, datasource_name),
        )
        datasource = cur.fetchone()

    if not datasource:
        raise RuntimeError(
            f"Tenant {tenant_id} has no current {datasource_name} datasource binding"
        )
    if str(datasource["type"] or "").casefold() not in {"pg", "postgres", "postgresql"}:
        raise RuntimeError(
            f"Datasource {datasource['datasource_id']} is not PostgreSQL: {datasource['type']}"
        )

    settings = decrypt_datasource_settings(datasource["configuration"])
    connection = psycopg2_config_from_datasource_settings(settings)
    export_postgres_compat_env(connection)
    return SlgBiDatasourceContext(
        tenant_id=tenant_id,
        datasource_id=int(datasource["datasource_id"]),
        connection=connection,
    )
