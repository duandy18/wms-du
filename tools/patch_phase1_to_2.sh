#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-"$(pwd)"}
cd "$ROOT"

say() { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m[WARN] %s\033[0m\n" "$*"; }

mk() { mkdir -p "$1"; }
wr() { dst="$1"; shift; mk "$(dirname "$dst")"; printf "%s" "$*" > "$dst"; say "write $dst"; }
app() { dst="$1"; shift; mk "$(dirname "$dst")"; printf "%s" "$*" >> "$dst"; say "append $dst"; }

# --- 1) 类型与工具 ---
wr src/types/inventory.ts "$(cat <<'TS'
export type InventoryTile = {
  item_id: number
  name: string
  spec: string
  qty_total: number
  top_locations: { location: string; qty: number }[]
  main_batch?: string
  earliest_expiry?: string
  flags?: { near_expiry?: boolean; expired?: boolean }
}

export type LocationBreakdown = {
  location: string
  qty: number
}

export type BatchBreakdown = {
  batch: string
  production_date?: string
  expiry_date?: string
  qty: number
}

export type InventoryDistribution = {
  item_id: number
  name: string
  locations: LocationBreakdown[]
  batches: BatchBreakdown[]
}
TS
)"

wr src/lib/api.ts "$(cat <<'TS'
export const API_BASE = import.meta.env.VITE_API_URL || ''
export const isMSW = (window as any).__MSW_ENABLED__ === true

export async function apiGet<T>(path: string): Promise<T> {
  const url = (API_BASE ? API_BASE.replace(/\/$/, '') : '') + path
  const res = await fetch(url)
  if (!res.ok) throw new Error(`[GET ${path}] ${res.status}`)
  return res.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: any): Promise<T> {
  const url = (API_BASE ? API_BASE.replace(/\/$/, '') : '') + path
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`[POST ${path}] ${res.status}`)
  return res.json() as Promise<T>
}
TS
)"

wr src/lib/csv.ts "$(cat <<'TS'
export function toCSV<T extends Record<string, any>>(rows: T[]): string {
  if (!rows.length) return ''
  const headers = Object.keys(rows[0])
  const esc = (v: any) => {
    const s = v == null ? '' : String(v)
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
  }
  const lines = [headers.join(','), ...rows.map(r => headers.map(h => esc(r[h])).join(','))]
  return lines.join('\n')
}

export function downloadCSV(filename: string, content: string) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
TS
)"

# --- 2) 通用组件 ---
wr src/components/common/ApiBadge.tsx "$(cat <<'TSX'
import React from 'react'

export default function ApiBadge() {
  const api = import.meta.env.VITE_API_URL || '—'
  const msw = (window as any).__MSW_ENABLED__ === true
  return (
    <div className="inline-flex items-center gap-2 rounded-2xl px-3 py-1 text-sm shadow bg-neutral-100">
      <span className="font-medium">API:</span>
      <code>{api}</code>
      <span className={"ml-2 rounded-full px-2 py-0.5 text-xs " + (msw ? 'bg-emerald-200' : 'bg-amber-200') }>
        {msw ? 'MSW: on' : 'MSW: off'}
      </span>
    </div>
  )
}
TSX
)"

# --- 3) Snapshot 页面与子组件 ---
wr src/components/snapshot/TileCard.tsx "$(cat <<'TSX'
import React from 'react'
import type { InventoryTile } from '../../types/inventory'

