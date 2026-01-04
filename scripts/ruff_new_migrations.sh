#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${1:-origin/main}"

# 找出本分支相对 BASE 新增的迁移文件
new_migrations=$(git diff --name-only --diff-filter=A "${BASE_REF}...HEAD" | grep -E '^alembic/versions/.*\.py$' || true)

if [[ -z "${new_migrations}" ]]; then
  echo "[ruff-new-migrations] No new alembic migrations added."
  exit 0
fi

echo "[ruff-new-migrations] Checking new migrations:"
echo "${new_migrations}"

# 只检查新增迁移，避免历史噪音
ruff check ${new_migrations}
