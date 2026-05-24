# app/pms/projections/repos/pms_projection_repo.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pms.projections.contracts.pms_projection import ProjectionResource


@dataclass(frozen=True)
class ProjectionResourceConfig:
    resource: ProjectionResource
    table_name: str
    id_column: str
    columns: tuple[str, ...]
    searchable_columns: tuple[str, ...]
    select_expressions: tuple[str, ...] | None = None
    from_sql: str | None = None
    order_by_sql: str | None = None


RESOURCE_CONFIGS: dict[ProjectionResource, ProjectionResourceConfig] = {
    "items": ProjectionResourceConfig(
        resource="items",
        table_name="wms_pms_item_projection",
        id_column="item_id",
        columns=(
            "item_id",
            "sku",
            "name",
            "spec",
            "enabled",
            "supplier_id",
            "supplier_code",
            "supplier_name",
            "brand",
            "category",
            "expiry_policy",
            "shelf_life_value",
            "shelf_life_unit",
            "lot_source_policy",
            "derivation_allowed",
            "uom_governance_enabled",
            "pms_updated_at",
            "source_hash",
            "sync_version",
            "synced_at",
        ),
        searchable_columns=(
            "i.sku",
            "i.name",
            "i.spec",
            "i.brand",
            "i.category",
            "s.supplier_code",
            "s.supplier_name",
        ),
        select_expressions=(
            "i.item_id",
            "i.sku",
            "i.name",
            "i.spec",
            "i.enabled",
            "i.supplier_id",
            "s.supplier_code AS supplier_code",
            "s.supplier_name AS supplier_name",
            "i.brand",
            "i.category",
            "i.expiry_policy",
            "i.shelf_life_value",
            "i.shelf_life_unit",
            "i.lot_source_policy",
            "i.derivation_allowed",
            "i.uom_governance_enabled",
            "i.pms_updated_at",
            "i.source_hash",
            "i.sync_version",
            "i.synced_at",
        ),
        from_sql=(
            "wms_pms_item_projection AS i "
            "LEFT JOIN wms_pms_supplier_projection AS s "
            "ON s.supplier_id = i.supplier_id"
        ),
        order_by_sql="i.item_id ASC",
    ),
    "suppliers": ProjectionResourceConfig(
        resource="suppliers",
        table_name="wms_pms_supplier_projection",
        id_column="supplier_id",
        columns=(
            "supplier_id",
            "supplier_code",
            "supplier_name",
            "active",
            "website",
            "pms_updated_at",
            "source_hash",
            "sync_version",
            "synced_at",
        ),
        searchable_columns=("supplier_code", "supplier_name", "website"),
    ),
    "uoms": ProjectionResourceConfig(
        resource="uoms",
        table_name="wms_pms_uom_projection",
        id_column="item_uom_id",
        columns=(
            "item_uom_id",
            "item_id",
            "uom",
            "display_name",
            "uom_name",
            "ratio_to_base",
            "net_weight_kg",
            "is_base",
            "is_purchase_default",
            "is_inbound_default",
            "is_outbound_default",
            "pms_updated_at",
            "source_hash",
            "sync_version",
            "synced_at",
        ),
        searchable_columns=("uom", "display_name", "uom_name"),
    ),
    "sku-codes": ProjectionResourceConfig(
        resource="sku-codes",
        table_name="wms_pms_sku_code_projection",
        id_column="sku_code_id",
        columns=(
            "sku_code_id",
            "item_id",
            "sku_code",
            "code_type",
            "is_primary",
            "is_active",
            "effective_from",
            "effective_to",
            "pms_updated_at",
            "source_hash",
            "sync_version",
            "synced_at",
        ),
        searchable_columns=("sku_code", "code_type"),
    ),
    "barcodes": ProjectionResourceConfig(
        resource="barcodes",
        table_name="wms_pms_barcode_projection",
        id_column="barcode_id",
        columns=(
            "barcode_id",
            "item_id",
            "item_uom_id",
            "barcode",
            "symbology",
            "active",
            "is_primary",
            "pms_updated_at",
            "source_hash",
            "sync_version",
            "synced_at",
        ),
        searchable_columns=("barcode", "symbology"),
    ),
}

