# app/wms/system/read_v1/contracts/app_manifest.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ManifestContractVersion = Literal["2.0"]
EndpointAuthPolicy = Literal[
    "internal_control_plane",
    "erp_service_client_required",
    "public_health",
]


class WmsSystemEndpointDescriptorOut(_Base):
    code: str = Field(..., min_length=1, max_length=128)
    method: HttpMethod
    path: str = Field(..., min_length=1, max_length=255)
    purpose: str = Field(..., min_length=1, max_length=255)
    is_required: bool = True
    is_active: bool = True
    auth_policy: EndpointAuthPolicy


class WmsSystemAppInfoOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1, max_length=128)
    app_type: str = Field(..., min_length=1, max_length=64)
    owner_domain: str = Field(..., min_length=1, max_length=128)
    status: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=512)


class WmsSystemDeploymentOut(_Base):
    env_code: str = Field(..., min_length=1, max_length=64)
    deployment_mode: str = Field(..., min_length=1, max_length=64)
    web_path: str = Field(..., min_length=1, max_length=255)
    api_path: str = Field(..., min_length=1, max_length=255)
    control_base_url: str = Field(..., min_length=1, max_length=255)
    internal_api_base_url: str = Field(..., min_length=1, max_length=255)
    public_web_url: str = Field(..., min_length=1, max_length=255)
    public_api_base_url: str | None = Field(default=None, max_length=255)


class WmsSystemServiceIdentityOut(_Base):
    service_client_code: Literal["wms-service"]
    service_client_header: Literal["X-Service-Client"]


class WmsSystemSecurityPolicyOut(_Base):
    self_description_auth_policy: Literal["internal_control_plane"]
    write_auth_policy: Literal["erp_service_client_required"]
    required_write_caller: Literal["erp-service"]


class WmsSystemBuildInfoOut(_Base):
    app_version: str = Field(..., min_length=1, max_length=64)
    git_sha: str | None = Field(default=None, max_length=128)
    image_tag: str | None = Field(default=None, max_length=128)
    build_time: str | None = Field(default=None, max_length=128)


class WmsSystemAppManifestOut(_Base):
    manifest_contract_version: ManifestContractVersion
    generated_at: datetime

    app: WmsSystemAppInfoOut
    deployment: WmsSystemDeploymentOut
    service_identity: WmsSystemServiceIdentityOut

    control_endpoints: list[WmsSystemEndpointDescriptorOut] = Field(default_factory=list)
    write_endpoints: list[WmsSystemEndpointDescriptorOut] = Field(default_factory=list)

    security: WmsSystemSecurityPolicyOut
    build: WmsSystemBuildInfoOut


__all__ = [
    "WmsSystemAppInfoOut",
    "WmsSystemAppManifestOut",
    "WmsSystemBuildInfoOut",
    "WmsSystemDeploymentOut",
    "WmsSystemEndpointDescriptorOut",
    "WmsSystemSecurityPolicyOut",
    "WmsSystemServiceIdentityOut",
]
