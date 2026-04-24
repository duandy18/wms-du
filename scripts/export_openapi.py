# scripts/export_openapi.py
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# scripts/export_openapi.py -> repo root 是 parents[1]
ROOT = Path(__file__).resolve().parents[1]


def _build_app() -> Any:
    """
    构建 FastAPI app 并导出正式 OpenAPI。

    注意：
    - devtools 已退役；
    - 不再支持 --enable-dev-routes；
    - 不再设置 WMS_ENABLE_DEV_ROUTES；
    - 把 cwd 切到 repo root，保证相对路径落在仓库内。
    """
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app.main import app

    return app


def export_openapi(out_path: Path) -> None:
    app = _build_app()
    spec: Dict[str, Any] = app.openapi()

    target = out_path
    if not target.is_absolute():
        target = ROOT / target

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        shown = target.relative_to(ROOT)
    except ValueError:
        shown = target
    print(f"exported: {shown}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export backend OpenAPI schema.")
    parser.add_argument(
        "--out",
        default="openapi/_current.json",
        help="Output path for OpenAPI json (default: openapi/_current.json)",
    )
    args = parser.parse_args()

    export_openapi(Path(args.out))


if __name__ == "__main__":
    main()
