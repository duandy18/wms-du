from fastapi.testclient import TestClient
from app.main import app  # 假设你的 FastAPI 应用在 app.main 中

client = TestClient(app)


# Helper function to get the last audit log (假设你已经实现了此方法)
def get_last_audit_log():
    # 查询数据库或审计日志
    pass


# Helper function to query stock by barcode (假设你已经实现了此方法)
def get_stock_by_barcode(barcode):
    # 查询数据库，获取对应条码的库存信息
    pass


# ---------------------------- 测试: 扫描通路成功 ----------------------------
def test_scan_gateway_transaction_success():
    """测试扫描请求成功并提交事务"""
    response = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "ITEM123"})

    # 验证返回的状态
    assert response.status_code == 200
    assert response.json()["committed"] is True  # 假设 committed 字段表示事务提交成功

    # 验证库存更新是否成功
    stock = get_stock_by_barcode("ITEM123")  # 查询库存
    assert stock.quantity == 10  # 假设库存数量更新为 10


def test_scan_gateway_transaction_failure():
    """测试无效扫描请求触发事务回滚"""
    response = client.post("/scan", json={"node": "putaway", "qty": -1, "barcode": "INVALID"})

    # 验证返回的错误
    assert response.status_code == 400
    assert "error" in response.json()

    # 验证库存没有更新
    stock = get_stock_by_barcode("INVALID")
    assert stock is None  # 假设无效条码不应该存在库存记录


# ---------------------------- 测试: 幂等性 ----------------------------
def test_scan_gateway_idempotency():
    """测试幂等性：相同请求不会造成重复操作"""
    response1 = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "ITEM123"})
    response2 = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "ITEM123"})

    # 验证两次请求的返回都相同，且没有重复操作
    assert response1.json()["scan_ref"] == response2.json()["scan_ref"]  # 假设 scan_ref 是唯一标识
    assert response1.json()["committed"] is True
    assert response2.json()["committed"] is True

    # 验证库存数量未发生变化
    stock = get_stock_by_barcode("ITEM123")
    assert stock.quantity == 10  # 假设库存数量在重复请求后依然为 10


# ---------------------------- 测试: 异常处理 ----------------------------
def test_scan_gateway_invalid_data():
    """测试无效数据：无效条码导致的错误响应"""
    response = client.post(
        "/scan", json={"node": "putaway", "qty": 10, "barcode": "INVALID_BARCODE"}
    )

    # 验证返回的错误响应
    assert response.status_code == 400
    assert "error" in response.json()

    # 确保错误信息写入了审计日志
    error_log = get_last_audit_log()  # 获取最后一条审计日志
    assert error_log["message"] == "Invalid barcode: INVALID_BARCODE"  # 假设记录的错误信息


# ---------------------------- 测试: 事务回滚与数据一致性 ----------------------------
def test_scan_gateway_transaction_rollback():
    """测试事务失败时的回滚，确保数据一致性"""
    response = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "INVALID_ITEM"})

    # 验证返回的错误
    assert response.status_code == 400
    assert "error" in response.json()

    # 确保库存数据没有被修改
    stock = get_stock_by_barcode("INVALID_ITEM")
    assert stock is None  # 假设无效条码不应修改库存


# ---------------------------- 测试: 数据一致性 ----------------------------
def test_scan_gateway_data_consistency():
    """测试并发扫描请求时的数据一致性"""
    response1 = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "ITEM123"})
    response2 = client.post("/scan", json={"node": "putaway", "qty": -5, "barcode": "ITEM123"})

    # 验证库存的最终一致性
    stock = get_stock_by_barcode("ITEM123")
    assert stock.quantity == 5  # 假设第一次加 10，第二次减 5，最终库存为 5


# ---------------------------- 测试: 请求成功和失败的日志验证 ----------------------------
def test_scan_gateway_log_success():
    """测试请求成功时，审计日志记录正确"""
    response = client.post("/scan", json={"node": "putaway", "qty": 10, "barcode": "ITEM123"})

    # 验证日志记录
    log = get_last_audit_log()  # 获取最后一条审计日志
    assert log["scan_ref"] is not None
    assert log["status"] == "success"
    assert log["barcode"] == "ITEM123"


def test_scan_gateway_log_failure():
    """测试请求失败时，审计日志记录错误"""
    response = client.post("/scan", json={"node": "putaway", "qty": -1, "barcode": "INVALID_ITEM"})

    # 验证日志记录错误
    log = get_last_audit_log()  # 获取最后一条审计日志
    assert log["status"] == "error"
    assert "Invalid barcode" in log["message"]
