#!/usr/bin/env bash
# CI 转发器：固定入口，不承载任何业务逻辑，仅把 CI 的调用转发到仓库根 run.sh
# 这样以后你只维护根 run.sh，ci.yml 永久稳定不用动。
set -euo pipefail

# 兼容旧用法：不传参数时默认跑四件套（老路由主入口）
CMD="${1:-ci:pg:all}"

# 计算仓库根路径（本文件位于 .github/ci/）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ -x "${ROOT}/run.sh" ]]; then
  exec "${ROOT}/run.sh" "$CMD" "${@:2}"
else
  echo "ERROR: ${ROOT}/run.sh not found or not executable." >&2
  exit 127
fi
