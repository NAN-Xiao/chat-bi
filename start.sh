SSR_PATH=/opt/shuzhi/g2-ssr
APP_PATH=/opt/shuzhi/app
PM2_CMD_PATH=$SSR_PATH/node_modules/pm2/bin/pm2
APP_ROLE=${APP_ROLE:-all}
API_HOST=${API_HOST:-0.0.0.0}
API_PORT=${API_PORT:-8000}
API_WORKERS=${API_WORKERS:-1}
MCP_HOST=${MCP_HOST:-0.0.0.0}
MCP_PORT=${MCP_PORT:-8001}
SSR_HOST=${SSR_HOST:-0.0.0.0}
SSR_PORT=${SSR_PORT:-3000}
START_SSR_WITH_API=${START_SSR_WITH_API:-true}

start_ssr() {
  cd "$SSR_PATH"
  nohup "$PM2_CMD_PATH" start "$SSR_PATH/app.js" --name zhishu-g2-ssr &
}

start_mcp() {
  cd "$APP_PATH"
  nohup uvicorn main:mcp_app --host "$MCP_HOST" --port "$MCP_PORT" &
}

start_api() {
  cd "$APP_PATH"
  exec uvicorn main:app --host "$API_HOST" --port "$API_PORT" --workers "$API_WORKERS" --proxy-headers
}

run_migrations() {
  cd "$APP_PATH"
  exec python -m scripts.db_migrate
}

start_worker() {
  cd "$APP_PATH"
  exec python -m scripts.task_worker
}

start_postgres_if_needed() {
  if [ "${ZHISHU_EMBEDDED_POSTGRES:-false}" = "true" ] || [ "$APP_ROLE" = "all" ]; then
    /usr/local/bin/docker-entrypoint.sh postgres &
    wait-for-it 127.0.0.1:5432 --timeout=120 --strict -- echo -e "\033[1;32mPostgreSQL started.\033[0m"
  fi
}

case "$APP_ROLE" in
  migrate)
    run_migrations
    ;;
  api)
    if [ "$START_SSR_WITH_API" = "true" ]; then
      start_ssr
    fi
    start_api
    ;;
  worker)
    start_worker
    ;;
  mcp)
    start_mcp
    wait
    ;;
  g2-ssr|ssr)
    start_ssr
    wait
    ;;
  all)
    start_postgres_if_needed
    start_ssr
    start_mcp
    start_api
    ;;
  *)
    echo "Unsupported APP_ROLE: $APP_ROLE"
    echo "Supported roles: all, migrate, api, worker, mcp, g2-ssr"
    exit 1
    ;;
esac
