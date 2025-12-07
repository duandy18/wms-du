# app/adapters/pdd.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ChannelAdapter
from app.models.store import StoreItem
from app.services.store_token_service import (
    StoreTokenExpired,
    StoreTokenNotFound,
    StoreTokenService,
)


@dataclass
class PddCredentials:
    """
    应用级凭据（AppKey / AppSecret / 回调地址）。

    注意：
    - 目前仅作为占位结构存在；
    - 真实的 app_key / app_secret 以后可以从单独的配置表 / 环境变量获取，
      不再耦合在 Store 模型里。
    """

    app_key: Optional[str] = None
    app_secret: Optional[str] = None
    callback_url: Optional[str] = None

    @property
    def ready(self) -> bool:
        return bool(self.app_key and self.app_secret)


class PddAdapter(ChannelAdapter):
    """
    拼多多适配器（骨架版）

    当前职责：
    - 提供一个“预览拉库存请求参数”的工具（按 item_ids → ext_sku_ids 映射）；
    - 预埋店铺级 token 的加载方法（load_token），为后续接真实 API 做准备；
    - fetch/push 仍为占位，实现后续可无缝替换为 SDK/API。
    """

    # ---------- 应用级凭据 ----------
    async def load_credentials(self, session: AsyncSession, *, store_id: int) -> PddCredentials:
        """
        目前不从数据库读取任何 app_key 信息，仅返回空凭据。

        未来如果你决定在某处存放 PDD AppKey/AppSecret，
        可以在这里接入真实配置，例如：
        - 从专门的 app_config 表读取；
        - 从环境变量 / Vault 中读取。
        """
        _ = session  # 当前未使用，仅占位以保留签名
        return PddCredentials()

    # ---------- 店铺级 token（预埋：从 OAuth / 手工凭据中取） ----------
    async def load_token(self, session: AsyncSession, *, store_id: int) -> Optional[str]:
        """
        加载“店铺级”的访问 token（优先 OAuth token，兜底手工 store_tokens），
        方便后续真正调用 PDD 接口时使用。

        现在这个方法暂时不在预览里使用，只是预埋好，
        等你开始接真 API 的时候直接用。
        """
        svc = StoreTokenService(session)
        try:
            rec = await svc.get_token_for_store(store_id=store_id, platform="pdd")
        except (StoreTokenNotFound, StoreTokenExpired):
            return None
        return rec.access_token

    # ---------- 预览：构造拉库存入参（含 ext_sku 映射与签名占位） ----------
    async def build_fetch_preview(
        self, session: AsyncSession, *, store_id: int, item_ids: Sequence[int]
    ) -> Dict[str, Any]:
        """
        返回“将要请求 PDD 拉库存”的预览（不真正调用平台）：

        返回结构示例：
        {
          "creds_ready": true/false,          # 应用级凭据是否齐全（目前恒 False）
          "has_token": true/false,            # 店铺级 token 是否已存在（OAuth/手工）
          "store_id": 1,
          "ext_sku_ids": ["...","..."],       # 与 item_ids 同顺序
          "signature": "pdd-signature-placeholder",
        }
        """
        creds = await self.load_credentials(session, store_id=store_id)
        token = await self.load_token(session, store_id=store_id)

        # 一次性取出并缓存：避免重复 .all() 导致结果耗尽 / 误判未绑定
        result = await session.execute(
            select(StoreItem.item_id, StoreItem.pdd_sku_id).where(
                StoreItem.store_id == store_id,
                StoreItem.item_id.in_(list(map(int, item_ids))),
            )
        )
        rows = result.all()
        mapping = {int(i): (sku or str(int(i))) for i, sku in rows}

        # 按 item_ids 顺序映射；未绑定回落为 item_id 字符串
        ext = [mapping.get(int(iid), str(int(iid))) for iid in item_ids]

        payload = {"store_id": store_id, "ext_sku_ids": ext}
        sig = self.sign(payload)
        return {
            "creds_ready": creds.ready,
            "has_token": bool(token),
            "store_id": store_id,
            "ext_sku_ids": ext,
            "signature": sig,
        }

    # ---------- 拉库存（占位实现；后续接 SDK） ----------
    async def fetch_inventory(self, *, store_id: int, item_ids: Sequence[int]) -> Dict[int, int]:
        """
        占位实现：真正接入时应该做的事情是：

        - 用 build_fetch_preview 中的逻辑构造 ext_sku_ids；
        - 调用 load_token() 拿到 access_token；
        - 按 PDD POP 文档拼接参数 + 签名；
        - 调用 PDD 库存查询接口，解析结果为 {item_id: qty}。

        当前占位实现始终返回 0，确保不会误导你。
        """
        return {int(i): 0 for i in item_ids}

    # ---------- 推库存（占位实现；后续接 SDK） ----------
    async def push_inventory(self, *, store_id: int, items: Sequence[dict]) -> Dict[str, Any]:
        """
        占位实现：真正接入时应该做的事情是：

        - items: [{item_id, qty}, ...] 或带 ext_sku_id 的结构；
        - 通过 load_token() 拿 access_token；
        - 拼签名，调用 PDD 批量推库存 API。

        现在只回显 preview，防止被误当成“已经连上平台”。
        """
        return {"ok": False, "reason": "PDD push not wired yet", "preview": list(items)}

    # ---------- 签名占位 ----------
    def sign(self, payload: dict) -> str:
        """
        签名占位：

        真实实现通常是：
        - 所有参数（含 app_key、timestamp 等）按字典序拼接；
        - 在前后加上 app_secret；
        - 做一次 MD5/SM3 等，得到签名字符串。

        这里先返回固定占位值，便于前端 / 调试页面看到结构是否正确。
        """
        _ = payload  # 当前未使用，仅占位
        return "pdd-signature-placeholder"
