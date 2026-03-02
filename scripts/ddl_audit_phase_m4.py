#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from datetime import datetime

DSN = "postgres://wms:wms@127.0.0.1:5433/wms"
OUT_DIR = "artifacts/ddl_audit/phase_m4"

TABLES = [
    "items",
    "item_barcodes",
    "item_uoms",
    "lots",
    "purchase_orders",
    "purchase_order_lines",
    "inbound_receipts",
    "inbound_receipt_lines",
    "stock_ledger",
    "stocks_lot",
    "stock_snapshots",
]

def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.stdout

def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    meta = []
    meta.append("# ddl_audit baseline")
    meta.append(f"# generated_at: {datetime.now().isoformat()}")
    meta.append(f"# dsn: {DSN}")
    try:
        ver = run(["psql", DSN, "-XAtc", "select version();"])
        meta.append("# db_version:")
        meta.append(ver.strip())
    except Exception as e:
        meta.append(f"# db_version: <failed> {e}")

    with open(os.path.join(OUT_DIR, "_meta.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(meta) + "\n")

    for t in TABLES:
        print(f"[ddl_audit] exporting \\d+ {t} ...")
        out = run(["psql", DSN, "-X", "-v", "ON_ERROR_STOP=1", "-c", f"\\d+ {t}"])
        with open(os.path.join(OUT_DIR, f"{t}.ddl.txt"), "w", encoding="utf-8") as f:
            f.write(out)

    print(f"[ddl_audit] done -> {OUT_DIR}")

if __name__ == "__main__":
    main()