export function TileCard({ t, onOpen }: { t: InventoryTile; onOpen: () => void }) {
  return (
    <div className="rounded-2xl shadow p-4 hover:shadow-lg transition cursor-pointer bg-white" onClick={onOpen}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-base font-semibold">{t.name}</div>
          <div className="text-xs text-neutral-500">#{t.item_id} · {t.spec}</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tabular-nums">{t.qty_total}</div>
          {t.flags?.expired ? (
            <span className="mt-1 inline-block rounded px-2 py-0.5 text-xs bg-red-100 text-red-700">已过期</span>
          ) : t.flags?.near_expiry ? (
            <span className="mt-1 inline-block rounded px-2 py-0.5 text-xs bg-amber-100 text-amber-700">临期</span>
          ) : null}
        </div>
      </div>
      <div className="mt-3 text-xs text-neutral-600">
        <div>Top 库位：{t.top_locations.map(l => `${l.location}(${l.qty})`).join('、') || '—'}</div>
        <div>主批次：{t.main_batch || '—'}，最早到期：{t.earliest_expiry || '—'}</div>
      </div>
    </div>
  )
}
TSX
)"

wr src/components/snapshot/InventoryDrawer.tsx "$(cat <<'TSX'
import React from 'react'
import type { InventoryDistribution } from '../../types/inventory'

export function InventoryDrawer({ open, onClose, data }: { open: boolean; onClose: () => void; data?: InventoryDistribution }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="w-[440px] max-w-[90vw] h-full bg-white shadow-xl p-5 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">{data?.name ?? '库存分布'}</div>
          <button className="rounded-xl px-3 py-1 bg-neutral-100 hover:bg-neutral-200" onClick={onClose}>关闭</button>
        </div>
        <div className="mt-4 space-y-6">
          <section>
            <div className="text-sm font-medium mb-2">库位分布</div>
            <div className="space-y-1 text-sm">
              {data?.locations?.length ? data!.locations.map((l, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-24 text-neutral-600">{l.location}</div>
                  <div className="flex-1 h-2 bg-neutral-100 rounded-full overflow-hidden">
                    <div className="h-full bg-neutral-400" style={{ width: 'calc(min(100%, ' + l.qty + ' * 1%))' }} />
                  </div>
                  <div className="w-10 text-right tabular-nums">{l.qty}</div>
                </div>
              )) : <div className="text-neutral-400">无数据</div>}
            </div>
          </section>
          <section>
            <div className="text-sm font-medium mb-2">批次（FEFO）</div>
            <div className="space-y-1 text-sm">
              {data?.batches?.length ? data!.batches.map((b, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{b.batch}</div>
                    <div className="text-xs text-neutral-500">生产 {b.production_date || '—'} · 到期 {b.expiry_date || '—'}</div>
                  </div>
                  <div className="tabular-nums">{b.qty}</div>
                </div>
              )) : <div className="text-neutral-400">无数据</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
TSX
)"

wr src/pages/SnapshotPage.tsx "$(cat <<'TSX'
import React from 'react'
import { useEffect, useMemo, useState } from 'react'
import { apiGet } from '../lib/api'
import type { InventoryTile, InventoryDistribution } from '../types/inventory'
import { TileCard } from '../components/snapshot/TileCard'
import { InventoryDrawer } from '../components/snapshot/InventoryDrawer'
import ApiBadge from '../components/common/ApiBadge'

function useQuery<T>(key: string, loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setLoading(true)
    loader().then(d => alive && setData(d)).catch(e => alive && setError(String(e))).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [key])
  return { data, error, loading }
}

