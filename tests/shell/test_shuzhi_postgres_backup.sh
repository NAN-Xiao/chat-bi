#!/usr/bin/env bash
set -euo pipefail

SCRIPT="${1:-deploy/scripts/shuzhi-postgres-backup.sh}"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

FAKE_PG_DUMP="$TEST_ROOT/fake-pg-dump"
cat > "$FAKE_PG_DUMP" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
output=""
for argument in "$@"; do
  case "$argument" in
    --file=*) output="${argument#*=}" ;;
  esac
done
[[ -n "$output" ]] || exit 3
printf 'partial archive\n' > "$output"
if [[ "${FAKE_PG_DUMP_FAIL:-0}" == "1" ]]; then
  exit 9
fi
printf 'complete archive\n' >> "$output"
EOF
chmod 0755 "$FAKE_PG_DUMP"

run_backup() {
  local backup_dir="$1"
  local fail_dump="${2:-0}"
  env \
    ENV_FILE="$TEST_ROOT/missing.env" \
    POSTGRES_SERVER="10.1.5.28" \
    POSTGRES_PORT="5432" \
    POSTGRES_DB="zhishu_bi" \
    POSTGRES_USER="root" \
    POSTGRES_PASSWORD="test-only" \
    BACKUP_DIR="$backup_dir" \
    BACKUP_RETENTION_DAYS="14" \
    PG_DUMP_BIN="$FAKE_PG_DUMP" \
    FAKE_PG_DUMP_FAIL="$fail_dump" \
    bash "$SCRIPT"
}

failure_dir="$TEST_ROOT/failure"
if run_backup "$failure_dir" 1; then
  fail "pg_dump 失败时脚本仍返回成功"
fi
if find "$failure_dir" -maxdepth 1 -type f \( -name '*.partial' -o -name '*.dump' \) | grep -q .; then
  fail "pg_dump 失败后残留了备份文件"
fi

success_dir="$TEST_ROOT/success"
run_backup "$success_dir"
backup_file="$(find "$success_dir" -maxdepth 1 -type f -name 'zhishu_bi-*.dump' | head -n 1)"
[[ -n "$backup_file" && -s "$backup_file" ]] || fail "没有生成非空正式备份"
[[ -s "$backup_file.sha256" ]] || fail "没有生成校验文件"
case "$(uname -s)" in
  MINGW*|MSYS*)
    cmp -s "$success_dir/zhishu_bi-latest.dump" "$backup_file" || fail "latest 备份内容与正式备份不一致"
    cmp -s "$success_dir/zhishu_bi-latest.dump.sha256" "$backup_file.sha256" || fail "latest 校验内容与正式校验不一致"
    ;;
  *)
    [[ -L "$success_dir/zhishu_bi-latest.dump" ]] || fail "没有生成 latest 备份链接"
    [[ -L "$success_dir/zhishu_bi-latest.dump.sha256" ]] || fail "没有生成 latest 校验链接"
    ;;
esac
if find "$success_dir" -maxdepth 1 -type f -name '*.partial' | grep -q .; then
  fail "成功后仍残留临时文件"
fi

expired_dir="$TEST_ROOT/expired"
mkdir -p "$expired_dir"
printf 'old archive\n' > "$expired_dir/zhishu_bi-20000101T000000Z.dump"
printf 'old checksum\n' > "$expired_dir/zhishu_bi-20000101T000000Z.dump.sha256"
touch -d '20 days ago' "$expired_dir"/zhishu_bi-20000101T000000Z.dump*
run_backup "$expired_dir"
[[ ! -e "$expired_dir/zhishu_bi-20000101T000000Z.dump" ]] || fail "过期备份未删除"
[[ ! -e "$expired_dir/zhishu_bi-20000101T000000Z.dump.sha256" ]] || fail "过期校验文件未删除"

echo "PASS: PostgreSQL backup shell behavior"
