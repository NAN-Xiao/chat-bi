#!/bin/bash
export PGPASSWORD='Password123@pg'
echo "Checking database slg_bi_mock..."
if ! psql -h 127.0.0.1 -p 5432 -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='slg_bi_mock'" | grep -q 1; then
  echo "Database not found, creating..."
  createdb -h 127.0.0.1 -p 5432 -U postgres slg_bi_mock
fi
echo "Importing /tmp/mock.sql into slg_bi_mock..."
psql -h 127.0.0.1 -p 5432 -U postgres -d slg_bi_mock -f /tmp/mock.sql
rc=$?
echo "IMPORT_DONE:$rc"
exit $rc
