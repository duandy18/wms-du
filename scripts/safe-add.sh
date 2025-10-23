#!/usr/bin/env bash
# ================================================================
# scripts/safe-add.sh
# 用途：安全地将改动文件加入 git 暂存区，过滤调试/临时文件
# 适用于大型分支准备合并前的“整理提交”
# ================================================================

set -euo pipefail

echo ">>> 执行安全 git add 流程..."
echo

# 过滤规则：排除 .bak、临时 compose、禁用迁移、可观测样例等
EXCLUDES=(
  "*.bak"
  "_migrations_disabled/"
  "ops/compose/micro/"
  "app/observability/"
  "ops/observability/"
  "scripts/ports_doctor.sh"
  "scripts/replay_illegal.py"
  ".DS_Store"
  "__pycache__/"
)

# 构建排除参数
EXCLUDE_ARGS=()
for e in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=( ":!$e" )
done

echo "过滤以下模式："
for e in "${EXCLUDES[@]}"; do
  echo "  - $e"
done
echo

# 实际执行 add（包括新增、修改、删除，但排除上述模式）
git add -A "${EXCLUDE_ARGS[@]}"

echo
echo ">>> 已加入暂存区的文件："
git diff --cached --name-only

echo
echo ">>> 提交示例："
echo "    git commit --no-verify -m 'chore: safe staged commit (auto-filtered temporary files)'"
echo
