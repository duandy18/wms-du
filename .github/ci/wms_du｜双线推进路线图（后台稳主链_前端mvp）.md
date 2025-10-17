# WMS-DU｜双线推进路线图（后台稳主链 + 前端 MVP）

> 目标：两周内形成“能点、能扫、能查”的仓库操作台。后台继续稳 Inbound→Putaway→Ledger→Stocks 主链；前端启动最小可用界面并与后台对接。

---

## 一、总体策略
- **双线推进**：后台“瘦而硬”，前端“MVP 可用”。
- **契约先行**：先定接口与状态码；前后端只依赖约定字段，新增字段保持向后兼容。
- **快测优先**：任何改动先写 quick（针刺）再改代码，绿了再提交。
- **一键联调**：后端 `make up && make migrate && make quick`；前端 `pnpm dev`，通过 `VITE_API_URL` 指向后端。

---

## 二、接口契约（MVP 版）

### 1) `POST /inbound/receive`
- **入参**：`{ "item_code": "SNAP-2", "qty": 10, "ref": "PO-20251015-1" }`
- **成功 200**：`{ "accepted_qty": 10 }`
- **失败 409**：`{ "code": "DUPLICATE_REF_LINE" }`

### 2) `POST /putaway`
- **入参**：`{ "item_code":"SNAP-2", "from_loc":"STAGE-1", "to_loc":"A-01-01", "qty":7, "ref":"PW-1" }`
- **成功 200**：`{ "moved": 7 }`
- **失败 409**：`{ "code": "NEGATIVE_STOCK" | "IDEMPOTENT" }`

### 3) `GET /stock/query?item_code=&location=&page=&size=`
- **成功 200**：`{ "items": [{ "item_code","location","qty" }], "total": 42 }`

### 4) `GET /ledger/recent?limit=50`
- **成功 200**：`[{ "ts","reason","ref","delta","item_code","location_id"? }]`

> 说明：前端仅依赖这些字段；新增字段保持可选。

---

## 三、后台任务（继续稳主链）
1) **接口落地**（与契约一致）：
   - `/inbound/receive`、`/putaway`、`/stock/query`、`/ledger/recent`。
2) **错误语义统一**：
   - 幂等/负库存返回 409；批次冲突预留 422；错误码稳定（UI 直接展示）。
3) **日志与可观测**：
   - 在服务层关键节点打结构化日志（item、loc、qty、reason、ref）。
4) **快测集**：
   - 入库幂等 409；负库存 409；并发 putaway（`SKIP LOCKED`）；查询 sum(delta) 与 stocks 对齐。

---

## 四、前端任务（React + Vite + TS + Tailwind + shadcn/ui）

### 项目结构
```
wms-fe/
  src/
    app.tsx
    lib/api.ts           # fetch 包装 + 错误码直达 UI
    pages/
      Inbound.tsx
      Putaway.tsx
      Stock.tsx
      Ledger.tsx
    components/
      Form.tsx
      Table.tsx
      ScanInput.tsx      # 输入框 + 回车模拟扫码
  index.html
  vite.config.ts
  tailwind.config.ts
  package.json
```

### `lib/api.ts`（最小实现）
```ts
export type ApiError = { code: string; message?: string };
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(import.meta.env.VITE_API_URL + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    const data = (await r.json().catch(() => ({}))) as ApiError;
    throw data.code ? data : { code: `HTTP_${r.status}` };
  }
  return r.json() as Promise<T>;
}
```

### Putaway 页面骨架（示例）
```tsx
import { useState } from "react";
import { api } from "../lib/api";
export default function Putaway() {
  const [input, setInput] = useState({ item_code:"", from_loc:"", to_loc:"", qty:1, ref:"" });
  const [msg, setMsg] = useState<string>("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    try {
      const res = await api<{ moved:number }>("/putaway", { method:"POST", body: JSON.stringify(input) });
      setMsg(`上架成功：+${res.moved}`);
    } catch (err: any) {
      setMsg(err.code === "NEGATIVE_STOCK" ? "库存不足" : err.code === "IDEMPOTENT" ? "重复操作（未变更）" : `失败：${err.code||"未知错误"}`);
    }
  }
  return (
    <form onSubmit={submit} className="p-4 grid gap-3 max-w-lg">
      <h1 className="text-xl font-semibold">Putaway</h1>
      <input className="input" placeholder="SKU / 条码" value={input.item_code} onChange={e=>setInput({...input, item_code:e.target.value})}/>
      <div className="grid grid-cols-2 gap-2">
        <input className="input" placeholder="来源库位" value={input.from_loc} onChange={e=>setInput({...input, from_loc:e.target.value})}/>
        <input className="input" placeholder="目标库位" value={input.to_loc} onChange={e=>setInput({...input, to_loc:e.target.value})}/>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input className="input" type="number" min={1} placeholder="数量" value={input.qty} onChange={e=>setInput({...input, qty:Number(e.target.value)})}/>
        <input className="input" placeholder="业务单号 ref" value={input.ref} onChange={e=>setInput({...input, ref:e.target.value})}/>
      </div>
      <button className="btn-primary">提交</button>
      {msg && <p className="text-sm text-gray-700">{msg}</p>}
    </form>
  );
}
```

---

## 五、两周交付节奏（MVP）
**D1–D2**：后端对齐 4 个 API；前端搭好项目并完成 Putaway 表单 + 提示。

**D3–D4**：前端完成 Inbound、Stock、Ledger 三页“能查/能提交流”；后台补 `/stock/query` 分页与筛选。

**D5–D7**：联调打磨：统一错误码与提示、加载态、空状态；加 1 条 Playwright e2e（Putaway 成功 → Stock 刷新）。

**D8–D10**：扫码体验：`ScanInput`（输入聚焦 + 回车即提交，兼容扫码枪）；表单校验、最近操作回显、快捷键（Enter 提交）。

---

## 六、联调与调试手册
- **只跑正在修的 quick**：`PYTHONPATH=. pytest -q -k "putaway" -s`
- **实时日志**：`PYTEST_ADDOPTS="-o log_cli=true"` 打开 pytest 实时日志。
- **API 本地联调**：后端 `uvicorn app.main:app --reload`；前端 `.env.development` 设置 `VITE_API_URL=http://127.0.0.1:8000`。
- **数据库巡检**：
  - `SELECT reason, ref, SUM(delta) FROM stock_ledger GROUP BY 1,2;`
  - `SELECT item_id, location_id, qty FROM stocks WHERE item_id=:i;`
  - 触发器：`SELECT tgname FROM pg_trigger ... WHERE relname='stock_ledger';`

---

## 七、开发者体验（DX）共识
- **接口契约先行**；
- **快测优先**；
- **UI 语义清晰**（409/422 文案）；
- **一键起服务**（后端 Make；前端 `pnpm dev`）。

---

## 八、立即执行的三步
1) 初始化前端项目（Vite + TS + Tailwind）并加入 `lib/api.ts` 与 `pages/Putaway.tsx`；
2) 后端按契约确认/调整 4 个路由的入参与返回；
3) `VITE_API_URL` 指向本地后端，联调 Putaway 表单成功返回 200。
