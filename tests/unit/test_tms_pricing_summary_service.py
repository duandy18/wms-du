from __future__ import annotations

from app.tms.pricing.summary.service import (
    compute_is_template_active,
    compute_pricing_status,
)


def test_compute_pricing_status_provider_disabled() -> None:
    assert (
        compute_pricing_status(
            provider_active=False,
            binding_active=True,
            active_template_id=1,
            template_archived=False,
        )
        == "provider_disabled"
    )


def test_compute_pricing_status_binding_disabled() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=False,
            active_template_id=1,
            template_archived=False,
        )
        == "binding_disabled"
    )


def test_compute_pricing_status_no_active_template() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=None,
            template_archived=False,
        )
        == "no_active_template"
    )


def test_compute_pricing_status_template_archived() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=1,
            template_archived=True,
        )
        == "template_archived"
    )


def test_compute_pricing_status_ready_when_draft_unarchived() -> None:
    assert (
        compute_pricing_status(
            provider_active=True,
            binding_active=True,
            active_template_id=1,
            template_archived=False,
        )
        == "ready"
    )


def test_compute_is_template_active_false_when_missing() -> None:
    assert (
        compute_is_template_active(
            active_template_id=None,
            template_archived=False,
        )
        is False
    )


def test_compute_is_template_active_false_when_archived() -> None:
    assert (
        compute_is_template_active(
            active_template_id=1,
            template_archived=True,
        )
        is False
    )


def test_compute_is_template_active_true_for_draft_unarchived() -> None:
    assert (
        compute_is_template_active(
            active_template_id=1,
            template_archived=False,
        )
        is True
    )
