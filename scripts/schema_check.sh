#!/usr/bin/env bash
set -euo pipefail

echo "==> Drift Gate #1: ORM 变更是否遗漏迁移（autogenerate 应为“空”）"

# 1) 固定 Gate 使用的临时 SQLite，并确保在 head
export ALEMBIC_SQLITE_URL="${ALEMBIC_SQLITE_URL:-sqlite:///gate_check.db}"
unset DATABASE_URL  # 避免不小心连到 PG
rm -f gate_check.db A.sql B.sql alembic/versions/*_autocheck_*.py 2>/dev/null || true
alembic upgrade head >/dev/null 2>&1 || true

# 2) 生成一次“自检迁移”
stamp="autocheck_$(date +%s)"
alembic revision --autogenerate -m "${stamp}" >/dev/null

rev_file="$(ls -t alembic/versions/*_${stamp}.py 2>/dev/null | head -n1 || true)"
# 兼容老脚本残留的 _autocheck_*.py
[ -z "${rev_file}" ] && rev_file="$(ls -t alembic/versions/*_autocheck_*.py 2>/dev/null | head -n1 || true)"

if [ -z "${rev_file}" ]; then
  echo "✅ 没有遗漏迁移（未生成自检文件）"
else
  # 3) 判断是否“空变更”（无任何 op. 调用）
  if ! grep -q "op\." "${rev_file}"; then
    rm -f "${rev_file}"
    echo "✅ 没有遗漏迁移（autogenerate 为空）"
  else
    echo "❌ 检测到模型改动但未提交迁移：${rev_file}"
    exit 1
  fi
fi

echo "==> Drift Gate #2: 迁移回放结构 VS ORM 元数据结构 快照对比"

# 4) 用脚本里的 SQLite 回放迁移（A.sql）和 ORM 结构（B.sql），做结构 diff
python3 scripts/sql/schema_snapshot.py >/dev/null

if diff -u A.sql B.sql >/dev/null; then
  echo "✅ 结构快照一致（A.sql 与 B.sql 无差异）"
else
  echo "❌ 结构快照不一致（见下方 diff）"
  diff -u A.sql B.sql || true
  exit 1
fi
