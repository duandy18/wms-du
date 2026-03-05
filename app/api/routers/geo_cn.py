# app/api/routers/geo_cn.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_current_user
from app.api.routers.shipping_provider_pricing_schemes_utils import check_perm
from app.db.deps import get_db
from app.geo.cn_registry import list_cities, list_provinces

router = APIRouter(prefix="/geo", tags=["geo"])


class GeoItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str


@router.get("/provinces", response_model=list[GeoItemOut])
def geo_list_provinces(
    q: str | None = Query(default=None),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    # ✅ 这里沿用配置写权限：因为这是配置页面的输入源
    check_perm(db, user, "config.store.write")
    return [GeoItemOut(code=x.code, name=x.name) for x in list_provinces(q=q)]


@router.get("/provinces/{province_code}/cities", response_model=list[GeoItemOut])
def geo_list_cities(
    province_code: str,
    q: str | None = Query(default=None),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    check_perm(db, user, "config.store.write")
    return [GeoItemOut(code=x.code, name=x.name) for x in list_cities(province_code=province_code, q=q)]
