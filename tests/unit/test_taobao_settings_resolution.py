from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.oms.platforms.models.taobao_app_config import TaobaoAppConfig
from app.oms.platforms.taobao.errors import TaobaoTopConfigError
from app.oms.platforms.taobao.repository import get_enabled_taobao_app_config
from app.oms.platforms.taobao.settings import (
    build_taobao_callback_url_from_model,
    build_taobao_top_config_from_model,
)


@pytest.fixture(autouse=True)
async def _clean_taobao_app_configs(session):
    await session.execute(text("DELETE FROM taobao_app_configs"))
    await session.commit()
    yield
    await session.execute(text("DELETE FROM taobao_app_configs"))
    await session.commit()


def _row(
    *,
    row_id: int = 1,
    app_key: str = "tb-app-key",
    app_secret: str = "tb-app-secret",
    callback_url: str = "http://127.0.0.1:8000/oms/taobao/oauth/callback",
    api_base_url: str = "https://eco.taobao.com/router/rest",
    sign_method: str = "md5",
    is_enabled: bool = True,
) -> TaobaoAppConfig:
    now = datetime.now(timezone.utc)
    row = TaobaoAppConfig(
        id=row_id,
        app_key=app_key,
        app_secret=app_secret,
        callback_url=callback_url,
        api_base_url=api_base_url,
        sign_method=sign_method,
        is_enabled=is_enabled,
        created_at=now,
        updated_at=now,
    )
    return row


def test_build_taobao_top_config_from_model_success():
    row = _row()
    cfg = build_taobao_top_config_from_model(row)

    assert cfg.app_key == "tb-app-key"
    assert cfg.app_secret == "tb-app-secret"
    assert cfg.api_base_url == "https://eco.taobao.com/router/rest"
    assert cfg.sign_method == "md5"


def test_build_taobao_top_config_from_model_rejects_invalid_sign_method():
    row = _row(sign_method="sha256")

    with pytest.raises(TaobaoTopConfigError) as exc:
        build_taobao_top_config_from_model(row)

    assert "unsupported taobao top sign_method" in str(exc.value)


def test_build_taobao_callback_url_from_model_requires_non_empty_value():
    row = _row(callback_url="")

    with pytest.raises(TaobaoTopConfigError) as exc:
        build_taobao_callback_url_from_model(row)

    assert "taobao callback_url is required" in str(exc.value)


@pytest.mark.asyncio
async def test_get_enabled_taobao_app_config_returns_none_when_missing(session):
    rows = await get_enabled_taobao_app_config(session)
    assert rows is None


@pytest.mark.asyncio
async def test_get_enabled_taobao_app_config_returns_enabled_row_when_disabled_rows_also_exist(session):
    session.add(_row(row_id=1001, app_key="k1", app_secret="s1", is_enabled=True))
    session.add(_row(row_id=1002, app_key="k2", app_secret="s2", is_enabled=False))
    await session.commit()

    row = await get_enabled_taobao_app_config(session)

    assert row is not None
    assert row.id == 1001
    assert row.app_key == "k1"
