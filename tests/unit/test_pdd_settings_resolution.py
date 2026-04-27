from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.platform_order_ingestion.models.pdd_app_config import PddAppConfig
from app.platform_order_ingestion.pdd.repository import get_enabled_pdd_app_config
from app.platform_order_ingestion.pdd.settings import (
    PddOpenConfigError,
    build_pdd_open_config_from_model,
    build_pdd_redirect_uri_from_model,
)


def _row(
    *,
    row_id: int = 1,
    client_id: str = "pdd-client-id-001",
    client_secret: str = "pdd-client-secret-001",
    redirect_uri: str = "http://127.0.0.1:8000/oms/pdd/oauth/callback",
    api_base_url: str = "https://gw-api.pinduoduo.com/api/router",
    sign_method: str = "md5",
    is_enabled: bool = True,
) -> PddAppConfig:
    now = datetime.now(timezone.utc)
    row = PddAppConfig(
        id=row_id,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        api_base_url=api_base_url,
        sign_method=sign_method,
        is_enabled=is_enabled,
        created_at=now,
        updated_at=now,
    )
    return row


def test_build_pdd_open_config_from_model_success():
    row = _row()
    cfg = build_pdd_open_config_from_model(row)

    assert cfg.client_id == "pdd-client-id-001"
    assert cfg.client_secret == "pdd-client-secret-001"
    assert cfg.api_base_url == "https://gw-api.pinduoduo.com/api/router"
    assert cfg.sign_method == "md5"


def test_build_pdd_open_config_from_model_rejects_invalid_sign_method():
    row = _row(sign_method="sha256")

    with pytest.raises(PddOpenConfigError) as exc:
        build_pdd_open_config_from_model(row)

    assert "unsupported pdd sign_method" in str(exc.value)


def test_build_pdd_redirect_uri_from_model_requires_non_empty_value():
    row = _row(redirect_uri="")

    with pytest.raises(PddOpenConfigError) as exc:
        build_pdd_redirect_uri_from_model(row)

    assert "pdd redirect_uri is required" in str(exc.value)


@pytest.mark.asyncio
async def test_get_enabled_pdd_app_config_returns_none_when_missing(session):
    row = await get_enabled_pdd_app_config(session)
    assert row is None


@pytest.mark.asyncio
async def test_get_enabled_pdd_app_config_returns_enabled_row_when_disabled_rows_also_exist(session):
    session.add(
        _row(
            row_id=2001,
            client_id="pdd-client-enabled",
            client_secret="pdd-secret-enabled",
            is_enabled=True,
        )
    )
    session.add(
        _row(
            row_id=2002,
            client_id="pdd-client-disabled",
            client_secret="pdd-secret-disabled",
            is_enabled=False,
        )
    )
    await session.commit()

    row = await get_enabled_pdd_app_config(session)

    assert row is not None
    assert row.id == 2001
    assert row.client_id == "pdd-client-enabled"
