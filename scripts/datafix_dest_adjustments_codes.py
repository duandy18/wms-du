# scripts/datafix_dest_adjustments_codes.py
from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from app.geo.cn_registry import resolve_city, resolve_province

DSN = os.environ.get("DEV_DB_DSN") or "postgresql+psycopg://wms:wms@127.0.0.1:5433/wms"


def main() -> None:
    eng = create_engine(DSN)
    with eng.begin() as conn:
        rows = conn.execute(
            text(
                """
                select id, scope, province_code, city_code, province_name, city_name, province, city
                from pricing_scheme_dest_adjustments
                order by id asc
                """
            )
        ).mappings().all()

        updated = 0
        skipped = 0

        for r in rows:
            pid = int(r["id"])
            scope = (r["scope"] or "").strip().lower()

            prov_name = (r["province_name"] or r["province"] or "").strip()
            city_name = (r["city_name"] or r["city"] or "").strip()

            prov_item = resolve_province(code=None, name=prov_name)
            if prov_item is None:
                skipped += 1
                print(f"[SKIP] id={pid} province_name={prov_name!r} (cannot resolve)")
                continue

            if scope == "province":
                # city must be null
                conn.execute(
                    text(
                        """
                        update pricing_scheme_dest_adjustments
                        set province_code = :pc,
                            province_name = :pn,
                            city_code = null,
                            city_name = null
                        where id = :id
                        """
                    ),
                    {"id": pid, "pc": prov_item.code, "pn": prov_item.name},
                )
                updated += 1
                continue

            if scope == "city":
                city_item = resolve_city(province_code=prov_item.code, code=None, name=city_name)
                if city_item is None:
                    skipped += 1
                    print(f"[SKIP] id={pid} province={prov_item.code} city_name={city_name!r} (cannot resolve)")
                    continue

                conn.execute(
                    text(
                        """
                        update pricing_scheme_dest_adjustments
                        set province_code = :pc,
                            province_name = :pn,
                            city_code = :cc,
                            city_name = :cn
                        where id = :id
                        """
                    ),
                    {"id": pid, "pc": prov_item.code, "pn": prov_item.name, "cc": city_item.code, "cn": city_item.name},
                )
                updated += 1
                continue

            skipped += 1
            print(f"[SKIP] id={pid} scope={scope!r} (invalid scope)")

        print(f"done. updated={updated} skipped={skipped}")


if __name__ == "__main__":
    main()