RESOURCE_ORDER: tuple[ProjectionResource, ...] = (
    "items",
    "suppliers",
    "uoms",
    "sku-codes",
    "barcodes",
)


class PmsProjectionRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def config(resource: ProjectionResource) -> ProjectionResourceConfig:
        try:
            return RESOURCE_CONFIGS[resource]
        except KeyError as exc:
            raise ValueError(f"unsupported PMS projection resource: {resource}") from exc

    @staticmethod
    def jsonable(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        return value

    @staticmethod
    def select_sql(cfg: ProjectionResourceConfig) -> str:
        return ", ".join(cfg.select_expressions or cfg.columns)

    @staticmethod
    def from_sql(cfg: ProjectionResourceConfig) -> str:
        return cfg.from_sql or cfg.table_name

    @staticmethod
    def order_by_sql(cfg: ProjectionResourceConfig) -> str:
        return cfg.order_by_sql or f"{cfg.id_column} ASC"

    @staticmethod
    def sync_run_from_row(row: Any) -> dict[str, Any]:
        data = dict(row)
        return {
            "id": int(data["id"]),
            "resource": str(data["resource"]),
            "status": str(data["status"]),
            "fetched": int(data.get("fetched") or 0),
            "upserted": int(data.get("upserted") or 0),
            "pages": int(data.get("pages") or 0),
            "started_at": data["started_at"],
            "finished_at": data.get("finished_at"),
            "duration_ms": (
                int(data["duration_ms"]) if data.get("duration_ms") is not None else None
            ),
            "error_message": data.get("error_message"),
            "triggered_by_user_id": (
                int(data["triggered_by_user_id"])
                if data.get("triggered_by_user_id") is not None
                else None
            ),
            "pms_api_base_url_snapshot": data.get("pms_api_base_url_snapshot"),
            "sync_version": data.get("sync_version"),
        }

    def latest_sync_runs(self) -> dict[str, dict[str, Any]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT DISTINCT ON (resource)
                        id,
                        resource,
                        status,
                        fetched,
                        upserted,
                        pages,
                        started_at,
                        finished_at,
                        duration_ms,
                        error_message,
                        triggered_by_user_id,
                        pms_api_base_url_snapshot,
                        sync_version
                    FROM wms_pms_projection_sync_runs
                    WHERE resource IN ('items', 'suppliers', 'uoms', 'sku-codes', 'barcodes')
                    ORDER BY resource, started_at DESC, id DESC
                    """
                )
            )
            .mappings()
            .all()
        )
        return {str(row["resource"]): self.sync_run_from_row(row) for row in rows}

    def resource_stats(self, cfg: ProjectionResourceConfig) -> dict[str, Any]:
        row = (
            self.db.execute(
                text(
                    f"""
                    SELECT
                        count(*)::bigint AS row_count,
                        max(synced_at) AS max_synced_at
                    FROM {cfg.table_name}
                    """
                )
            )
            .mappings()
            .one()
        )
        return {
            "row_count": int(row["row_count"] or 0),
            "max_synced_at": row["max_synced_at"],
        }

    def list_projection_rows(
        self,
        *,
        cfg: ProjectionResourceConfig,
        limit: int,
        offset: int,
        q: str | None,
    ) -> dict[str, Any]:
        where_sql = ""
        params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
        query_text = (q or "").strip()
        if query_text and cfg.searchable_columns:
            where_parts = [
                f"CAST({column} AS TEXT) ILIKE :q"
                for column in cfg.searchable_columns
            ]
            where_sql = "WHERE " + " OR ".join(where_parts)
            params["q"] = f"%{query_text}%"

        from_sql = self.from_sql(cfg)
        total = int(
            self.db.execute(
                text(f"SELECT count(*)::bigint FROM {from_sql} {where_sql}"),
                params,
            ).scalar_one()
        )

        rows = (
            self.db.execute(
                text(
                    f"""
                    SELECT {self.select_sql(cfg)}
                    FROM {from_sql}
                    {where_sql}
                    ORDER BY {self.order_by_sql(cfg)}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )

        return {
            "resource": cfg.resource,
            "table_name": cfg.table_name,
            "limit": int(limit),
            "offset": int(offset),
            "total": total,
            "columns": list(cfg.columns),
            "rows": [
                {key: self.jsonable(value) for key, value in dict(row).items()}
                for row in rows
            ],
        }

    def create_sync_run(
        self,
        *,
        resource: ProjectionResource,
        triggered_by_user_id: int | None,
        pms_api_base_url_snapshot: str | None,
        sync_version: str,
    ) -> int:
        row = (
            self.db.execute(
                text(
                    """
                    INSERT INTO wms_pms_projection_sync_runs (
                        resource,
                        status,
                        fetched,
                        upserted,
                        pages,
                        started_at,
                        triggered_by_user_id,
                        pms_api_base_url_snapshot,
                        sync_version
                    )
                    VALUES (
                        :resource,
                        'RUNNING',
                        0,
                        0,
                        0,
                        now(),
                        :triggered_by_user_id,
                        :pms_api_base_url_snapshot,
                        :sync_version
                    )
                    RETURNING id
                    """
                ),
                {
                    "resource": resource,
                    "triggered_by_user_id": triggered_by_user_id,
                    "pms_api_base_url_snapshot": pms_api_base_url_snapshot,
                    "sync_version": sync_version,
                },
            )
            .mappings()
            .one()
        )
        self.db.commit()
        return int(row["id"])

    def finish_sync_run(
        self,
        *,
        run_id: int,
        status: str,
        duration_ms: int,
        fetched: int = 0,
        upserted: int = 0,
        pages: int = 0,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        row = (
            self.db.execute(
                text(
                    """
                    UPDATE wms_pms_projection_sync_runs
                       SET status = :status,
                           fetched = :fetched,
                           upserted = :upserted,
                           pages = :pages,
                           finished_at = now(),
                           duration_ms = :duration_ms,
                           error_message = :error_message
                     WHERE id = :run_id
                    RETURNING
                        id,
                        resource,
                        status,
                        fetched,
                        upserted,
                        pages,
                        started_at,
                        finished_at,
                        duration_ms,
                        error_message,
                        triggered_by_user_id,
                        pms_api_base_url_snapshot,
                        sync_version
                    """
                ),
                {
                    "run_id": int(run_id),
                    "status": status,
                    "fetched": int(fetched),
                    "upserted": int(upserted),
                    "pages": int(pages),
                    "duration_ms": int(duration_ms),
                    "error_message": error_message,
                },
            )
            .mappings()
            .one()
        )
        self.db.commit()
        return self.sync_run_from_row(row)

    def list_sync_runs(
        self,
        *,
        resource: ProjectionResource | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": int(limit)}
        where_sql = ""
        if resource is not None:
            self.config(resource)
            where_sql = "WHERE resource = :resource"
            params["resource"] = resource

        rows = (
            self.db.execute(
                text(
                    f"""
                    SELECT
                        id,
                        resource,
                        status,
                        fetched,
                        upserted,
                        pages,
                        started_at,
                        finished_at,
                        duration_ms,
                        error_message,
                        triggered_by_user_id,
                        pms_api_base_url_snapshot,
                        sync_version
                    FROM wms_pms_projection_sync_runs
                    {where_sql}
                    ORDER BY started_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [self.sync_run_from_row(row) for row in rows]

    def check_items(self, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT
                        i.item_id,
                        i.supplier_id
                    FROM wms_pms_item_projection AS i
                    LEFT JOIN wms_pms_supplier_projection AS s
                      ON s.supplier_id = i.supplier_id
                    WHERE i.supplier_id IS NOT NULL
                      AND s.supplier_id IS NULL
                    ORDER BY i.item_id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            )
            .mappings()
            .all()
        )
        return [
            {
                "issue_type": "ITEM_SUPPLIER_MISSING_IN_PROJECTION",
                "resource": "items",
                "source_id": str(row["item_id"]),
                "message": "商品投影中的 supplier_id 在供应商投影中不存在",
                "item_id": int(row["item_id"]),
                "supplier_id": int(row["supplier_id"]),
            }
            for row in rows
        ]

    def check_suppliers(self, limit: int) -> list[dict[str, Any]]:
        _ = limit
        return []

    def check_uoms(self, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT
                        u.item_uom_id,
                        u.item_id
                    FROM wms_pms_uom_projection AS u
                    LEFT JOIN wms_pms_item_projection AS i
                      ON i.item_id = u.item_id
                    WHERE i.item_id IS NULL
                    ORDER BY u.item_uom_id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            )
            .mappings()
            .all()
        )
        return [
            {
                "issue_type": "UOM_ITEM_MISSING_IN_PROJECTION",
                "resource": "uoms",
                "source_id": str(row["item_uom_id"]),
                "message": "包装单位投影中的 item_id 在商品投影中不存在",
                "item_id": int(row["item_id"]),
                "item_uom_id": int(row["item_uom_id"]),
            }
            for row in rows
        ]

    def check_sku_codes(self, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT
                        s.sku_code_id,
                        s.item_id
                    FROM wms_pms_sku_code_projection AS s
                    LEFT JOIN wms_pms_item_projection AS i
                      ON i.item_id = s.item_id
                    WHERE i.item_id IS NULL
                    ORDER BY s.sku_code_id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            )
            .mappings()
            .all()
        )
        return [
            {
                "issue_type": "SKU_CODE_ITEM_MISSING_IN_PROJECTION",
                "resource": "sku-codes",
                "source_id": str(row["sku_code_id"]),
                "message": "SKU 编码投影中的 item_id 在商品投影中不存在",
                "item_id": int(row["item_id"]),
            }
            for row in rows
        ]

    def check_barcodes(self, limit: int) -> list[dict[str, Any]]:
        rows = (
            self.db.execute(
                text(
                    """
                    SELECT
                        b.barcode_id,
                        b.item_id,
                        b.item_uom_id,
                        u.item_id AS projection_item_id,
                        CASE
                          WHEN i.item_id IS NULL THEN 'BARCODE_ITEM_MISSING_IN_PROJECTION'
                          WHEN u.item_uom_id IS NULL THEN 'BARCODE_UOM_MISSING_IN_PROJECTION'
                          WHEN u.item_id <> b.item_id THEN 'BARCODE_UOM_ITEM_MISMATCH'
                          ELSE 'OK'
                        END AS issue_type
                    FROM wms_pms_barcode_projection AS b
                    LEFT JOIN wms_pms_item_projection AS i
                      ON i.item_id = b.item_id
                    LEFT JOIN wms_pms_uom_projection AS u
                      ON u.item_uom_id = b.item_uom_id
                    WHERE i.item_id IS NULL
                       OR u.item_uom_id IS NULL
                       OR u.item_id <> b.item_id
                    ORDER BY b.barcode_id ASC
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            )
            .mappings()
            .all()
        )

        messages = {
            "BARCODE_ITEM_MISSING_IN_PROJECTION": "条码投影中的 item_id 在商品投影中不存在",
            "BARCODE_UOM_MISSING_IN_PROJECTION": "条码投影中的 item_uom_id 在包装单位投影中不存在",
            "BARCODE_UOM_ITEM_MISMATCH": "条码投影中的 item_id 与包装单位投影所属 item_id 不一致",
        }
        return [
            {
                "issue_type": str(row["issue_type"]),
                "resource": "barcodes",
                "source_id": str(row["barcode_id"]),
                "message": messages.get(str(row["issue_type"]), "条码投影一致性异常"),
                "item_id": int(row["item_id"]),
                "item_uom_id": int(row["item_uom_id"]),
                "projection_item_id": (
                    int(row["projection_item_id"])
                    if row["projection_item_id"] is not None
                    else None
                ),
            }
            for row in rows
        ]


__all__ = [
    "PmsProjectionRepo",
    "ProjectionResourceConfig",
    "RESOURCE_CONFIGS",
    "RESOURCE_ORDER",
]