export default function SnapshotPage() {
  const [view, setView] = useState<'tile' | 'table'>('tile')
  const q = useQuery('snapshot', () => apiGet<InventoryTile[]>('/snapshot/inventory'))
  const [openId, setOpenId] = useState<number | null>(null)
  const [dist, setDist] = useState<InventoryDistribution | undefined>()

  useEffect(() => {
    if (openId != null) {
      apiGet<InventoryDistribution>(`/snapshot/location-heat?item_id=${openId}`).then(setDist).catch(() => setDist(undefined))
    }
  }, [openId])

  const table = useMemo(() => q.data || [], [q.data])

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">库存快照</div>
        <ApiBadge />
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => setView('tile')} className={"rounded-xl px-3 py-1 " + (view==='tile' ? 'bg-black text-white' : 'bg-neutral-100')}>图块</button>
        <button onClick={() => setView('table')} className={"rounded-xl px-3 py-1 " + (view==='table' ? 'bg-black text-white' : 'bg-neutral-100')}>表格</button>
      </div>

      {q.loading && <div className="text-neutral-500">加载中…</div>}
      {q.error && <div className="text-red-600">加载失败：{q.error}</div>}
      {!q.loading && !q.error && !q.data?.length && <div className="text-neutral-400">空空如也，去收一批货吧。</div>}

      {view === 'tile' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {table.map(t => (
            <TileCard key={t.item_id} t={t} onOpen={() => setOpenId(t.item_id)} />
          ))}
        </div>
      )}

      {view === 'table' && (
        <div className="overflow-x-auto">
          <table className="min-w-[720px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">ID</th>
                <th className="py-2 pr-3">名称</th>
                <th className="py-2 pr-3">规格</th>
                <th className="py-2 pr-3">总量</th>
                <th className="py-2 pr-3">Top2 库位</th>
                <th className="py-2 pr-3">主批次</th>
                <th className="py-2 pr-3">最早到期</th>
                <th className="py-2 pr-3">状态</th>
              </tr>
            </thead>
            <tbody>
              {table.map(t => (
                <tr key={t.item_id} className="border-t hover:bg-neutral-50 cursor-pointer" onClick={() => setOpenId(t.item_id)}>
                  <td className="py-2 pr-3 tabular-nums">{t.item_id}</td>
                  <td className="py-2 pr-3">{t.name}</td>
                  <td className="py-2 pr-3">{t.spec}</td>
                  <td className="py-2 pr-3 tabular-nums">{t.qty_total}</td>
                  <td className="py-2 pr-3">{t.top_locations.map(l => `${l.location}(${l.qty})`).join('、')}</td>
                  <td className="py-2 pr-3">{t.main_batch || '—'}</td>
                  <td className="py-2 pr-3">{t.earliest_expiry || '—'}</td>
                  <td className="py-2 pr-3">{t.flags?.expired ? '已过期' : t.flags?.near_expiry ? '临期' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <InventoryDrawer open={openId != null} onClose={() => setOpenId(null)} data={dist} />
    </div>
  )
}
TSX
)"

# --- 4) 三大任务页（最小可用+zod 校验提示位） ---
wr src/pages/OutboundPage.tsx "$(cat <<'TSX'
import React, { useState } from 'react'
import { z } from 'zod'
import { apiPost, apiGet } from '../lib/api'

const schema = z.object({
  ref: z.string().min(1, 'ref 必填'),
  item_id: z.coerce.number().min(1, 'item 必填'),
  location_id: z.coerce.number().optional(),
  qty: z.coerce.number().min(1, '数量必须 > 0')
})

type StockHint = { available: number }

export default function OutboundPage(){
  const [form, setForm] = useState({ ref:'', item_id:0, location_id:undefined as number|undefined, qty:1 })
  const [msg, setMsg] = useState<string>('')

  const onSubmit = async () => {
    const r = schema.safeParse(form)
    if (!r.success) { setMsg(r.error.issues.map(i=>i.message).join('、')); return }
    try {
      const res = await apiPost<{ok:boolean}>('/outbound/commit', form)
      setMsg(res.ok ? '出库成功' : '出库失败')
    } catch(e:any){ setMsg('失败：'+e.message) }
  }

  const checkAvail = async () => {
    if (!form.item_id) return
    try {
      const data = await apiGet<StockHint>(`/stock/query?item_id=${form.item_id}`)
      setMsg(`可用量：${data.available}`)
    } catch {}
  }

  return (
    <div className="p-4 space-y-3">
      <div className="text-xl font-semibold">出库</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input placeholder="ref（幂等）" className="rounded-xl border p-2" value={form.ref} onChange={e=>setForm({...form, ref:e.target.value})} />
        <input placeholder="item_id" className="rounded-xl border p-2" value={form.item_id} onChange={e=>setForm({...form, item_id:Number(e.target.value||0)})} onBlur={checkAvail} />
        <input placeholder="location_id(可选)" className="rounded-xl border p-2" value={form.location_id||''} onChange={e=>setForm({...form, location_id:e.target.value?Number(e.target.value):undefined})} />
        <input placeholder="qty" className="rounded-xl border p-2" value={form.qty} onChange={e=>setForm({...form, qty:Number(e.target.value||0)})} />
      </div>
      <div className="flex gap-2">
        <button className="rounded-xl px-4 py-2 bg-black text-white" onClick={onSubmit}>提交</button>
        <button className="rounded-xl px-3 py-2 bg-neutral-100" onClick={checkAvail}>查询可用量</button>
      </div>
      {msg && <div className="text-sm text-neutral-700">{msg}</div>}
    </div>
  )
}
TSX
)"

wr src/pages/InboundPage.tsx "$(cat <<'TSX'
import React from 'react'
export default function InboundPage(){
  return (
    <div className="p-4 space-y-2">
      <div className="text-xl font-semibold">收货（MSW）</div>
      <div className="text-neutral-600">左侧待收列表 + 表单占位（沿用你现有 /inbound/receive handler）。</div>
    </div>
  )
}
TSX
)"

wr src/pages/PutawayPage.tsx "$(cat <<'TSX'
import React from 'react'
export default function PutawayPage(){
  return (
    <div className="p-4 space-y-2">
      <div className="text-xl font-semibold">上架（已具备）</div>
      <div className="text-neutral-600">此页挂接你现有 Putaway MVP 组件或表单。</div>
    </div>
  )
}
TSX
)"

