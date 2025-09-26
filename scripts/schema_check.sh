#!/usr/bin/env bash
# scripts/schema_check.sh
set -euo pipefail

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

echo -e "${YELLOW}==> Drift Gate #1: ORM 变更是否遗漏迁移（autogenerate 应为“空”）${NC}"

# 临时生成一个带标记的迁移，如果生成了文件，就说明模型变更未提交迁移
STAMP="autocheck_$(date +%s)"
created=""
set +e
out=$(alembic revision --autogenerate -m "$STAMP" 2>&1)
status=$?
set -e

# 找出刚生成的迁移文件（如果有）
if git ls-files --others --exclude-standard alembic/versions | grep -qi "$STAMP"; then
  created=$(git ls-files --others --exclude-standard alembic/versions | grep -i "$STAMP" | head -n1)
fi

if [[ -n "${created}" ]]; then
  echo -e "${RED}❌ 检测到模型改动但未提交迁移：${created}${NC}"
  # 清理临时文件，避免污染工作区
  rm -f "${created}"
  exit 1
else
  echo -e "${GREEN}✅ 没有遗漏迁移（autogenerate 为空）${NC}"
fi

echo -e "${YELLOW}==> Drift Gate #2: 迁移回放结构 VS ORM 元数据结构 快照对比${NC}"
python scripts/sql/schema_snapshot.py

if diff -u A.sql B.sql; then
  echo -e "${GREEN}✅ 模型 / 迁移 / 数据库 结构一致${NC}"
else
  echo -e "${RED}❌ 结构快照不一致：请检查 Alembic 迁移与 ORM 定义${NC}"
  exit 1
fi
