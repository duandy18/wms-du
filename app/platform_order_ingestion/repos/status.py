# Module split: platform order ingestion store-level status repository.
from __future__ import annotations

from typing import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_APP_TABLE_BY_PLATFORM = {
    "pdd": "pdd_app_configs",
    "taobao": "taobao_app_configs",
    "jd": "jd_app_configs",
}


def normalize_platform(value: str) -> str:
    return str(value or "").strip().lower()


async def load_store_row(
    session: AsyncSession,
    *,
    store_id: int,
) -> Mapping | None:
    result = await session.execute(
        text(
            """
            SELECT id, platform, store_code, store_name, active
              FROM stores
             WHERE id = :store_id
             LIMIT 1
            """
        ),
        {"store_id": int(store_id)},
    )
    return result.mappings().first()


async def count_enabled_app_configs(
    session: AsyncSession,
    *,
    platform: str,
) -> int:
    platform_norm = normalize_platform(platform)
    table = _APP_TABLE_BY_PLATFORM.get(platform_norm)
    if table is None:
        return 0

    result = await session.execute(
        text(f"SELECT count(*) FROM {table} WHERE is_enabled IS TRUE")
    )
    return int(result.scalar_one() or 0)


async def load_connection_row(
    session: AsyncSession,
    *,
    store_id: int,
    platform: str,
) -> Mapping | None:
    result = await session.execute(
        text(
            """
            SELECT
              id,
              store_id,
              platform,
              auth_source,
              connection_status,
              credential_status,
              reauth_required,
              pull_ready,
              status,
              status_reason,
              last_authorized_at,
              last_pull_checked_at,
              last_error_at
            FROM store_platform_connections
            WHERE store_id = :store_id
              AND platform = :platform
            LIMIT 1
            """
        ),
        {"store_id": int(store_id), "platform": normalize_platform(platform)},
    )
    return result.mappings().first()


async def load_credential_row(
    session: AsyncSession,
    *,
    store_id: int,
    platform: str,
) -> Mapping | None:
    result = await session.execute(
        text(
            """
            SELECT
              id,
              store_id,
              platform,
              credential_type,
              expires_at,
              scope,
              granted_identity_type,
              granted_identity_value,
              granted_identity_display
            FROM store_platform_credentials
            WHERE store_id = :store_id
              AND platform = :platform
            LIMIT 1
            """
        ),
        {"store_id": int(store_id), "platform": normalize_platform(platform)},
    )
    return result.mappings().first()


async def load_latest_job_with_run(
    session: AsyncSession,
    *,
    store_id: int,
    platform: str,
) -> Mapping | None:
    result = await session.execute(
        text(
            """
            SELECT
              j.id AS job_id,
              j.job_type,
              j.status AS job_status,
              j.time_from,
              j.time_to,
              j.order_status,
              j.page_size AS job_page_size,
              j.cursor_page,
              j.last_run_at,
              j.last_success_at,
              j.last_error_at,
              j.last_error_message,
              j.created_at AS job_created_at,

              r.id AS run_id,
              r.status AS run_status,
              r.page AS run_page,
              r.page_size AS run_page_size,
              r.has_more,
              r.orders_count,
              r.success_count,
              r.failed_count,
              r.started_at,
              r.finished_at,
              r.error_message AS run_error_message
            FROM platform_order_pull_jobs j
            LEFT JOIN LATERAL (
              SELECT *
              FROM platform_order_pull_job_runs r
              WHERE r.job_id = j.id
              ORDER BY r.id DESC
              LIMIT 1
            ) r ON TRUE
            WHERE j.store_id = :store_id
              AND j.platform = :platform
            ORDER BY j.id DESC
            LIMIT 1
            """
        ),
        {"store_id": int(store_id), "platform": normalize_platform(platform)},
    )
    return result.mappings().first()
