#!/usr/bin/env python3
# scripts/dev/ingest_platform_skus_to_mirror.py
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


@dataclass(frozen=True)
class MirrorIngestItem:
    platform: str
    shop_id: int
    platform_sku_id: str
    sku_name: Optional[str]
    spec: Optional[str]
    raw_payload: Optional[dict[str, Any]]
    source: str
    observed_at: datetime


def _parse_iso_datetime(s: str) -> datetime:
    """
    Accept ISO8601:
    - "2026-02-06T07:47:49Z"
    - "2026-02-06T07:47:49.123Z"
    - "2026-02-06T07:47:49+00:00"
    - "2026-02-06T07:47:49" (treated as UTC)
    """
    s2 = s.strip()
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_dict(x: Any) -> Optional[dict[str, Any]]:
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    raise ValueError(f"raw_payload must be object/dict or null, got: {type(x).__name__}")


def _load_items(path: Path, *, default_source: str) -> list[MirrorIngestItem]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Input JSON must be a list of objects")

    items: list[MirrorIngestItem] = []
    for idx, obj in enumerate(raw):
        if not isinstance(obj, dict):
            raise ValueError(f"Item[{idx}] must be object/dict, got: {type(obj).__name__}")

        platform = obj.get("platform")
        shop_id = obj.get("shop_id")
        platform_sku_id = obj.get("platform_sku_id")

        if not isinstance(platform, str) or not platform:
            raise ValueError(f"Item[{idx}].platform must be non-empty string")
        if not isinstance(shop_id, int):
            raise ValueError(f"Item[{idx}].shop_id must be int")
        if not isinstance(platform_sku_id, str) or not platform_sku_id:
            raise ValueError(f"Item[{idx}].platform_sku_id must be non-empty string")

        sku_name = obj.get("sku_name")
        spec = obj.get("spec")

        if sku_name is not None and not isinstance(sku_name, str):
            raise ValueError(f"Item[{idx}].sku_name must be string or null")
        if spec is not None and not isinstance(spec, str):
            raise ValueError(f"Item[{idx}].spec must be string or null")

        raw_payload = _ensure_dict(obj.get("raw_payload"))

        source = obj.get("source") or default_source
        if not isinstance(source, str) or not source:
            raise ValueError(f"Item[{idx}].source must be non-empty string")

        observed_at_raw = obj.get("observed_at")
        if observed_at_raw is None:
            observed_at = datetime.now(timezone.utc)
        else:
            if not isinstance(observed_at_raw, str):
                raise ValueError(f"Item[{idx}].observed_at must be ISO string or null")
            observed_at = _parse_iso_datetime(observed_at_raw)

        items.append(
            MirrorIngestItem(
                platform=platform,
                shop_id=shop_id,
                platform_sku_id=platform_sku_id,
                sku_name=sku_name,
                spec=spec,
                raw_payload=raw_payload,
                source=source,
                observed_at=observed_at,
            )
        )

    return items


def _chunk(seq: Sequence[MirrorIngestItem], n: int) -> list[list[MirrorIngestItem]]:
    out: list[list[MirrorIngestItem]] = []
    buf: list[MirrorIngestItem] = []
    for it in seq:
        buf.append(it)
        if len(buf) >= n:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest platform SKUs into platform_sku_mirror (UPSERT).")
    ap.add_argument("--file", required=True, help="Path to JSON file (list of mirror items).")
    ap.add_argument("--source", default="manual_file", help="Default source if item.source missing.")
    ap.add_argument("--batch", type=int, default=200, help="Commit every N rows (default: 200).")
    ap.add_argument("--dry-run", action="store_true", help="Validate and print summary, but do not write DB.")
    ap.add_argument(
        "--dsn",
        default=None,
        help="Override DB DSN for this process (sets WMS_DATABASE_URL/WMS_TEST_DATABASE_URL).",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="Delete mirror rows for keys in input file before ingest (same DB).",
    )
    ap.add_argument(
        "--clean-only",
        action="store_true",
        help="Only clean mirror rows for keys in input file, do not ingest.",
    )
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"file not found: {path}")

    # Optional DSN override MUST happen before importing app/db modules,
    # otherwise SessionLocal/engine may already be bound to previous env.
    if args.dsn:
        dsn = args.dsn.strip()
        os.environ["WMS_DATABASE_URL"] = dsn
        os.environ["WMS_TEST_DATABASE_URL"] = dsn
        mode = "TEST (wms_test) ✅" if "wms_test" in dsn else "DEV / OTHER ⚠️  (CHECK!)"
        print("[ingest] DSN override enabled")
        print(f"[ingest]   WMS_DATABASE_URL      = {dsn}")
        print(f"[ingest]   WMS_TEST_DATABASE_URL = {dsn}")
        print(f"[ingest]   MODE = {mode}")

    # Delayed imports: ensure DSN override (if any) takes effect.
    from sqlalchemy import text  # noqa: WPS433

    from app.db.session import SessionLocal  # noqa: WPS433
    from app.services.platform_sku_mirror_service import PlatformSkuMirrorService  # noqa: WPS433

    items = _load_items(path, default_source=args.source)
    print(
        f"[ingest] items={len(items)} dry_run={args.dry_run} clean={args.clean} clean_only={args.clean_only} batch={args.batch}"
    )

    if args.dry_run:
        for i, it in enumerate(items[:3]):
            print(f"[sample#{i}] {it.platform} {it.shop_id} {it.platform_sku_id} sku_name={it.sku_name!r}")
        return 0

    db = SessionLocal()
    try:
        if args.clean or args.clean_only:
            deleted = 0
            for it in items:
                res = db.execute(
                    text(
                        """
                        delete from platform_sku_mirror
                        where platform=:platform and shop_id=:shop_id and platform_sku_id=:platform_sku_id
                        """
                    ),
                    {
                        "platform": it.platform,
                        "shop_id": it.shop_id,
                        "platform_sku_id": it.platform_sku_id,
                    },
                )
                deleted += int(getattr(res, "rowcount", 0) or 0)
            db.commit()
            print(f"[ingest] clean done: deleted={deleted}")

            if args.clean_only:
                return 0

        svc = PlatformSkuMirrorService(db)
        written = 0
        for group in _chunk(items, max(1, args.batch)):
            for it in group:
                svc.upsert(
                    platform=it.platform,
                    shop_id=it.shop_id,
                    platform_sku_id=it.platform_sku_id,
                    sku_name=it.sku_name,
                    spec=it.spec,
                    raw_payload=it.raw_payload,
                    source=it.source,
                    observed_at=it.observed_at,
                )
                written += 1
            db.commit()
            print(f"[ingest] committed {written}/{len(items)}")

        print(f"[ingest] done: written={written}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
