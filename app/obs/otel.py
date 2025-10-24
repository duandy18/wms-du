# app/obs/otel.py
# OpenTelemetry 初始化（容错 + 智能回落 + gRPC/HTTP 双协议）
from __future__ import annotations

import os
import socket
from typing import Optional


def _resolve_otlp_endpoint() -> tuple[str, str]:
    """
    决定 OTLP 导出端点与协议。
    优先级：
      1) 显式环境变量 OTEL_EXPORTER_OTLP_ENDPOINT / OTEL_EXPORTER_OTLP_PROTOCOL
      2) 同一 docker 网络内的 otel-collector:4317（gRPC）
      3) 宿主机 localhost:4317（gRPC）
    备注：你也可通过设置 OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf 强制走 HTTP(4318)。
    """
    ep = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    proto = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "").strip().lower()

    if ep:  # 用户显式指定 -> 原样使用
        return ep, proto or "grpc"

    # 尝试容器网络名
    try:
        socket.getaddrinfo("otel-collector", 4317)
        return "http://otel-collector:4317", "grpc"
    except Exception:
        # 宿主直连（pytest/脚本本机运行的场景）
        return "http://localhost:4317", "grpc"


def setup_tracing(app=None, sqlalchemy_engine=None) -> bool:
    """
    初始化 OpenTelemetry。
    - 依赖缺失或 Collector 不可用时，静默降级（返回 False）
    - 成功启用返回 True
    """
    # 依赖可选：缺失则直接降级
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # 两种导出器按协议动态选择
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
            OTLPSpanExporter as _OTLPGrpcExporter,
        )
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
                OTLPSpanExporter as _OTLPHttpExporter,
            )
        except Exception:  # 某些安装不含 http 导出器
            _OTLPHttpExporter = None  # type: ignore

        # 自动注入的各类 instrumentation
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
    except Exception:
        return False  # 依赖缺失：不报错、不拖垮

    try:
        # 资源标识
        service_name = os.getenv("OTEL_SERVICE_NAME", "wms-du")
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": os.getenv("GIT_SHA", "dev"),
                "deployment.environment": os.getenv("ENV", "local"),
            }
        )

        # Provider
        provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(provider)

        # 端点与协议（grpc / http/protobuf）
        endpoint, proto = _resolve_otlp_endpoint()
        proto = (proto or "grpc").lower()

        # Sampler 行为可以通过环境变量控制（如 OTEL_TRACES_SAMPLER=always_on）
        # 这里不强行覆盖，遵循 SDK 默认 + 环境变量

        # 导出器配置
        insecure = True  # dev 环境默认明文
        if proto.startswith("http"):
            if _OTLPHttpExporter is None:
                # 回退到 gRPC，如果 http exporter 不可用
                exporter = _OTLPGrpcExporter(endpoint=endpoint, insecure=insecure)
            else:
                # 允许用户用 4318 + http/protobuf
                # 若用户只设置了协议没改端点，自动切到 4318
                if endpoint.endswith(":4317"):
                    endpoint = endpoint.replace(":4317", ":4318")
                exporter = _OTLPHttpExporter(endpoint=endpoint)
        else:
            exporter = _OTLPGrpcExporter(endpoint=endpoint, insecure=insecure)

        provider.add_span_processor(BatchSpanProcessor(exporter))

        # Instrumentations（按需启用）
        if app is not None:
            # 排除 /metrics 避免打点风暴
            FastAPIInstrumentor.instrument_app(app, excluded_urls="metrics")
        if sqlalchemy_engine is not None:
            SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine)

        # 这些无害，装上即用
        try:
            RedisInstrumentor().instrument()
        except Exception:
            pass
        try:
            CeleryInstrumentor().instrument()
        except Exception:
            pass

        return True

    except Exception:
        # Collector 不可达或导出器异常：不抛出，静默降级
        return False
