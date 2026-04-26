"""oms store code naming cutover

Revision ID: 28e74f19a54f
Revises: 'ecd37dd41170'
Create Date: generated

终态口径：
- store_id    = 本系统内部主键，stores.id
- store_code  = 平台店铺编码 / 平台店铺号，来源于平台
- store_name  = 平台店铺名称，来源于平台

本迁移不做 shop/store 双轨兼容：
- 旧 stores.shop_id 的值迁移为 stores.store_code
- 旧 stores.name 迁移为 stores.store_name
- 旧 stores.store_code 的 Sxxx 内部编码废弃
- platform_test_shops 改为 platform_test_stores
- 核心事实表 shop_id 改为 store_code
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "28e74f19a54f"
down_revision: Union[str, Sequence[str], None] = 'ecd37dd41170'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _exec(sql: str) -> None:
    op.execute(sa.text(sql))


def _col_exists(conn, table: str, column: str) -> bool:
    return (
        conn.execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema = 'public'
                   AND table_name = :table
                   AND column_name = :column
                 LIMIT 1
                """
            ),
            {"table": table, "column": column},
        ).first()
        is not None
    )


def _table_exists(conn, table: str) -> bool:
    return (
        conn.execute(
            sa.text(
                """
                SELECT 1
                  FROM information_schema.tables
                 WHERE table_schema = 'public'
                   AND table_name = :table
                 LIMIT 1
                """
            ),
            {"table": table},
        ).first()
        is not None
    )


