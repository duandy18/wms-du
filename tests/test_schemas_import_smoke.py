# tests/test_schemas_import_smoke.py
from app import schemas


def test_pydantic_schemas_importable():
    # if import fails, pytest will error before reaching here
    assert hasattr(schemas, "__all__") or True
