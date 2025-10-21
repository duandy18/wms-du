#!/usr/bin/env bash
# ===================================================================
# WMS-DU CI forwarder
# -------------------------------------------------------------------
# 作用：
#   - 保持历史兼容：CI 可继续使用 .github/ci/run.sh
#   - 自动定位仓库根目录并转交执行 ./run.sh
#   - 确保根脚本有执行权限
# ===================================================================

set -Eeuo pipefail

# --- 定位仓库根目录 ---
if ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  # 若 git 不可用（例如 Actions checkout 后未带 .git），则用路径反推
  SELF="$(readlink -f "$0" 2>/dev/null || python3 - <<'PY'
import os,sys
p=os.path.abspath(sys.argv[1]); print(os.path.realpath(p))
PY
"$0")"
  ROOT="$(dirname "$(dirname "$SELF")")"
fi

TARGET="$ROOT/run.sh"

# --- 检查文件存在 ---
if [[ ! -f "$TARGET" ]]; then
  echo "❌ Cannot find root run.sh at: $TARGET" >&2
  echo "   Please ensure the repo has a root-level run.sh" >&2
  exit 127
fi

# --- 确保可执行权限 ---
chmod +x "$TARGET" || true

# --- 环境预设（仅兜底，不覆盖 CI 自身 env） ---
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export PYTHONPATH="${PYTHONPATH:-$ROOT}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://wms:wms@127.0.0.1:5432/wms}"

# --- 转发执行 ---
exec "$TARGET" "$@"
