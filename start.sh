#!/usr/bin/env sh
set -eu

APP_ROLE=${APP_ROLE:-all}
SQLBOT_HOME=${SQLBOT_HOME:-/opt/sqlbot}
SSR_PATH=${SSR_PATH:-$SQLBOT_HOME/g2-ssr}
APP_PATH=${APP_PATH:-$SQLBOT_HOME/app}
PM2_CMD_PATH=${PM2_CMD_PATH:-$SSR_PATH/node_modules/pm2/bin/pm2}
LOG_DIR=${LOG_DIR:-$APP_PATH/logs}

API_HOST=${API_HOST:-0.0.0.0}
API_PORT=${API_PORT:-8000}
MCP_HOST=${MCP_HOST:-0.0.0.0}
MCP_PORT=${MCP_PORT:-8001}

POSTGRES_SERVER=${POSTGRES_SERVER:-localhost}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
REDIS_HOST=${REDIS_HOST:-127.0.0.1}
REDIS_PORT=${REDIS_PORT:-6379}
CACHE_TYPE=${CACHE_TYPE:-memory}
MCP_ENABLED=${MCP_ENABLED:-false}

mkdir -p "$LOG_DIR"

wait_for_tcp() {
  host="$1"
  port="$2"
  label="$3"
  wait-for-it "$host:$port" --timeout=120 --strict -- printf "\\033[1;32m%s is reachable.\\033[0m\\n" "$label"
}

start_embedded_postgres_if_needed() {
  case "$POSTGRES_SERVER" in
    localhost|127.0.0.1|::1)
      /usr/local/bin/docker-entrypoint.sh postgres >> "$LOG_DIR/postgres.log" 2>&1 &
      sleep 5
      wait_for_tcp 127.0.0.1 5432 "PostgreSQL"
      ;;
    *)
      wait_for_tcp "$POSTGRES_SERVER" "$POSTGRES_PORT" "Remote PostgreSQL"
      ;;
  esac
}

wait_for_dependencies() {
  wait_for_tcp "$POSTGRES_SERVER" "$POSTGRES_PORT" "PostgreSQL"
  if [ "$(printf '%s' "$CACHE_TYPE" | tr '[:upper:]' '[:lower:]')" = "redis" ]; then
    wait_for_tcp "$REDIS_HOST" "$REDIS_PORT" "Redis"
  fi
}

run_migrations() {
  cd "$APP_PATH"
  AUTO_MIGRATE_ON_STARTUP=false alembic upgrade head
}

start_g2_ssr_background() {
  if [ -x "$PM2_CMD_PATH" ]; then
    nohup "$PM2_CMD_PATH" start "$SSR_PATH/app.js" --output "$LOG_DIR/g2-ssr.log" --error "$LOG_DIR/g2-ssr-error.log" &
  else
    nohup node "$SSR_PATH/app.js" >> "$LOG_DIR/g2-ssr.log" 2>> "$LOG_DIR/g2-ssr-error.log" &
  fi
}

start_g2_ssr_foreground() {
  if [ -x "$PM2_CMD_PATH" ]; then
    exec "$PM2_CMD_PATH" start "$SSR_PATH/app.js" --no-daemon --output "$LOG_DIR/g2-ssr.log" --error "$LOG_DIR/g2-ssr-error.log"
  fi
  exec node "$SSR_PATH/app.js"
}

start_mcp_background() {
  if [ "$(printf '%s' "$MCP_ENABLED" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
    cd "$APP_PATH"
    nohup uvicorn main:mcp_app --host "$MCP_HOST" --port "$MCP_PORT" >> "$LOG_DIR/uvicorn-mcp.log" 2>&1 &
  fi
}

start_mcp_foreground() {
  cd "$APP_PATH"
  export AUTO_MIGRATE_ON_STARTUP=false
  exec uvicorn main:mcp_app --host "$MCP_HOST" --port "$MCP_PORT"
}

start_api_foreground() {
  cd "$APP_PATH"
  export AUTO_MIGRATE_ON_STARTUP=${AUTO_MIGRATE_ON_STARTUP:-false}
  exec uvicorn main:app --host "$API_HOST" --port "$API_PORT" --workers 1 --proxy-headers
}

start_worker_foreground() {
  cd "$APP_PATH"
  export AUTO_MIGRATE_ON_STARTUP=false
  exec python -m scripts.task_worker
}

case "$APP_ROLE" in
  migrate)
    wait_for_dependencies
    run_migrations
    ;;
  api)
    wait_for_dependencies
    start_api_foreground
    ;;
  worker)
    wait_for_dependencies
    start_worker_foreground
    ;;
  mcp)
    wait_for_dependencies
    start_mcp_foreground
    ;;
  g2-ssr)
    start_g2_ssr_foreground
    ;;
  all)
    start_embedded_postgres_if_needed
    if [ "$(printf '%s' "$CACHE_TYPE" | tr '[:upper:]' '[:lower:]')" = "redis" ]; then
      wait_for_tcp "$REDIS_HOST" "$REDIS_PORT" "Redis"
    fi
    run_migrations
    start_g2_ssr_background
    start_mcp_background
    cd "$APP_PATH"
    export AUTO_MIGRATE_ON_STARTUP=false
    exec uvicorn main:app --host "$API_HOST" --port "$API_PORT" --workers 1 --proxy-headers >> "$LOG_DIR/uvicorn-web.log" 2>&1
    ;;
  *)
    echo "Unknown APP_ROLE: $APP_ROLE" >&2
    echo "Supported APP_ROLE values: all, migrate, api, worker, mcp, g2-ssr" >&2
    exit 2
    ;;
esac
