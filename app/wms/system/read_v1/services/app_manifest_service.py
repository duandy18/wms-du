# app/wms/system/read_v1/services/app_manifest_service.py
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Literal

from app.wms.system.read_v1.contracts import (
    WmsSystemAppInfoOut,
    WmsSystemAppManifestOut,
    WmsSystemBuildInfoOut,
    WmsSystemDeploymentOut,
    WmsSystemEndpointDescriptorOut,
    WmsSystemSecurityPolicyOut,
    WmsSystemServiceIdentityOut,
)

WMS_APP_CODE = "wms"
WMS_APP_NAME = "WMS 仓储执行系统"
WMS_APP_VERSION = "1.1.0"
WMS_MANIFEST_CONTRACT_VERSION = "2.0"

WMS_SERVICE_CLIENT_CODE = "wms-service"
WMS_SERVICE_CLIENT_HEADER = "X-Service-Client"
ERP_SERVICE_CLIENT_CODE = "erp-service"


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _endpoint(
    *,
    code: str,
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"],
    path: str,
    purpose: str,
    auth_policy: Literal[
        "internal_control_plane",
        "erp_service_client_required",
        "public_health",
    ],
    is_required: bool = True,
    is_active: bool = True,
) -> WmsSystemEndpointDescriptorOut:
    return WmsSystemEndpointDescriptorOut(
        code=code,
        method=method,
        path=path,
        purpose=purpose,
        is_required=is_required,
        is_active=is_active,
        auth_policy=auth_policy,
    )


def build_wms_app_manifest() -> WmsSystemAppManifestOut:
    app_version = _env_value("WMS_APP_VERSION", "APP_VERSION") or WMS_APP_VERSION
    env_code = _env_value("WMS_ENV_CODE", "ENV_CODE", "WMS_ENV", "ENV") or "dev"
    deployment_mode = _env_value("WMS_DEPLOYMENT_MODE", "DEPLOYMENT_MODE") or "local"

    control_base_url = (
        _env_value("WMS_CONTROL_BASE_URL", "WMS_INTERNAL_API_BASE_URL", "WMS_LOCAL_API_URL")
        or "http://127.0.0.1:8000"
    )
    internal_api_base_url = (
        _env_value("WMS_INTERNAL_API_BASE_URL", "WMS_LOCAL_API_URL") or control_base_url
    )

    return WmsSystemAppManifestOut(
        manifest_contract_version=WMS_MANIFEST_CONTRACT_VERSION,
        generated_at=datetime.now(UTC),
        app=WmsSystemAppInfoOut(
            app_code=WMS_APP_CODE,
            app_name=WMS_APP_NAME,
            app_type="business_system",
            owner_domain="warehouse_execution",
            status="available",
            description=(
                "WMS 仓储执行系统，负责库存、入库、出库、仓库、仓内作业、"
                "发货交接和仓储侧执行事实能力。"
            ),
        ),
        deployment=WmsSystemDeploymentOut(
            env_code=env_code,
            deployment_mode=deployment_mode,
            web_path=_env_value("WMS_WEB_PATH") or "/wms",
            api_path=_env_value("WMS_API_PATH") or "/api/wms",
            control_base_url=control_base_url,
            internal_api_base_url=internal_api_base_url,
            public_web_url=_env_value("WMS_PUBLIC_WEB_URL", "WMS_LOCAL_WEB_URL")
            or "http://127.0.0.1:5173",
            public_api_base_url=_env_value("WMS_PUBLIC_API_BASE_URL"),
        ),
        service_identity=WmsSystemServiceIdentityOut(
            service_client_code=WMS_SERVICE_CLIENT_CODE,
            service_client_header=WMS_SERVICE_CLIENT_HEADER,
        ),
        control_endpoints=[
            _endpoint(
                code="app_manifest",
                method="GET",
                path="/system/read/v1/app-manifest",
                purpose="应用清单自描述",
                auth_policy="internal_control_plane",
            ),
            _endpoint(
                code="page_catalog",
                method="GET",
                path="/system/read/v1/page-catalog",
                purpose="页面目录",
                auth_policy="internal_control_plane",
            ),
            _endpoint(
                code="service_capabilities",
                method="GET",
                path="/system/read/v1/service-capabilities",
                purpose="服务能力目录",
                auth_policy="internal_control_plane",
            ),
            _endpoint(
                code="service_dependencies",
                method="GET",
                path="/system/read/v1/service-dependencies",
                purpose="服务依赖声明",
                auth_policy="internal_control_plane",
            ),
            _endpoint(
                code="openapi",
                method="GET",
                path="/openapi.json",
                purpose="OpenAPI 合同",
                auth_policy="internal_control_plane",
            ),
            _endpoint(
                code="health",
                method="GET",
                path="/healthz",
                purpose="应用健康检查",
                auth_policy="public_health",
            ),
            _endpoint(
                code="db_health",
                method="GET",
                path="/health/db",
                purpose="数据库健康检查",
                auth_policy="internal_control_plane",
            ),
        ],
        write_endpoints=[
            _endpoint(
                code="iam_apply",
                method="POST",
                path="/system/write/v1/iam/apply",
                purpose="ERP 用户与页面权限写入",
                auth_policy="erp_service_client_required",
            ),
            _endpoint(
                code="iam_verify",
                method="POST",
                path="/system/write/v1/iam/verify",
                purpose="ERP 用户与页面权限校验",
                auth_policy="erp_service_client_required",
            ),
            _endpoint(
                code="service_permission_apply",
                method="POST",
                path="/system/write/v1/service-permissions/apply",
                purpose="ERP 系统间访问白名单写入",
                auth_policy="erp_service_client_required",
            ),
            _endpoint(
                code="service_permission_verify",
                method="GET",
                path="/system/write/v1/service-permissions/verify",
                purpose="ERP 系统间访问白名单校验",
                auth_policy="erp_service_client_required",
            ),
        ],
        security=WmsSystemSecurityPolicyOut(
            self_description_auth_policy="internal_control_plane",
            write_auth_policy="erp_service_client_required",
            required_write_caller=ERP_SERVICE_CLIENT_CODE,
        ),
        build=WmsSystemBuildInfoOut(
            app_version=app_version,
            git_sha=_env_value("WMS_GIT_SHA", "GIT_SHA", "COMMIT_SHA"),
            image_tag=_env_value("WMS_IMAGE_TAG", "IMAGE_TAG"),
            build_time=_env_value("WMS_BUILD_TIME", "BUILD_TIME"),
        ),
    )


__all__ = [
    "WMS_APP_CODE",
    "WMS_APP_NAME",
    "WMS_APP_VERSION",
    "build_wms_app_manifest",
]
