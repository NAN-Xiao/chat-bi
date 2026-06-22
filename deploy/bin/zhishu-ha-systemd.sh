#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
API_PORTS="${ZHISHU_API_PORTS:-8000 8002}"
WORKER_IDS="${ZHISHU_WORKER_IDS:-1 2}"

run_migration() {
  systemctl start zhishu-migrate.service
}

api_units() {
  for port in ${API_PORTS}; do
    printf 'zhishu-api@%s.service\n' "${port}"
  done
}

worker_units() {
  for id in ${WORKER_IDS}; do
    printf 'zhishu-worker@%s.service\n' "${id}"
  done
}

all_units() {
  api_units
  worker_units
}

case "${ACTION}" in
  migrate)
    run_migration
    ;;
  start)
    run_migration
    systemctl start $(all_units)
    ;;
  stop)
    systemctl stop $(all_units)
    ;;
  restart)
    run_migration
    systemctl restart $(all_units)
    ;;
  reload)
    systemctl daemon-reload
    run_migration
    systemctl restart $(all_units)
    ;;
  status)
    systemctl status zhishu-migrate.service $(all_units) --no-pager
    ;;
  *)
    echo "Usage: $0 {migrate|start|stop|restart|reload|status}" >&2
    exit 2
    ;;
esac
