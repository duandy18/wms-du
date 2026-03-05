#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# ✅ 无论从哪里运行脚本，都确保可 import `app.*`
# scripts/export_openapi.py -> repo root 是 parents[1]
REPO_ROOT = Path(__file__).resolve().parents[1]


def _ensure_repo_root() -> None:
    """
    让脚本具有“从任意工作目录执行都稳定”的特性：
    - 把 repo root 插入 sys.path，保证 `import app` 可用
    - 把 cwd 切到 repo root，保证相对路径（如 openapi/_current.json）落在仓库内
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    os.chdir(REPO_ROOT)


def _build_app(enable_dev_routes: bool) -> Any:
    """
    通过 import app.main 来构建 FastAPI app（不需要启动服务）。

    关键点：
    - app/main.py 在 import 时会 mount_routers(app, enable_dev_routes=...)
    - enable_dev_routes 由环境变量 WMS_ENV / WMS_ENABLE_DEV_ROUTES 控制
    """
    _ensure_repo_root()

    # 统一显式设置，避免不同机器“环境变量缺失导致契约漂移”
    os.environ.setdefault("WMS_ENV", "dev")
    os.environ.setdefault("PYTEST_RUNNING", "0")
    os.environ.setdefault("WMS_DUMP_ROUTES", "0")
    os.environ["WMS_ENABLE_DEV_ROUTES"] = "1" if enable_dev_routes else "0"

    from app.main import app  # noqa: WPS433 (import inside func is intentional)

    return app


def export_openapi(out_path: Path, enable_dev_routes: bool) -> None:
    app = _build_app(enable_dev_routes=enable_dev_routes)
    spec: Dict[str, Any] = app.openapi()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 为了 git diff 稳定：sort_keys + indent
    out_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to a json file.")
    p.add_argument(
        "--out",
        default="openapi/_current.json",
        help="Output path for OpenAPI json (default: openapi/_current.json)",
    )
    p.add_argument(
        "--enable-dev-routes",
        action="store_true",
        help="Include /dev/* routes in the exported OpenAPI.",
    )
    args = p.parse_args()

    export_openapi(Path(args.out), enable_dev_routes=bool(args.enable_dev_routes))
    print(f"exported: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