def _rename_column(conn, table: str, old: str, new: str) -> None:
    if _table_exists(conn, table) and _col_exists(conn, table, old) and not _col_exists(conn, table, new):
        _exec(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')


def _drop_column_if_exists(conn, table: str, column: str) -> None:
    if _table_exists(conn, table) and _col_exists(conn, table, column):
        _exec(f'ALTER TABLE "{table}" DROP COLUMN "{column}"')


def upgrade() -> None:
    conn = op.get_bind()

    # ---------------------------------------------------------------------
    # 0) 先移除依赖 stores / orders 旧列的视图。
    # PostgreSQL 不允许 ALTER 被 view/rule 依赖的列，因此必须在触发表/列改名前 drop。
    # 后面会按 store_code 终态重新创建该 view。
    # ---------------------------------------------------------------------
    _exec("DROP VIEW IF EXISTS vw_routing_metrics_daily")

    # ---------------------------------------------------------------------
    # 1) 先移除依赖旧 stores.shop_id / stores.name 的触发器与函数
    # ---------------------------------------------------------------------
    _exec("DROP TRIGGER IF EXISTS trg_fsc_lines_store_refresh ON stores")
    _exec("DROP TRIGGER IF EXISTS trg_stores_store_code_default ON stores")
    _exec("DROP FUNCTION IF EXISTS trg_stores_store_code_default()")
    _exec("DROP FUNCTION IF EXISTS finance_trg_shipping_cost_store_refresh()")
    _exec("DROP FUNCTION IF EXISTS finance_refresh_shipping_cost_line(bigint)")

    # ---------------------------------------------------------------------
    # 1) stores：旧 shop_id -> 新 store_code；旧 name -> 新 store_name
    #    旧 store_code 是 Sxxx 内部码，终态废弃
    # ---------------------------------------------------------------------
    if _table_exists(conn, "stores"):
        _exec("ALTER TABLE stores DROP CONSTRAINT IF EXISTS uq_stores_platform_shop")
        _exec("ALTER TABLE stores DROP CONSTRAINT IF EXISTS uq_stores_platform_store_code")
        _exec("DROP INDEX IF EXISTS ix_stores_shop")
        _exec("DROP INDEX IF EXISTS ix_stores_platform_name")
        _exec("DROP INDEX IF EXISTS ix_stores_platform_store_name")
        _exec("DROP INDEX IF EXISTS ix_stores_store_code")

        if _col_exists(conn, "stores", "shop_id") and _col_exists(conn, "stores", "store_code"):
            # 当前 store_code 多数是 Sxxx 内部码，不能保留为终态字段。
            _exec("ALTER TABLE stores DROP COLUMN store_code")

        _rename_column(conn, "stores", "shop_id", "store_code")
        _rename_column(conn, "stores", "name", "store_name")

        _exec(
            """
            ALTER TABLE stores
            ALTER COLUMN store_code TYPE varchar(128),
            ALTER COLUMN store_code SET NOT NULL
            """
        )
        _exec(
            """
            ALTER TABLE stores
            ALTER COLUMN store_name TYPE varchar(256),
            ALTER COLUMN store_name SET NOT NULL
            """
        )
        _exec(
            """
            ALTER TABLE stores
            ADD CONSTRAINT uq_stores_platform_store_code
            UNIQUE (platform, store_code)
            """
        )
        _exec("CREATE INDEX ix_stores_store_code ON stores (store_code)")
        _exec("CREATE INDEX ix_stores_platform_store_name ON stores (platform, store_name)")

    # ---------------------------------------------------------------------
    # 2) platform_test_shops -> platform_test_stores
    # ---------------------------------------------------------------------
    if _table_exists(conn, "platform_test_shops") and not _table_exists(conn, "platform_test_stores"):
        _exec("ALTER TABLE platform_test_shops RENAME TO platform_test_stores")

    if _table_exists(conn, "platform_test_stores"):
        _rename_column(conn, "platform_test_stores", "shop_id", "store_code")

        _exec(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_platform_test_shops_store_id'
              ) THEN
                ALTER TABLE platform_test_stores
                RENAME CONSTRAINT fk_platform_test_shops_store_id TO fk_platform_test_stores_store_id;
              END IF;
              IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_platform_test_shops_platform_code'
              ) THEN
                ALTER TABLE platform_test_stores
                RENAME CONSTRAINT uq_platform_test_shops_platform_code TO uq_platform_test_stores_platform_code;
              END IF;
              IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_platform_test_shops_store_id'
              ) THEN
                ALTER TABLE platform_test_stores
                RENAME CONSTRAINT uq_platform_test_shops_store_id TO uq_platform_test_stores_store_id;
              END IF;
            END $$;
            """
        )
        _exec("DROP INDEX IF EXISTS ix_platform_test_shops_platform_shop")
        _exec("DROP INDEX IF EXISTS ix_platform_test_stores_platform_store_code")
        _exec(
            """
            CREATE INDEX ix_platform_test_stores_platform_store_code
            ON platform_test_stores(platform, store_code)
            """
        )

    # platform_shops 当前不在主线，且空表；终态退役。
    _exec("DROP TABLE IF EXISTS platform_shops")

    # ---------------------------------------------------------------------
    # 3) 订单与平台订单事实
    # ---------------------------------------------------------------------
    if _table_exists(conn, "orders"):
        _exec("ALTER TABLE orders DROP CONSTRAINT IF EXISTS uq_orders_platform_shop_ext")
        _exec("DROP INDEX IF EXISTS ix_orders_platform_shop")
        _exec("DROP INDEX IF EXISTS ix_orders_platform_store")
        _rename_column(conn, "orders", "shop_id", "store_code")
        _exec(
            """
            COMMENT ON COLUMN orders.store_code IS '店铺 ID（字符串，与 stores.store_code 对齐）'
            """
        )
        _exec(
            """
            ALTER TABLE orders
            ADD CONSTRAINT uq_orders_platform_store_ext
            UNIQUE (platform, store_code, ext_order_no)
            """
        )
        _exec("CREATE INDEX ix_orders_platform_store ON orders(platform, store_code)")

    if _table_exists(conn, "platform_order_lines"):
        _exec("DROP INDEX IF EXISTS ux_platform_order_lines_key")
        _exec("DROP INDEX IF EXISTS ix_platform_order_lines_order")
        _rename_column(conn, "platform_order_lines", "shop_id", "store_code")
        _exec(
            """
            CREATE UNIQUE INDEX ux_platform_order_lines_key
            ON platform_order_lines(platform, store_code, ext_order_no, line_key)
            """
        )
        _exec(
            """
            CREATE INDEX ix_platform_order_lines_order
            ON platform_order_lines(platform, store_code, ext_order_no)
            """
        )

    if _table_exists(conn, "order_state_snapshot"):
        _exec("DROP INDEX IF EXISTS ix_order_state_snapshot_lookup")
        _rename_column(conn, "order_state_snapshot", "shop_id", "store_code")
        _exec(
            """
            CREATE UNIQUE INDEX ix_order_state_snapshot_lookup
            ON order_state_snapshot(platform, store_code, order_no)
            """
        )

    # ---------------------------------------------------------------------
    # 4) FSKU 商家编码绑定
    # ---------------------------------------------------------------------
    if _table_exists(conn, "merchant_code_fsku_bindings"):
        _exec("ALTER TABLE merchant_code_fsku_bindings DROP CONSTRAINT IF EXISTS ux_mc_fsku_bindings_unique")
        _exec("DROP INDEX IF EXISTS ix_mc_fsku_bindings_lookup")
        _exec("DROP INDEX IF EXISTS ux_mc_fsku_bindings_current")
        _rename_column(conn, "merchant_code_fsku_bindings", "shop_id", "store_code")
        _exec(
            """
            ALTER TABLE merchant_code_fsku_bindings
            ADD CONSTRAINT ux_mc_fsku_bindings_store_unique
            UNIQUE (platform, store_code, merchant_code)
            """
        )
        _exec(
            """
            CREATE INDEX ix_mc_fsku_bindings_store_lookup
            ON merchant_code_fsku_bindings(platform, store_code, merchant_code)
            """
        )

    # ---------------------------------------------------------------------
    # 5) shipping / waybill / finance shipping
    # ---------------------------------------------------------------------
    if _table_exists(conn, "shipping_records"):
        _exec("ALTER TABLE shipping_records DROP CONSTRAINT IF EXISTS uq_shipping_records_platform_shop_ref")
        _exec("ALTER TABLE shipping_records DROP CONSTRAINT IF EXISTS uq_shipping_records_platform_shop_ref_package")
        _rename_column(conn, "shipping_records", "shop_id", "store_code")
        _exec(
            """
            ALTER TABLE shipping_records
            ADD CONSTRAINT uq_shipping_records_platform_store_ref_package
            UNIQUE (platform, store_code, order_ref, package_no)
            """
        )

    if _table_exists(conn, "transport_shipments"):
        _exec("ALTER TABLE transport_shipments DROP CONSTRAINT IF EXISTS uq_transport_shipments_platform_shop_ref")
        _rename_column(conn, "transport_shipments", "shop_id", "store_code")
        _exec(
            """
            ALTER TABLE transport_shipments
            ADD CONSTRAINT uq_transport_shipments_platform_store_ref
            UNIQUE (platform, store_code, order_ref)
            """
        )

    if _table_exists(conn, "electronic_waybill_configs"):
        _exec("ALTER TABLE electronic_waybill_configs DROP CONSTRAINT IF EXISTS uq_electronic_waybill_configs_platform_shop_provider")
        _exec("DROP INDEX IF EXISTS ix_electronic_waybill_configs_platform_shop")
        _rename_column(conn, "electronic_waybill_configs", "shop_id", "store_code")
        _exec(
            """
            ALTER TABLE electronic_waybill_configs
            ADD CONSTRAINT uq_electronic_waybill_configs_platform_store_provider
            UNIQUE (platform, store_code, shipping_provider_id)
            """
        )
        _exec(
            """
            CREATE INDEX ix_electronic_waybill_configs_platform_store
            ON electronic_waybill_configs(platform, store_code)
            """
        )

    if _table_exists(conn, "finance_shipping_cost_lines"):
        _exec("DROP INDEX IF EXISTS ix_fsc_lines_platform_shop")
        _exec("DROP INDEX IF EXISTS ix_fsc_lines_shop_id")
        _exec("DROP INDEX IF EXISTS ix_fsc_lines_platform_store")
        _exec("DROP INDEX IF EXISTS ix_fsc_lines_store_code")
        _rename_column(conn, "finance_shipping_cost_lines", "shop_id", "store_code")
        _rename_column(conn, "finance_shipping_cost_lines", "shop_name", "store_name")
        _exec("CREATE INDEX ix_fsc_lines_platform_store ON finance_shipping_cost_lines(platform, store_code)")
        _exec("CREATE INDEX ix_fsc_lines_store_code ON finance_shipping_cost_lines(store_code)")

    # ---------------------------------------------------------------------
    # 6) events / outbound commits
    # ---------------------------------------------------------------------
    if _table_exists(conn, "event_error_log"):
        _exec("DROP INDEX IF EXISTS ix_event_error_log_key")
        _rename_column(conn, "event_error_log", "shop_id", "store_code")
        _exec(
            """
            CREATE INDEX ix_event_error_log_key
            ON event_error_log(platform, store_code, idempotency_key)
            """
        )

    if _table_exists(conn, "platform_events"):
        _rename_column(conn, "platform_events", "shop_id", "store_code")

    if _table_exists(conn, "outbound_commits"):
        _rename_column(conn, "outbound_commits", "shop_id", "store_code")

    # ---------------------------------------------------------------------
    # 7) 视图：routing metrics
    # ---------------------------------------------------------------------
    if _table_exists(conn, "orders") and _table_exists(conn, "stores"):
        join_fulfillment = ""
        warehouse_expr = "NULL::bigint"

        if _col_exists(conn, "orders", "warehouse_id"):
            warehouse_expr = "o.warehouse_id"
        elif _table_exists(conn, "order_fulfillment"):
            if _col_exists(conn, "order_fulfillment", "actual_warehouse_id") and _col_exists(
                conn, "order_fulfillment", "planned_warehouse_id"
            ):
                join_fulfillment = "LEFT JOIN order_fulfillment f ON f.order_id = o.id"
                warehouse_expr = "COALESCE(f.actual_warehouse_id, f.planned_warehouse_id)"
            elif _col_exists(conn, "order_fulfillment", "planned_warehouse_id"):
                join_fulfillment = "LEFT JOIN order_fulfillment f ON f.order_id = o.id"
                warehouse_expr = "f.planned_warehouse_id"
            elif _col_exists(conn, "order_fulfillment", "actual_warehouse_id"):
                join_fulfillment = "LEFT JOIN order_fulfillment f ON f.order_id = o.id"
                warehouse_expr = "f.actual_warehouse_id"

        _exec(
            f"""
            CREATE OR REPLACE VIEW vw_routing_metrics_daily AS
            SELECT
                date_trunc('day', o.created_at) AS day,
                o.platform,
                o.store_code,
                COALESCE(s.route_mode, 'FALLBACK') AS route_mode,
                {warehouse_expr} AS warehouse_id,
                COUNT(*) FILTER (WHERE {warehouse_expr} IS NOT NULL) AS routed_orders,
                COUNT(*) FILTER (WHERE {warehouse_expr} IS NULL)     AS failed_orders
            FROM orders o
            LEFT JOIN stores s
              ON s.platform = o.platform
             AND s.store_code = o.store_code
            {join_fulfillment}
            GROUP BY
                date_trunc('day', o.created_at),
                o.platform,
                o.store_code,
                COALESCE(s.route_mode, 'FALLBACK'),
                {warehouse_expr}
            """
        )

    # ---------------------------------------------------------------------
    # 8) 重建 finance shipping refresh function / store trigger
    # ---------------------------------------------------------------------
    if _table_exists(conn, "finance_shipping_cost_lines") and _table_exists(conn, "shipping_records"):
        _exec(
            """
            CREATE OR REPLACE FUNCTION finance_refresh_shipping_cost_line(p_shipping_record_id bigint)
            RETURNS void
            LANGUAGE plpgsql
            AS $$
            BEGIN
              INSERT INTO finance_shipping_cost_lines (
                shipping_record_id,
                platform,
                store_code,
                store_name,
                order_ref,
                package_no,
                tracking_no,
                warehouse_id,
                warehouse_name,
                shipping_provider_id,
                shipping_provider_code,
                shipping_provider_name,
                shipped_time,
                shipped_date,
                dest_province,
                dest_city,
                gross_weight_kg,
                freight_estimated,
                surcharge_estimated,
                cost_estimated,
                source_updated_at,
                calculated_at
              )
              SELECT
                sr.id AS shipping_record_id,
                sr.platform AS platform,
                sr.store_code AS store_code,
                s.store_name AS store_name,
                sr.order_ref AS order_ref,
                sr.package_no AS package_no,
                sr.tracking_no AS tracking_no,
                sr.warehouse_id AS warehouse_id,
                COALESCE(w.name, '') AS warehouse_name,
                sr.shipping_provider_id AS shipping_provider_id,
                COALESCE(sp.shipping_provider_code, sr.shipping_provider_code) AS shipping_provider_code,
                COALESCE(sp.name, sr.shipping_provider_name) AS shipping_provider_name,
                sr.created_at AS shipped_time,
                DATE(sr.created_at) AS shipped_date,
                sr.dest_province AS dest_province,
                sr.dest_city AS dest_city,
                sr.gross_weight_kg AS gross_weight_kg,
                sr.freight_estimated AS freight_estimated,
                sr.surcharge_estimated AS surcharge_estimated,
                sr.cost_estimated AS cost_estimated,
                sr.created_at AS source_updated_at,
                now() AS calculated_at
              FROM shipping_records sr
              JOIN warehouses w
                ON w.id = sr.warehouse_id
              LEFT JOIN shipping_providers sp
                ON sp.id = sr.shipping_provider_id
              LEFT JOIN stores s
                ON upper(s.platform) = upper(sr.platform)
               AND btrim(CAST(s.store_code AS text)) = btrim(CAST(sr.store_code AS text))
              WHERE sr.id = p_shipping_record_id
              ON CONFLICT (shipping_record_id) DO UPDATE SET
                platform = EXCLUDED.platform,
                store_code = EXCLUDED.store_code,
                store_name = EXCLUDED.store_name,
                order_ref = EXCLUDED.order_ref,
                package_no = EXCLUDED.package_no,
                tracking_no = EXCLUDED.tracking_no,
                warehouse_id = EXCLUDED.warehouse_id,
                warehouse_name = EXCLUDED.warehouse_name,
                shipping_provider_id = EXCLUDED.shipping_provider_id,
                shipping_provider_code = EXCLUDED.shipping_provider_code,
                shipping_provider_name = EXCLUDED.shipping_provider_name,
                shipped_time = EXCLUDED.shipped_time,
                shipped_date = EXCLUDED.shipped_date,
                dest_province = EXCLUDED.dest_province,
                dest_city = EXCLUDED.dest_city,
                gross_weight_kg = EXCLUDED.gross_weight_kg,
                freight_estimated = EXCLUDED.freight_estimated,
                surcharge_estimated = EXCLUDED.surcharge_estimated,
                cost_estimated = EXCLUDED.cost_estimated,
                source_updated_at = EXCLUDED.source_updated_at,
                calculated_at = now();
            END;
            $$;
            """
        )

        _exec(
            """
            CREATE OR REPLACE FUNCTION finance_trg_shipping_cost_store_refresh()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
              v_record_id bigint;
            BEGIN
              IF TG_OP IN ('INSERT', 'UPDATE') THEN
                FOR v_record_id IN
                  SELECT id
                  FROM shipping_records
                  WHERE upper(platform) = upper(NEW.platform)
                    AND btrim(CAST(store_code AS text)) = btrim(CAST(NEW.store_code AS text))
                LOOP
                  PERFORM finance_refresh_shipping_cost_line(v_record_id);
                END LOOP;
              END IF;

              IF TG_OP IN ('UPDATE', 'DELETE') THEN
                FOR v_record_id IN
                  SELECT id
                  FROM shipping_records
                  WHERE upper(platform) = upper(OLD.platform)
                    AND btrim(CAST(store_code AS text)) = btrim(CAST(OLD.store_code AS text))
                LOOP
                  PERFORM finance_refresh_shipping_cost_line(v_record_id);
                END LOOP;
              END IF;

              IF TG_OP = 'DELETE' THEN
                RETURN OLD;
              END IF;
              RETURN NEW;
            END;
            $$;
            """
        )

        _exec(
            """
            CREATE TRIGGER trg_fsc_lines_store_refresh
            AFTER INSERT OR UPDATE OF store_name, platform, store_code OR DELETE
            ON stores
            FOR EACH ROW
            EXECUTE FUNCTION finance_trg_shipping_cost_store_refresh()
            """
        )

        _exec(
            """
            SELECT finance_refresh_shipping_cost_line(sr.id)
            FROM shipping_records sr
            """
        )


def downgrade() -> None:
    # 终态治理迁移，不支持自动 downgrade，避免把 store_code 再拆回 shop_id 双轨。
    raise RuntimeError("downgrade is intentionally unsupported for oms store_code naming cutover")
