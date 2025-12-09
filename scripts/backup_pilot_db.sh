#!/usr/bin/env bash
set -euo pipefail

# ================================
# WMS-DU Pilot DB 备份脚本（示例）
# 在中试服务器上使用，按实际情况修改以下变量：
# ================================

DB_HOST="127.0.0.1"
DB_PORT="54322"
DB_NAME="wms_pilot"
DB_USER="wms"

BACKUP_DIR="backups/pilot"
mkdir -p "$BACKUP_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/pilot_${DB_NAME}_${TS}.sql.gz"

echo "[backup] Dumping ${DB_NAME} on ${DB_HOST}:${DB_PORT} ..."
PGPASSWORD="${PGPASSWORD:-wms}" pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -F p \
  "$DB_NAME" \
  | gzip > "$BACKUP_FILE"

echo "[backup] Done: $BACKUP_FILE"
