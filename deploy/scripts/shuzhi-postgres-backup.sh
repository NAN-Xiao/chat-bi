#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/shuzhi/shuzhi.env}"

read_env_var() {
  local name="$1"
  local line
  local value

  if [[ -n "${!name:-}" ]] || [[ ! -f "$ENV_FILE" ]]; then
    return
  fi

  line="$(grep -E "^[[:space:]]*${name}=" "$ENV_FILE" | tail -n 1 || true)"
  if [[ -z "$line" ]]; then
    return
  fi

  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  export "$name=$value"
}

for env_name in \
  POSTGRES_SERVER POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD \
  BACKUP_DIR BACKUP_RETENTION_DAYS PG_DUMP_BIN PGCONNECT_TIMEOUT PGSSLMODE
do
  read_env_var "$env_name"
done

: "${POSTGRES_SERVER:?POSTGRES_SERVER is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/shuzhi/postgres}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
PG_DUMP_BIN="${PG_DUMP_BIN:-pg_dump}"

if ! [[ "$BACKUP_RETENTION_DAYS" =~ ^[0-9]+$ ]] || [[ "$BACKUP_RETENTION_DAYS" -lt 1 ]]; then
  echo "BACKUP_RETENTION_DAYS must be a positive integer." >&2
  exit 2
fi

if ! command -v "$PG_DUMP_BIN" >/dev/null 2>&1; then
  echo "Cannot find pg_dump binary: $PG_DUMP_BIN" >&2
  exit 2
fi

umask 077
mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
safe_db_name="${POSTGRES_DB//[^A-Za-z0-9_.-]/_}"
backup_file="$BACKUP_DIR/${safe_db_name}-${timestamp}.dump"
checksum_file="$backup_file.sha256"

export PGPASSWORD="$POSTGRES_PASSWORD"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"
export PGSSLMODE="${PGSSLMODE:-prefer}"

"$PG_DUMP_BIN" \
  --host="$POSTGRES_SERVER" \
  --port="$POSTGRES_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="$backup_file"

unset PGPASSWORD

if [[ ! -s "$backup_file" ]]; then
  echo "Backup file is empty: $backup_file" >&2
  rm -f "$backup_file" "$checksum_file"
  exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$backup_file" > "$checksum_file"
elif command -v shasum >/dev/null 2>&1; then
  shasum -a 256 "$backup_file" > "$checksum_file"
fi

ln -sfn "$backup_file" "$BACKUP_DIR/${safe_db_name}-latest.dump"
if [[ -f "$checksum_file" ]]; then
  ln -sfn "$checksum_file" "$BACKUP_DIR/${safe_db_name}-latest.dump.sha256"
fi

find "$BACKUP_DIR" -maxdepth 1 -type f -name "${safe_db_name}-*.dump" -mtime +"$BACKUP_RETENTION_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -type f -name "${safe_db_name}-*.dump.sha256" -mtime +"$BACKUP_RETENTION_DAYS" -delete

echo "PostgreSQL backup completed: $backup_file"
