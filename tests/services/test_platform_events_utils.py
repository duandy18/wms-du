from app.services.platform_events import _classify


def test_classify_paid_aliases():
    for s in ["PAID", "paid", "Paid", "NEW", "WAIT_SELLER_SEND_GOODS"]:
        assert _classify(s) == "RESERVE"


def test_classify_cancel_aliases():
    for s in ["CANCELED", "CANCELLED", "VOID", "TRADE_CLOSED"]:
        assert _classify(s) == "CANCEL"


def test_classify_shipped_aliases():
    for s in ["SHIPPED", "DELIVERED", "WAIT_BUYER_CONFIRM_GOODS", "TRADE_FINISHED"]:
        assert _classify(s) == "SHIP"


def test_classify_unknown_state():
    for s in ["", "FOO", "SOMETHING_ELSE", None]:
        assert _classify(s) == "IGNORE"
