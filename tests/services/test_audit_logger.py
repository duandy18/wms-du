import pytest
import re

pytestmark = pytest.mark.asyncio

def test_audit_logger_masking(capsys):
    from app.services.audit_logger import audit_log
    audit_log("services", "inventory", "adjust", meta={"receiver":"张三", "phone":"13812345678"})
    out = capsys.readouterr().out
    # 基本字段
    assert "adjust" in out and "inventory" in out
    # 手机脱敏（留前3后4）
    assert re.search(r"138\*+\d{4}", out)
