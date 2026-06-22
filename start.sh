set -eu

SSR_PATH=/opt/sqlbot/g2-ssr
APP_PATH=/opt/sqlbot/app
PM2_CMD_PATH=$SSR_PATH/node_modules/pm2/bin/pm2
LOG_DIR=${LOG_DIR:-$APP_PATH/logs}

mkdir -p "$LOG_DIR"

/usr/local/bin/docker-entrypoint.sh postgres >> "$LOG_DIR/postgres.log" 2>&1 &
sleep 5
wait-for-it 127.0.0.1:5432 --timeout=120 --strict -- printf "\\033[1;32mPostgreSQL started.\\033[0m\\n"

nohup "$PM2_CMD_PATH" start "$SSR_PATH/app.js" --output "$LOG_DIR/g2-ssr.log" --error "$LOG_DIR/g2-ssr-error.log" &
#nohup node $SSR_PATH/app.js &

nohup uvicorn main:mcp_app --host 0.0.0.0 --port 8001 >> "$LOG_DIR/uvicorn-mcp.log" 2>&1 &

cd "$APP_PATH"
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers >> "$LOG_DIR/uvicorn-web.log" 2>&1
