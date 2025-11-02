import pytest
from datetime import date
from app.services.utils.expiry import calc_expire_at, ExpiryError

def test_calc_expire_at_basic():
    assert calc_expire_at(date(2025,10,31), 365) == date(2026,10,31)

def test_calc_expire_at_none_allowed():
    assert calc_expire_at(None, None, allow_null=True) is None

def test_calc_expire_at_incomplete_raises():
    with pytest.raises(ExpiryError):
        calc_expire_at(date(2025,10,31), None)

def test_calc_expire_at_negative_days():
    with pytest.raises(ExpiryError):
        calc_expire_at(date(2025,10,31), -1)
