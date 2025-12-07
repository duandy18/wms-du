#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

echo "[phase3] 目标：清理 batches/stocks 上残留的 location_id 直接引用"
echo "   - 只动我们明确挑出的几个文件"
echo "   - 其余文件先保留，后面分阶段收拾"
echo

TARGET_FILES=(
  "app/services/reservation_lock.py"
  "app/services/stock_helpers.py"
  "tests/helpers/inventory.py"
  "tests/utils/ensure_minimal.py"
  "tests/db/test_v_stocks_enriched.py"
  "tests/db/test_batches_expiry_constraints.py"
  "tests/services/test_reservation_lifecycle.py"
  "tests/services/phase34/test_ship_reserve_out_of_order.py"
  "tests/services/phase34/test_adjust_stress_perf.py"
)

echo "[phase3] 将处理以下文件："
for f in "${TARGET_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    echo "  - $f"
  else
    echo "  - $f (不存在，跳过)"
  fi
done
echo

python << 'PY'
import pathlib
import re
import sys

ROOT = pathlib.Path(".").resolve()

TARGET_FILES = [
    pathlib.Path(p) for p in [
        "app/services/reservation_lock.py",
        "app/services/stock_helpers.py",
        "tests/helpers/inventory.py",
        "tests/utils/ensure_minimal.py",
        "tests/db/test_v_stocks_enriched.py",
        "tests/db/test_batches_expiry_constraints.py",
        "tests/services/test_reservation_lifecycle.py",
        "tests/services/phase34/test_ship_reserve_out_of_order.py",
        "tests/services/phase34/test_adjust_stress_perf.py",
    ]
]

def rewrite_sql(text: str) -> str:
    """
    只做两类聚焦修改：
    1) INSERT INTO batches(...) 里去掉 location_id 列及对应 values 占位
    2) INSERT/SELECT/ON CONFLICT 里针对 batches 的 column list 去掉 location_id

    对 stocks 先不做自动重写（因为 item+loc → item+wh 的迁移需要业务语义），
    避免一刀切把位移逻辑干碎。
    """

    # 1) INSERT INTO batches 列表中去掉 location_id
    def drop_loc_from_batches_cols(m: re.Match) -> str:
        cols = m.group("cols")
        # 粗暴：把 location_id 相关逗号一块干掉
        cols2 = re.sub(r"\s*location_id\s*,\s*", " ", cols)
        cols2 = re.sub(r",\s*location_id\s*(,)?", lambda mm: "," if mm.group(1) else "", cols2)
        cols2 = re.sub(r"\s+", " ", cols2).strip()
        return f"INSERT INTO batches ({cols2})"

    text = re.sub(
        r"INSERT\s+INTO\s+batches\s*\((?P<cols>[^)]+)\)",
        drop_loc_from_batches_cols,
        text,
        flags=re.IGNORECASE,
    )

    # 2) batches 的 ON CONFLICT (...) 去掉 location_id
    def drop_loc_from_conflict_cols(m: re.Match) -> str:
        cols = m.group("cols")
        cols2 = re.sub(r"\s*location_id\s*,\s*", " ", cols)
        cols2 = re.sub(r",\s*location_id\s*(,)?", lambda mm: "," if mm.group(1) else "", cols2)
        cols2 = re.sub(r"\s+", " ", cols2).strip()
        return f"ON CONFLICT ({cols2})"

    text = re.sub(
        r"ON\s+CONFLICT\s*\((?P<cols>[^)]+)\)",
        drop_loc_from_conflict_cols,
        text,
        flags=re.IGNORECASE,
    )

    # 3) 针对 batches 的 WHERE 子句中，去掉 b.location_id 条件（若存在）
    text = re.sub(
        r"AND\s+b\.location_id\s*=\s*:loc\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"b\.location_id\s*=\s*:loc\s+AND",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # NOTE：stocks 相关先不自动动，避免把 item+loc 语义改坏；
    # 这块会在后续“位置→仓库聚合”设计里按文件单独改。

    return text

for rel in TARGET_FILES:
    path = ROOT / rel
    if not path.exists():
        continue
    old = path.read_text(encoding="utf-8")
    new = rewrite_sql(old)
    if new != old:
        print(f"[rewrite] {rel}")
        path.write_text(new, encoding="utf-8")
    else:
        print(f"[skip]    {rel} (no change)")

PY

echo
echo "[phase3] 批处理完成。建议立即查看 git diff："
echo "  git diff app/services tests/helpers tests/utils tests/db tests/services/phase34"
echo
echo "[phase3] 然后跑一轮："
echo "  ALEMBIC_CHECK_SCOPE=phase3 alembic check"
echo "  PYTHONPATH=. pytest -q -s tests/services/soft_reserve/ --forked"
