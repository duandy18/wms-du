# app/pms/items/repos/item_list_repo.py
from __future__ import annotations

from typing import Any, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def list_item_list_row_mappings(
    db: Session,
    *,
    enabled: Optional[bool] = None,
    supplier_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = 200,
) -> list[Mapping[str, Any]]:
    """
    商品列表页 owner 聚合读。

    真相来源：
    - items：商品身份、策略、启停
    - pms_brands / pms_business_categories：品牌分类展示投影
    - suppliers：供应商展示投影
    - item_barcodes：主条码与条码数量
    - item_uoms：基础包装、采购默认包装、净重、包装数量
    - item_sku_codes：SKU 编码数量
    - item_attribute_values：属性值数量
    """

    conditions: list[str] = []
    params: dict[str, Any] = {
        "limit": max(1, min(int(limit or 200), 500)),
    }

    if enabled is not None:
        conditions.append("i.enabled = :enabled")
        params["enabled"] = bool(enabled)

    if supplier_id is not None:
        conditions.append("i.supplier_id = :supplier_id")
        params["supplier_id"] = int(supplier_id)

    qv = (q or "").strip()
    if qv:
        conditions.append(
            """
            (
              lower(i.sku) LIKE :q_like
              OR lower(i.name) LIKE :q_like
              OR lower(COALESCE(i.spec, '')) LIKE :q_like
              OR lower(COALESCE(s.name, '')) LIKE :q_like
              OR lower(COALESCE(br.name_cn, '')) LIKE :q_like
              OR lower(COALESCE(cat.category_name, '')) LIKE :q_like
              OR lower(COALESCE(pb.barcode, '')) LIKE :q_like
            )
            """
        )
        params["q_like"] = f"%{qv.lower()}%"

    where_sql = ""
    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    sql = f"""
    WITH base_uom AS (
      SELECT DISTINCT ON (u.item_id)
        u.item_id,
        u.uom,
        u.net_weight_kg
      FROM item_uoms u
      WHERE u.is_base IS TRUE
      ORDER BY u.item_id, u.id ASC
    ),
    purchase_uom AS (
      SELECT DISTINCT ON (u.item_id)
        u.item_id,
        u.uom,
        u.ratio_to_base
      FROM item_uoms u
      WHERE u.is_purchase_default IS TRUE
      ORDER BY u.item_id, u.id ASC
    ),
    primary_barcode AS (
      SELECT DISTINCT ON (b.item_id)
        b.item_id,
        b.barcode
      FROM item_barcodes b
      WHERE b.active IS TRUE
        AND b.is_primary IS TRUE
      ORDER BY b.item_id, b.id ASC
    ),
    uom_counts AS (
      SELECT item_id, COUNT(*)::int AS cnt
      FROM item_uoms
      GROUP BY item_id
    ),
    barcode_counts AS (
      SELECT item_id, COUNT(*)::int AS cnt
      FROM item_barcodes
      WHERE active IS TRUE
      GROUP BY item_id
    ),
    sku_code_counts AS (
      SELECT item_id, COUNT(*)::int AS cnt
      FROM item_sku_codes
      WHERE is_active IS TRUE
      GROUP BY item_id
    ),
    attribute_counts AS (
      SELECT item_id, COUNT(*)::int AS cnt
      FROM item_attribute_values
      GROUP BY item_id
    )
    SELECT
      i.id::int AS item_id,
      i.sku,
      i.name,
      i.spec,
      i.enabled,

      br.name_cn AS brand,
      cat.category_name AS category,
      s.name AS supplier_name,

      pb.barcode AS primary_barcode,

      bu.uom AS base_uom,
      bu.net_weight_kg AS base_net_weight_kg,

      pu.uom AS purchase_uom,
      pu.ratio_to_base::int AS purchase_ratio_to_base,

      i.lot_source_policy::text AS lot_source_policy,
      i.expiry_policy::text AS expiry_policy,
      i.shelf_life_value,
      i.shelf_life_unit::text AS shelf_life_unit,

      COALESCE(uc.cnt, 0)::int AS uom_count,
      COALESCE(bc.cnt, 0)::int AS barcode_count,
      COALESCE(sc.cnt, 0)::int AS sku_code_count,
      COALESCE(ac.cnt, 0)::int AS attribute_count,

      i.updated_at
    FROM items i
    LEFT JOIN pms_brands br
      ON br.id = i.brand_id
    LEFT JOIN pms_business_categories cat
      ON cat.id = i.category_id
    LEFT JOIN suppliers s
      ON s.id = i.supplier_id
    LEFT JOIN base_uom bu
      ON bu.item_id = i.id
    LEFT JOIN purchase_uom pu
      ON pu.item_id = i.id
    LEFT JOIN primary_barcode pb
      ON pb.item_id = i.id
    LEFT JOIN uom_counts uc
      ON uc.item_id = i.id
    LEFT JOIN barcode_counts bc
      ON bc.item_id = i.id
    LEFT JOIN sku_code_counts sc
      ON sc.item_id = i.id
    LEFT JOIN attribute_counts ac
      ON ac.item_id = i.id
    {where_sql}
    ORDER BY i.updated_at DESC NULLS LAST, i.id DESC
    LIMIT :limit
    """

    rows = db.execute(text(sql), params).mappings().all()
    return list(rows)
