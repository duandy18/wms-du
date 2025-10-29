import pytest
pytestmark = [pytest.mark.xfail(reason="WIP: barcode utils", strict=False)]

def test_barcode_encode_decode_roundtrip():
    from app.services.barcode import encode, decode
    code = encode({"item_id": 1, "batch": "B001"})
    obj = decode(code)
    assert obj["item_id"] == 1
