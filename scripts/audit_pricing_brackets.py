#!/usr/bin/env python3
from __future__ import annotations

import os
from sqlalchemy import create_engine, text


def _is_truthy(v: str | None) -> bool:
    if v is None:
        return False
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def main() -> None:
    dsn = os.environ.get("WMS_DATABASE_URL") or os.environ.get("WMS_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("[audit-pricing-brackets] FAIL: WMS_DATABASE_URL not set")

    # 默认：过滤 UT-/TEST-（避免测试基线数据拖死 audit）
    # 严格模式：AUDIT_PRICING_INCLUDE_TEST=1 则不过滤
    include_test = _is_truthy(os.environ.get("AUDIT_PRICING_INCLUDE_TEST"))

    engine = create_engine(dsn, future=True)

    where_extra = ""
    if not include_test:
        where_extra = " AND sch.name NOT LIKE 'UT-%' AND sch.name NOT LIKE 'TEST-%' "

    sql = text(
        f"""
        SELECT
          sch.id AS scheme_id,
          sch.shipping_provider_id AS provider_id,
          sch.name AS scheme_name,
          z.id AS zone_id,
          z.name AS zone_name,
          COUNT(*) FILTER (WHERE b.active) AS active_brackets,
          COUNT(*) FILTER (WHERE b.active AND b.max_kg IS NULL) AS active_inf_brackets
        FROM shipping_provider_pricing_schemes sch
        JOIN shipping_provider_zones z
          ON z.scheme_id = sch.id
        LEFT JOIN shipping_provider_zone_brackets b
          ON b.zone_id = z.id
        WHERE sch.active = true
        {where_extra}
        GROUP BY sch.id, sch.shipping_provider_id, sch.name, z.id, z.name
        ORDER BY sch.id, z.id
        """
    )

    bad: list[dict] = []

    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
        for r in rows:
            ab = int(r["active_brackets"] or 0)
            ainf = int(r["active_inf_brackets"] or 0)
            if ab <= 0 or ainf <= 0:
                bad.append(
                    {
                        "scheme_id": int(r["scheme_id"]),
                        "provider_id": int(r["provider_id"]),
                        "scheme_name": str(r["scheme_name"]),
                        "zone_id": int(r["zone_id"]),
                        "zone_name": str(r["zone_name"]),
                        "active_brackets": ab,
                        "active_inf_brackets": ainf,
                    }
                )

    if not rows:
        if include_test:
            print("[audit-pricing-brackets] OK (no active schemes/zones found)")
        else:
            print("[audit-pricing-brackets] OK (no active production-like schemes/zones found)")
        return

    if bad:
        print("[audit-pricing-brackets] FAIL: zones missing active brackets or missing inf bracket (max_kg IS NULL)")
        print(f"[audit-pricing-brackets] include_test={include_test}")
        for it in bad[:50]:
            print(it)
        raise SystemExit(1)

    print(f"[audit-pricing-brackets] OK (include_test={include_test})")


if __name__ == "__main__":
    main()
