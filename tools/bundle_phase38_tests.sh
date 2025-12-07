#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  bundle_phase38_tests.sh
#
#  用于一次性打包 Phase 3.8 第一批需要对齐的 18 个测试文件。
#
#  默认输出：phase38_snapshot_ledger_tests.tar.gz
#  自定义输出：
#       bash tools/bundle_phase38_tests.sh mypack.tgz
#
#  脚本会检查所有文件是否存在，缺失则中断。
# ============================================================

OUT="${1:-phase38_snapshot_ledger_tests.tar.gz}"

FILES=(
  # ----------------------------------------------------------
  # 圈 1 · Snapshot + Invariants（与库存地基强相关）
  # ----------------------------------------------------------
  tests/ci/test_db_invariants_helpers.py
  tests/db/test_batches_expiry_constraints.py
  tests/services/test_snapshot_service.py
  tests/services/test_snapshot_service_contract.py
  tests/services/test_snapshot_service_dbproc.py
  tests/services/test_snapshot_service_split.py
  tests/services/test_snapshot_service_batch_agg.py
  tests/quick/test_snapshot_inventory_pg.py
  tests/quick/test_snapshot_run_v2.py
  tests/quick/test_stock_snapshot_pg.py
  tests/quick/test_stock_snapshot_backfill_pg.py

  # ----------------------------------------------------------
  # 圈 2 · Ledger 体系（after_qty / 聚合视图）
  # ----------------------------------------------------------
  tests/ci/test_ledger_idem_constraint.py
  tests/services/test_stock_ledger.py
  tests/services/test_stock_ledger_route.py
  tests/services/test_ledger_writer.py
  tests/services/test_stock_on_hand_aggregation.py
  tests/api/test_stock_ledger.py
  tests/unit/test_ledger_writer_idem_v2.py
)

echo ""
echo "🟦 [bundle] 打包 Phase 3.8 测试文件"
echo "🟦 [bundle] 输出文件: $OUT"
echo ""

echo "🟩 开始检查文件存在性…"

MISSING=0
for f in "${FILES[@]}"; do
  if [[ -f "$f" ]]; then
    echo "   ✔  $f"
  else
    echo "   ✖  缺失: $f" >&2
    MISSING=1
  fi
done

if [[ "$MISSING" -eq 1 ]]; then
  echo ""
  echo "🟥 检测到缺失文件，停止打包。" >&2
  exit 1
fi

echo ""
echo "🟦 所有文件存在，开始打包…"
tar czf "$OUT" "${FILES[@]}"

echo "🟩 打包完成：$OUT"
echo ""
echo "你现在可以直接上传这个压缩包。"