wr src/pages/tools/StockToolPage.tsx "$(cat <<'TSX'
import React, { useState } from 'react'
import { apiGet } from '../../lib/api'
import { downloadCSV, toCSV } from '../../lib/csv'

export default function StockToolPage(){
  const [item, setItem] = useState('')
  const [loc, setLoc] = useState('')
  const [rows, setRows] = useState<any[]>([])

  const search = async () => {
    const qs = new URLSearchParams({ item_id: item, location_id: loc })
    const data = await apiGet<any[]>(`/stock/query?${qs}`)
    setRows(data)
  }

  const exportCsv = () => {
    const csv = toCSV(rows)
    downloadCSV('stock.csv', csv)
  }

  return (
    <div className="p-4 space-y-3">
      <div className="text-xl font-semibold">Stock 工具</div>
      <div className="flex gap-2">
        <input placeholder="item_id" className="rounded-xl border p-2" value={item} onChange={e=>setItem(e.target.value)} />
        <input placeholder="location_id" className="rounded-xl border p-2" value={loc} onChange={e=>setLoc(e.target.value)} />
        <button className="rounded-xl px-3 py-2 bg-black text-white" onClick={search}>查询</button>
        <button className="rounded-xl px-3 py-2 bg-neutral-100" onClick={exportCsv} disabled={!rows.length}>导出 CSV</button>
      </div>
      {!rows.length ? <div className="text-neutral-400">空态：还没有结果。</div> : (
        <div className="overflow-x-auto">
          <table className="min-w-[720px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                {Object.keys(rows[0]).map(h => <th key={h} className="py-2 pr-3">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r,i)=> (
                <tr key={i} className="border-t">
                  {Object.values(r).map((v,j)=> <td key={j} className="py-2 pr-3">{String(v)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
TSX
)"

wr src/pages/tools/LedgerToolPage.tsx "$(cat <<'TSX'
import React, { useEffect, useState } from 'react'
import { apiGet } from '../../lib/api'

type Row = { id: number; item_id:number; location_id:number; delta:number; reason:string; ref:string; at:string }

export default function LedgerToolPage(){
  const [rows, setRows] = useState<Row[]>([])
  const [sum, setSum] = useState(0)
  useEffect(()=>{
    apiGet<Row[]>('/ledger/recent').then(r=>{ setRows(r); setSum(r.reduce((a,b)=>a+b.delta,0)) })
  },[])
  return (
    <div className="p-4 space-y-3">
      <div className="text-xl font-semibold">Ledger 最近流水</div>
      <div className="text-sm text-neutral-600">Σdelta：<span className="tabular-nums font-semibold">{sum}</span></div>
      {!rows.length ? <div className="text-neutral-400">暂无流水</div> : (
        <div className="overflow-x-auto">
          <table className="min-w-[720px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">id</th><th className="py-2 pr-3">item</th><th className="py-2 pr-3">loc</th>
                <th className="py-2 pr-3">delta</th><th className="py-2 pr-3">reason</th><th className="py-2 pr-3">ref</th><th className="py-2 pr-3">at</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r=> (
                <tr key={r.id} className="border-top">
                  <td className="py-2 pr-3">{r.id}</td>
                  <td className="py-2 pr-3">{r.item_id}</td>
                  <td className="py-2 pr-3">{r.location_id}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.delta}</td>
                  <td className="py-2 pr-3">{r.reason}</td>
                  <td className="py-2 pr-3">{r.ref}</td>
                  <td className="py-2 pr-3">{r.at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
TSX
)"

# --- 5) MSW handlers ---
wr src/mocks/handlers/snapshot.ts "$(cat <<'TS'
import { http, HttpResponse } from 'msw'

const tiles = [
  { item_id:1, name:'双拼猫粮', spec:'1.5kg', qty_total:100, top_locations:[{location:'A1', qty:60},{location:'B3', qty:40}], main_batch:'B202509', earliest_expiry:'2026-01-10', flags:{ near_expiry:false } },
  { item_id:2, name:'冻干三文鱼', spec:'500g', qty_total:42, top_locations:[{location:'C2', qty:20},{location:'A2', qty:22}], main_batch:'S202510', earliest_expiry:'2026-02-01', flags:{} },
]

export const snapshotHandlers = [
  http.get('/snapshot/inventory', () => HttpResponse.json(tiles)),
  http.get('/snapshot/kpis', () => HttpResponse.json({ total_items: tiles.length, total_qty: tiles.reduce((a,b)=>a+b.qty_total,0) })),
  http.get('/snapshot/todo-inbound', () => HttpResponse.json([{ id:'IN-1', supplier:'喵厂', items:3 }])),
  http.get('/snapshot/todo-putaway', () => HttpResponse.json([{ id:'PW-1', lines:5 }])),
  http.get('/snapshot/location-heat', ({ request }) => {
    const u = new URL(request.url)
    const id = Number(u.searchParams.get('item_id'))
    const t = tiles.find(x=>x.item_id===id)
    if (!t) return HttpResponse.json({ item_id:id, name:'未知', locations:[], batches:[] })
    return HttpResponse.json({
      item_id: t.item_id,
      name: t.name,
      locations: [
        { location:'A1', qty:60 }, { location:'B3', qty:40 }, { location:'STAGE', qty:5 }
      ],
      batches: [
        { batch:'B202509', production_date:'2025-09-01', expiry_date:'2026-01-10', qty:70 },
        { batch:'B202510', production_date:'2025-10-01', expiry_date:'2026-02-01', qty:35 }
      ]
    })
  }),
]
TS
)"

wr src/mocks/handlers/outbound.ts "$(cat <<'TS'
import { http, HttpResponse } from 'msw'

export const outboundHandlers = [
  http.post('/outbound/commit', async ({ request }) => {
    const body = await request.json() as any
    if (!body?.ref || !body?.item_id || !body?.qty) return HttpResponse.json({ ok:false, error:'bad request' }, { status:400 })
    // 幂等模拟：同一 ref 第二次返回 200 但提示幂等
    const key = 'ref:'+body.ref
    const once = (globalThis as any).__out_ref || ((globalThis as any).__out_ref = new Set())
    const first = !once.has(key)
    once.add(key)
    return HttpResponse.json({ ok:true, idempotent: !first })
  })
]
TS
)"

wr src/mocks/handlers/index.ts "$(cat <<'TS'
export * from './snapshot'
export * from './outbound'
// 保留：已实现的 inbound/putaway/stock/ledger handlers 在你现有代码处
TS
)"

# 若无 browser.ts，则创建最小版本
if [ ! -f src/mocks/browser.ts ]; then
wr src/mocks/browser.ts "$(cat <<'TS'
import { setupWorker } from 'msw/browser'
import * as H from './handlers'

const allHandlers = [
  ...H.snapshotHandlers,
  ...H.outboundHandlers,
]

export const worker = setupWorker(...allHandlers)
TS
)"
fi

# --- 6) 路由注入：在存在的 router.tsx 中插入；若不存在则创建 ---
if [ -f src/router.tsx ]; then
  if grep -q "// \\[ROUTE_MARKER\\]" src/router.tsx; then
    app src/router.tsx "\n      {/* Phase1→2 */}\n      <Route path=\"/\" element={<SnapshotPage/>} />\n      <Route path=\"/inbound\" element={<InboundPage/>} />\n      <Route path=\"/putaway\" element={<PutawayPage/>} />\n      <Route path=\"/outbound\" element={<OutboundPage/>} />\n      <Route path=\"/tools/stock\" element={<StockToolPage/>} />\n      <Route path=\"/tools/ledger\" element={<LedgerToolPage/>} />\n      {/* /Phase1→2 */}\n"
    say "routes appended after // [ROUTE_MARKER]"
  else
    warn "未找到 // [ROUTE_MARKER]，请手动在 <Routes> 内加入 6 条路由（见文档）"
  fi
else
wr src/router.tsx "$(cat <<'TSX'
import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import SnapshotPage from './pages/SnapshotPage'
import InboundPage from './pages/InboundPage'
import PutawayPage from './pages/PutawayPage'
import OutboundPage from './pages/OutboundPage'
import StockToolPage from './pages/tools/StockToolPage'
import LedgerToolPage from './pages/tools/LedgerToolPage'

export default function AppRouter(){
  return (
    <BrowserRouter>
      <div className="p-3 border-b flex items-center gap-3 bg-white sticky top-0 z-40">
        <Link to="/" className="font-semibold">WMS</Link>
        <nav className="flex gap-2 text-sm">
          <Link to="/inbound" className="rounded px-2 py-1 hover:bg-neutral-100">Inbound</Link>
          <Link to="/putaway" className="rounded px-2 py-1 hover:bg-neutral-100">Putaway</Link>
          <Link to="/outbound" className="rounded px-2 py-1 hover:bg-neutral-100">Outbound</Link>
          <Link to="/tools/stock" className="rounded px-2 py-1 hover:bg-neutral-100">Stock</Link>
          <Link to="/tools/ledger" className="rounded px-2 py-1 hover:bg-neutral-100">Ledger</Link>
        </nav>
      </div>
      <Routes>
        {/* Phase1→2 */}
        <Route path="/" element={<SnapshotPage/>} />
        <Route path="/inbound" element={<InboundPage/>} />
        <Route path="/putaway" element={<PutawayPage/>} />
        <Route path="/outbound" element={<OutboundPage/>} />
        <Route path="/tools/stock" element={<StockToolPage/>} />
        <Route path="/tools/ledger" element={<LedgerToolPage/>} />
        {/* /Phase1→2 */}
      </Routes>
    </BrowserRouter>
  )
}
TSX
)"
fi

say "补丁生成完成。建议执行：
  pnpm i zod msw zustand @tanstack/react-table @radix-ui/react-icons swiper recharts
  pnpm dev"
