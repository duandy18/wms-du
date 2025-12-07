#!/usr/bin/env bash
# 安全的 Phase 2 表结构导出：即使某个 psql 失败也不会退出你的当前 shell/venv

# -------- 配置 --------
OUTDIR="tools/audits/phase2/ddl"
DBURL="${DATABASE_URL}"

# 表清单（按需调整/增减）
tables=(
  order_lines
  order_state_snapshot
  reservation_lines
  pick_tasks
  pick_task_lines
  pick_task_line_reservations
  outbound_commits
  outbound_ship_ops
  platform_events
  event_log
  event_store
  event_replay_cursor
  audit_events
  orders
  order_items
)

# -------- 前置检查（不中断当前 shell）--------
if ! command -v psql >/dev/null 2>&1; then
  echo "[ERROR] psql 未找到，请确认已安装并在 PATH 中。" >&2
  exit 127
fi

if [ -z "${DBURL}" ]; then
  echo "[ERROR] 未设置 DATABASE_URL 环境变量。" >&2
  echo "例如：export DATABASE_URL=postgresql+psycopg://wms:wms@127.0.0.1:5433/wms" >&2
  exit 2
fi

mkdir -p "${OUTDIR}"

# -------- 导出（遇错继续）--------
echo ">>> 输出目录：${OUTDIR}"
for t in "${tables[@]}"; do
  echo ">>> dumping ${t}"
  # -v ON_ERROR_STOP=1 让 psql 有语法错误时返回非0；但我们用 || 只记warn不退出
  psql "${DBURL}" -v ON_ERROR_STOP=1 -c "\d+ ${t}" > "${OUTDIR}/${t}.ddl.txt" 2> "${OUTDIR}/${t}.err.txt"
  if [ $? -ne 0 ]; then
    echo "[WARN] 导出 ${t} 失败，详见 ${OUTDIR}/${t}.err.txt"
    # 不中断循环，继续下一个表
  fi
done

echo ">>> Done. 所有文件已生成在 ${OUTDIR}/"
exit 0
