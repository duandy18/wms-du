from app.oms.services.platform_events_classify import classify


def test_classify_paid_aliases():
    for s in ["PAID", "paid", "Paid", "NEW", "WAIT_SELLER_SEND_GOODS"]:
        assert classify(s) == "PICK"


def test_classify_cancel_aliases():
    for s in ["CANCELED", "CANCELLED", "VOID", "TRADE_CLOSED"]:
        assert classify(s) == "CANCEL"


def test_classify_shipped_aliases():
    for s in ["SHIPPED", "DELIVERED", "WAIT_BUYER_CONFIRM_GOODS", "TRADE_FINISHED"]:
        assert classify(s) == "SHIP"


def test_classify_unknown_state():
    for s in ["", "FOO", "SOMETHING_ELSE", None]:
        assert classify(s) == "IGNORE"
