from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.tms.pricing.summary.service import compute_pricing_status


def test_compute_pricing_status_provider_disabled() -> None:
    assert (
        compute_pricing_status(
            provider_active=False,
            binding_active=True,
            active_template_id=1,
            effective_from=None,
            now=datetime.now(timezone.utc),
        )
        == "provider_disabled"
    )


def test_compute_pricing_status_binding_disabled() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=False,
            active_template_id=1,
            effective_from=None,
            now=datetime.now(timezone.utc),
        )
        == "binding_disabled"
    )


def test_compute_pricing_status_no_active_template() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=None,
            effective_from=None,
            now=datetime.now(timezone.utc),
        )
        == "no_active_template"
    )


def test_compute_pricing_status_active() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=1,
            effective_from=None,
            now=datetime.now(timezone.utc),
        )
        == "active"
    )


def test_compute_pricing_status_scheduled() -> None:
    now = datetime.now(timezone.utc)
    future_time = now + timedelta(hours=1)

    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=1,
            effective_from=future_time,
            now=now,
        )
        == "scheduled"
    )
