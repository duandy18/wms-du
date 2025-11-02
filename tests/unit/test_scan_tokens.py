import pytest

from app.services.scan_tokens import extract_scan_context

pytestmark = pytest.mark.grp_scan


def test_tokens_parse_happy_path():
    payload = {
        "mode": "pick",
        "tokens": {"barcode": "TASK:42 LOC:900 ITEM:3001 QTY:2"},
        "ctx": {"device_id": "RF01", "operator": "alice"},
    }
    sc = extract_scan_context(payload)
    assert sc.mode == "pick"
    assert sc.task_id == 42
    assert sc.location_id == 900
    assert sc.item_id == 3001
    assert sc.qty == 2
    assert sc.device_id == "RF01"
    assert sc.operator == "alice"


def test_tokens_parse_split_fields():
    payload = {
        "mode": "pick",
        "tokens": {"task": "TASK:7", "loc": "LOC:1", "item": "ITEM:606", "qty": "QTY:5"},
        "ctx": {"device_id": "RF02"},
    }
    sc = extract_scan_context(payload)
    assert (sc.task_id, sc.location_id, sc.item_id, sc.qty) == (7, 1, 606, 5)


def test_tokens_parse_weird_separators():
    payload = {"mode": "pick", "tokens": "TASK:1;LOC:2|ITEM:3,QTY:4"}
    sc = extract_scan_context(payload)
    assert (sc.task_id, sc.location_id, sc.item_id, sc.qty) == (1, 2, 3, 4)
