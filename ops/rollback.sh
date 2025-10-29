#!/usr/bin/env bash
set -Eeuo pipefail
# 用法：./ops/rollback.sh v1.0.0 /path/to/backup.dump  （备份优先）
TAG="${1:-v1.0.0}"
BACKUP="${2:-}"

echo "== 停应用（按需处理你的进程管理方式）=="
# systemctl --user stop wms.service || true
pkill -f "uvicorn app.main:app" || true
sleep 1

echo "== 代码回滚 =="
git fetch --all -p
git checkout main
git reset --hard "$TAG"

if [[ -n "$BACKUP" && -f "$BACKUP" ]]; then
  echo "== DB 还原（优先用备份） =="
  pg_restore -c -d "$DATABASE_URL" "$BACKUP"
else
  echo "== DB 降级到 Tag 对应迁移（如需）=="
  # 你也可以把 alembic revision id 写在 RELEASE_NOTES 中，下面只是占位
  # alembic downgrade <rev_at_TAG>
  echo "(跳过：未提供备份/指定版本)"
fi

echo "== 重启验证 =="
uvicorn app.main:app --host "${WMS_HOST:-0.0.0.0}" --port "${WMS_PORT:-8000}" --workers "${WMS_WORKERS:-2}" &
sleep 1
./ops/healthcheck.sh
echo "回滚完成"
