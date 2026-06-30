"""Migrate datasource configurations to the server-side Fernet format.

This script converts legacy datasource configuration ciphertexts into the
current ``fernet:v1:`` format used by ``common.utils.crypto``. It is designed
to be run from the backend runtime environment with the same stable encryption
secret used by the deployed service.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from cryptography.fernet import Fernet


FERNET_PREFIX = "fernet:v1:"
DEFAULT_LEGACY_KEYS = (
    "Zhishu1234567890",
    "SQLBot1234567890",
)
AES_KEY_SIZES = {16, 24, 32}


@dataclass
class DatasourceRow:
    id: int
    name: str
    type: str
    tenant_id: int | None
    configuration: str


def _backend_path() -> Path:
    return Path(__file__).resolve().parents[1] / "backend"


def _load_psycopg2():
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import RealDictCursor  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on runtime env
        raise RuntimeError(
            "缺少 psycopg2，请在后端运行环境执行，或先安装 psycopg2-binary。"
        ) from exc
    return psycopg2, RealDictCursor


def _decode_key_token(token: str) -> bytes | None:
    token = token.strip()
    if not token:
        return None
    if token.startswith("base64:"):
        try:
            decoded = base64.b64decode(token.removeprefix("base64:"), validate=True)
            return decoded if len(decoded) in AES_KEY_SIZES else None
        except Exception:
            return None
    if token.startswith("hex:"):
        try:
            decoded = bytes.fromhex(token.removeprefix("hex:"))
            return decoded if len(decoded) in AES_KEY_SIZES else None
        except Exception:
            return None
    try:
        decoded = base64.b64decode(token, validate=True)
        if len(decoded) in AES_KEY_SIZES:
            return decoded
    except Exception:
        pass
    try:
        decoded = bytes.fromhex(token)
        if len(decoded) in AES_KEY_SIZES:
            return decoded
    except Exception:
        pass
    raw = token.encode("utf-8")
    return raw if len(raw) in AES_KEY_SIZES else None


def _legacy_keys(extra_keys: list[str]) -> list[bytes]:
    keys: list[bytes] = []
    for token in [*DEFAULT_LEGACY_KEYS, *extra_keys]:
        key = _decode_key_token(token)
        if key and key not in keys:
            keys.append(key)
    return keys


def _is_json_object(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except Exception:
        return False
    return isinstance(parsed, dict)


def decrypt_legacy_or_plaintext(configuration: str, legacy_keys: list[bytes]) -> tuple[str, str]:
    if configuration.startswith(FERNET_PREFIX):
        return configuration, "fernet"
    if _is_json_object(configuration):
        return configuration, "plain_json"

    raw = base64.b64decode(configuration)
    last_error: Exception | None = None
    for key in legacy_keys:
        try:
            cipher = AES.new(key, AES.MODE_ECB)
            plaintext = unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")
            if _is_json_object(plaintext):
                return plaintext, f"legacy_ecb:{key.decode('utf-8', errors='replace')}"
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise ValueError(f"无法用已知旧密钥解密配置：{last_error}") from last_error
    raise ValueError("无法识别配置格式")


def encrypt_fernet(plaintext: str, secret: str) -> str:
    derived = base64.urlsafe_b64encode(sha256(secret.encode("utf-8")).digest())
    return FERNET_PREFIX + Fernet(derived).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _resolve_encryption_secret(args: argparse.Namespace) -> str:
    secret = (
        args.encryption_key
        or os.getenv("SENSITIVE_CONFIG_ENCRYPTION_KEY")
        or os.getenv("DATASOURCE_CONFIG_ENCRYPTION_KEY")
        or os.getenv("SECRET_KEY")
    )
    if not secret:
        raise RuntimeError(
            "缺少新版加密密钥。请在后端运行环境设置 "
            "SENSITIVE_CONFIG_ENCRYPTION_KEY（推荐）或传 --encryption-key。"
        )
    if len(secret) < 32:
        raise RuntimeError("新版加密密钥长度必须至少 32 个字符。")
    return secret


def _db_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "host": args.host or os.getenv("POSTGRES_SERVER", "127.0.0.1"),
        "port": int(args.port or os.getenv("POSTGRES_PORT", "15432")),
        "dbname": args.database or os.getenv("POSTGRES_DB", "zhishu_bi"),
        "user": args.user or os.getenv("POSTGRES_USER", "root"),
        "password": args.password or os.getenv("POSTGRES_PASSWORD", "Password123@pg"),
    }


def _backup_path(args: argparse.Namespace) -> Path:
    backup_dir = Path(args.backup_dir or Path.cwd() / ".codex-runtime" / "backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir / f"datasource_config_migration_{int(time.time())}.json"


def _load_rows(conn: Any, ids: list[int]) -> list[DatasourceRow]:
    _, real_dict_cursor = _load_psycopg2()
    where = "configuration IS NOT NULL AND configuration <> ''"
    params: list[Any] = []
    if ids:
        where += " AND id = ANY(%s)"
        params.append(ids)
    with conn.cursor(cursor_factory=real_dict_cursor) as cur:
        cur.execute(
            f"""
            SELECT id, name, type, tenant_id, configuration
            FROM public.core_datasource
            WHERE {where}
            ORDER BY id
            """,
            params,
        )
        return [
            DatasourceRow(
                id=int(row["id"]),
                name=str(row["name"]),
                type=str(row["type"]),
                tenant_id=row.get("tenant_id"),
                configuration=str(row["configuration"] or ""),
            )
            for row in cur.fetchall()
        ]


def migrate(args: argparse.Namespace) -> int:
    secret = _resolve_encryption_secret(args)
    legacy_keys = _legacy_keys(args.legacy_key or [])
    psycopg2, _ = _load_psycopg2()
    conn = psycopg2.connect(**_db_config(args), connect_timeout=args.connect_timeout)
    changed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    try:
        rows = _load_rows(conn, args.datasource_id or [])
        backup_items = [
            {
                "id": row.id,
                "name": row.name,
                "type": row.type,
                "tenant_id": row.tenant_id,
                "configuration": row.configuration,
            }
            for row in rows
        ]
        backup_file = _backup_path(args)
        backup_file.write_text(json.dumps(backup_items, ensure_ascii=False, indent=2), encoding="utf-8")

        for row in rows:
            try:
                plaintext, source = decrypt_legacy_or_plaintext(row.configuration, legacy_keys)
                if source == "fernet":
                    skipped.append({"id": row.id, "name": row.name, "reason": "already_fernet"})
                    continue
                encrypted = encrypt_fernet(plaintext, secret)
                changed.append(
                    {
                        "id": row.id,
                        "name": row.name,
                        "source": source,
                        "old_prefix": row.configuration[:12],
                        "new_prefix": encrypted[:12],
                        "configuration": encrypted,
                    }
                )
            except Exception as exc:
                failed.append({"id": row.id, "name": row.name, "reason": str(exc)})

        if args.apply and changed:
            with conn:
                with conn.cursor() as cur:
                    for item in changed:
                        cur.execute(
                            """
                            UPDATE public.core_datasource
                               SET configuration = %s
                             WHERE id = %s
                            """,
                            (item["configuration"], item["id"]),
                        )
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry-run",
                    "backup": str(backup_file),
                    "scanned": len(rows),
                    "will_update": len(changed),
                    "skipped": skipped,
                    "updated": [
                        {
                            "id": item["id"],
                            "name": item["name"],
                            "source": item["source"],
                            "old_prefix": item["old_prefix"],
                            "new_prefix": item["new_prefix"],
                        }
                        for item in changed
                    ],
                    "failed": failed,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if failed else 0
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="迁移 core_datasource.configuration 到 fernet:v1 服务端加密格式。"
    )
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；默认只预览。")
    parser.add_argument("--host", default=None, help="系统库地址，默认读 POSTGRES_SERVER。")
    parser.add_argument("--port", type=int, default=None, help="系统库端口，默认读 POSTGRES_PORT。")
    parser.add_argument("--database", default=None, help="系统库名称，默认读 POSTGRES_DB。")
    parser.add_argument("--user", default=None, help="系统库用户，默认读 POSTGRES_USER。")
    parser.add_argument("--password", default=None, help="系统库密码，默认读 POSTGRES_PASSWORD。")
    parser.add_argument("--connect-timeout", type=int, default=5)
    parser.add_argument("--backup-dir", default=None, help="备份目录，默认 .codex-runtime/backups。")
    parser.add_argument(
        "--datasource-id",
        type=int,
        action="append",
        default=[],
        help="只迁移指定数据源，可重复传；默认扫描全部数据源。",
    )
    parser.add_argument(
        "--legacy-key",
        action="append",
        default=[],
        help="额外旧 AES-ECB 密钥，可重复传；默认兼容 Zhishu1234567890 与 SQLBot1234567890。",
    )
    parser.add_argument(
        "--encryption-key",
        default=None,
        help="新版服务端加密密钥；优先使用后端环境变量 SENSITIVE_CONFIG_ENCRYPTION_KEY。",
    )
    return parser


def main() -> int:
    sys.path.insert(0, str(_backend_path()))
    parser = build_parser()
    args = parser.parse_args()
    return migrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
