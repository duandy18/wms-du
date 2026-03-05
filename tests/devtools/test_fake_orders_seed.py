# tests/devtools/test_fake_orders_seed.py
from __future__ import annotations

import pytest

from app.services.devtools.fake_orders_service import parse_seed


def test_parse_seed_requires_at_least_one_shop() -> None:
    with pytest.raises(ValueError, match=r"at least one shop"):
        parse_seed({"platform": "PDD", "shops": []})


def test_parse_seed_requires_links_and_variants_and_filled_code() -> None:
    # shops 不是空，但 links 为空：后续 generate 会炸，这里应该提前拦（你们目前 parse_seed 未拦 links 为空的话，这条会失败）
    with pytest.raises(ValueError):
        parse_seed(
            {
                "platform": "PDD",
                "shops": [
                    {"shop_id": "1", "title_prefix": "X", "links": []},
                ],
            }
        )

    # variants 数量必须 1..6
    with pytest.raises(ValueError, match=r"variants must be 1\.\.6"):
        parse_seed(
            {
                "platform": "PDD",
                "shops": [
                    {
                        "shop_id": "1",
                        "title_prefix": "",
                        "links": [
                            {"spu_key": "SPU-1", "title": "T", "variants": []},
                        ],
                    }
                ],
            }
        )

    # filled_code 不能为空（如果你们暂时允许空，这条会失败；但为了“拣货端可测”，我建议这条必须锁死）
    with pytest.raises(ValueError):
        parse_seed(
            {
                "platform": "PDD",
                "shops": [
                    {
                        "shop_id": "1",
                        "title_prefix": "",
                        "links": [
                            {
                                "spu_key": "SPU-1",
                                "title": "T",
                                "variants": [{"variant_name": "V1", "filled_code": ""}],
                            }
                        ],
                    }
                ],
            }
        )


def test_parse_seed_ok_minimal_shape() -> None:
    seed = parse_seed(
        {
            "platform": "PDD",
            "shops": [
                {
                    "shop_id": "1",
                    "title_prefix": "【模拟】",
                    "links": [
                        {
                            "spu_key": "SPU-1",
                            "title": "测试商品",
                            "variants": [{"variant_name": "默认规格", "filled_code": "UT-REPLAY-FSKU-1"}],
                        }
                    ],
                }
            ],
        }
    )
    assert seed.platform == "PDD"
    assert len(seed.shops) == 1
    assert seed.shops[0].shop_id == "1"
    assert len(seed.shops[0].links) == 1
    assert seed.shops[0].links[0].spu_key == "SPU-1"
    assert len(seed.shops[0].links[0].variants) == 1
    assert seed.shops[0].links[0].variants[0].filled_code == "UT-REPLAY-FSKU-1"
