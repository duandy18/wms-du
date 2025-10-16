#!/usr/bin/env bash
set -euo pipefail
ROOT=${1:-"$(pwd)"}
cd "$ROOT"

say() { printf "\033[1;32m==> %s\033[0m\n" "$*"; }
warn(){ printf "\033[1;33m[WARN] %s\033[0m\n" "$*"; }

mk() { mkdir -p "$1"; }
wr() { dst="$1"; shift; mk "$(dirname "$dst")"; printf "%s" "$*" > "$dst"; say "write $dst"; }
app() { dst="$1"; shift; mk "$(dirname "$dst")"; printf "%s" "$*" >> "$dst"; say "append $dst"; }

# --- 1) Pages: /tasks, /batches, /moves ---
wr src/pages/TasksPage.tsx "$(cat <<'TSX'
import React, { useEffect, useState } from 'react'
type Task = { id:string; type:'INBOUND'|'PUTAWAY'|'OUTBOUND'; assignee?:string; status:'READY'|'IN_PROGRESS'|'DONE'|'CANCELED'; updated_at:string; lines?:number }
export default function TasksPage(){
  const [rows, setRows] = useState<Task[]>([])
  const [q, setQ] = useState('')
  const load = async () => {
    const url = '/tasks/list' + (q ? ('?q='+encodeURIComponent(q)) : '')
    const res = await fetch(url); if(!res.ok) throw new Error(String(res.status))
    setRows(await res.json())
  }
  useEffect(()=>{ load().catch(()=>{}) },[])
  const goto = (t: Task) => {
    if (t.type === 'INBOUND') location.assign('/inbound')
    else if (t.type === 'PUTAWAY') location.assign('/putaway')
    else location.assign('/outbound')
  }
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">Tasks</div>
        <div className="flex gap-2">
          <input placeholder="搜索 type/assignee" className="rounded-xl border p-2" value={q} onChange={e=>setQ(e.target.value)} />
          <button className="rounded-xl px-3 py-2 bg-neutral-100" onClick={load}>搜索</button>
        </div>
      </div>
      {!rows.length ? <div className="text-neutral-400">暂无任务</div> : (
        <div className="overflow-x-auto">
          <table className="min-w-[760px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">id</th>
                <th className="py-2 pr-3">type</th>
                <th className="py-2 pr-3">assignee</th>
                <th className="py-2 pr-3">status</th>
                <th className="py-2 pr-3">lines</th>
                <th className="py-2 pr-3">updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t hover:bg-neutral-50 cursor-pointer" onClick={()=>goto(r)}>
                  <td className="py-2 pr-3">{r.id}</td>
                  <td className="py-2 pr-3">{r.type}</td>
                  <td className="py-2 pr-3">{r.assignee || '—'}</td>
                  <td className="py-2 pr-3">{r.status}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.lines ?? 0}</td>
                  <td className="py-2 pr-3">{new Date(r.updated_at).toLocaleString()}</td>
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

wr src/pages/BatchesPage.tsx "$(cat <<'TSX'
import React, { useEffect, useState } from 'react'
type Row = { id:number; item_id:number; item_name:string; batch_code:string; production_date:string; expiry_date:string; qty:number; near?:boolean; expired?:boolean }
export default function BatchesPage(){
  const [rows, setRows] = useState<Row[]>([])
  const [item, setItem] = useState('')
  const load = async () => {
    const qs = item ? ('?item_id='+encodeURIComponent(item)) : ''
    const res = await fetch('/batches/list'+qs); if(!res.ok) throw new Error(String(res.status))
    setRows(await res.json())
  }
  useEffect(()=>{ load().catch(()=>{}) },[])
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">Batches</div>
        <div className="flex gap-2">
          <input placeholder="item_id" className="rounded-xl border p-2" value={item} onChange={e=>setItem(e.target.value)} />
          <button className="rounded-xl px-3 py-2 bg-neutral-100" onClick={load}>查询</button>
        </div>
      </div>
      {!rows.length ? <div className="text-neutral-400">暂无批次</div> : (
        <div className="overflow-x-auto">
          <table className="min-w-[840px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">batch</th>
                <th className="py-2 pr-3">item</th>
                <th className="py-2 pr-3">production</th>
                <th className="py-2 pr-3">expiry</th>
                <th className="py-2 pr-3">qty</th>
                <th className="py-2 pr-3">flags</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t">
                  <td className="py-2 pr-3">{r.batch_code}</td>
                  <td className="py-2 pr-3">#{r.item_id} {r.item_name}</td>
                  <td className="py-2 pr-3">{r.production_date}</td>
                  <td className="py-2 pr-3">{r.expiry_date}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.qty}</td>
                  <td className="py-2 pr-3">{r.expired ? '已过期' : r.near ? '临期' : '—'}</td>
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

wr src/pages/MovesPage.tsx "$(cat <<'TSX'
import React, { useEffect, useState } from 'react'
type Row = { id:number; item_id:number; from_location?:string; to_location?:string; delta:number; reason:string; ref?:string; batch_code?:string; at:string }
export default function MovesPage(){
  const [rows, setRows] = useState<Row[]>([])
  const [item, setItem] = useState('')
  const load = async () => {
    const qs = item ? ('?item_id='+encodeURIComponent(item)) : ''
    const res = await fetch('/moves/recent'+qs); if(!res.ok) throw new Error(String(res.status))
    setRows(await res.json())
  }
  useEffect(()=>{ load().catch(()=>{}) },[])
  const sum = rows.reduce((a,b)=>a+b.delta,0)
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">Moves / Ledger</div>
        <div className="flex gap-2">
          <input placeholder="item_id" className="rounded-xl border p-2" value={item} onChange={e=>setItem(e.target.value)} />
          <button className="rounded-xl px-3 py-2 bg-neutral-100" onClick={load}>查询</button>
        </div>
      </div>
      <div className="text-sm text-neutral-600">Σdelta：<span className="tabular-nums font-semibold">{sum}</span></div>
      {!rows.length ? <div className="text-neutral-400">暂无流水</div> : (
        <div className="overflow-x-auto">
          <table className="min-w-[960px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">id</th>
                <th className="py-2 pr-3">item</th>
                <th className="py-2 pr-3">from</th>
                <th className="py-2 pr-3">to</th>
                <th className="py-2 pr-3">delta</th>
                <th className="py-2 pr-3">batch</th>
                <th className="py-2 pr-3">reason</th>
                <th className="py-2 pr-3">ref</th>
                <th className="py-2 pr-3">at</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-t">
                  <td className="py-2 pr-3">{r.id}</td>
                  <td className="py-2 pr-3">{r.item_id}</td>
                  <td className="py-2 pr-3">{r.from_location || '—'}</td>
                  <td className="py-2 pr-3">{r.to_location || '—'}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.delta}</td>
                  <td className="py-2 pr-3">{r.batch_code || '—'}</td>
                  <td className="py-2 pr-3">{r.reason}</td>
                  <td className="py-2 pr-3">{r.ref || '—'}</td>
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

# --- 2) MSW handlers ---
wr src/mocks/handlers/tasks.ts "$(cat <<'TS'
import { http, HttpResponse } from 'msw'

const sample = [
  { id:'T-IN-1001', type:'INBOUND', assignee:'alice', status:'READY', updated_at:new Date().toISOString(), lines:3 },
  { id:'T-PW-2001', type:'PUTAWAY', assignee:'bob', status:'IN_PROGRESS', updated_at:new Date().toISOString(), lines:5 },
  { id:'T-OUT-3001', type:'OUTBOUND', assignee:null, status:'READY', updated_at:new Date().toISOString(), lines:2 }
]

export const taskHandlers = [
  http.get('/tasks/list', ({ request }) => {
    const u = new URL(request.url)
    const q = (u.searchParams.get('q') || '').toLowerCase()
    const filtered = sample.filter(t =>
      !q || [t.id, t.type, t.assignee, t.status].filter(Boolean).join(' ').toLowerCase().includes(q)
    )
    return HttpResponse.json(filtered)
  }),
  http.patch('/tasks/:id/status', async ({ params, request }) => {
    const { id } = params as { id:string }
    const body = await request.json() as any
    const idx = sample.findIndex(s => s.id === id)
    if (idx === -1) return HttpResponse.json({ ok:false }, { status:404 })
    if (body?.status) sample[idx].status = body.status
    sample[idx].updated_at = new Date().toISOString()
    return HttpResponse.json({ ok:true, task: sample[idx] })
  })
]
TS
)"

wr src/mocks/handlers/batches.ts "$(cat <<'TS'
import { http, HttpResponse } from 'msw'

const batches = [
  { id:1, item_id:1, item_name:'双拼猫粮', batch_code:'B202509', production_date:'2025-09-01', expiry_date:'2026-01-10', qty:70, near:false, expired:false },
  { id:2, item_id:1, item_name:'双拼猫粮', batch_code:'B202510', production_date:'2025-10-01', expiry_date:'2026-02-01', qty:35, near:true, expired:false },
  { id:3, item_id:2, item_name:'冻干三文鱼', batch_code:'S202510', production_date:'2025-10-05', expiry_date:'2026-04-01', qty:20, near:false, expired:false }
]

export const batchHandlers = [
  http.get('/batches/list', ({ request }) => {
    const u = new URL(request.url)
    const item = Number(u.searchParams.get('item_id') || '0')
    const list = item ? batches.filter(b => b.item_id === item) : batches
    return HttpResponse.json(list)
  })
]
TS
)"

wr src/mocks/handlers/moves.ts "$(cat <<'TS'
import { http, HttpResponse } from 'msw'

let counter = 100
const now = () => new Date().toISOString()
const moves = [
  { id: ++counter, item_id:1, from_location:null, to_location:'STAGE', delta:+10, reason:'INBOUND', ref:'PO-1', batch_code:'B202509', at: now() },
  { id: ++counter, item_id:1, from_location:'STAGE', to_location:'A1', delta:+10, reason:'PUTAWAY', ref:'PW-1', batch_code:'B202509', at: now() },
  { id: ++counter, item_id:1, from_location:'A1', to_location:null, delta:-3, reason:'OUTBOUND', ref:'SO-1', batch_code:'B202509', at: now() },
]

export const moveHandlers = [
  http.get('/moves/recent', ({ request }) => {
    const u = new URL(request.url)
    const item = Number(u.searchParams.get('item_id') || '0')
    const list = item ? moves.filter(m => m.item_id === item) : moves
    return HttpResponse.json(list)
  })
]
TS
)"

# --- 3) handlers index export ---
if [ -f src/mocks/handlers/index.ts ]; then
  app src/mocks/handlers/index.ts "$(cat <<'TS'

export * from './tasks'
export * from './batches'
export * from './moves'
TS
)"
else
  wr src/mocks/handlers/index.ts "$(cat <<'TS'
export * from './tasks'
export * from './batches'
export * from './moves'
TS
)"
fi

# --- 4) Router injection or creation ---
inject_routes() {
app src/router.tsx "$(cat <<'TSX'

        {/* Phase2-shells */}
        <Route path="/tasks" element={<TasksPage/>} />
        <Route path="/batches" element={<BatchesPage/>} />
        <Route path="/moves" element={<MovesPage/>} />
        {/* /Phase2-shells */}
TSX
)"
say "routes appended (Phase2-shells)"
}

if [ -f src/router.tsx ]; then
  # Ensure imports exist
  if ! grep -q "from './pages/TasksPage'" src/router.tsx; then
    sed -i "1 a\\import TasksPage from './pages/TasksPage'\\nimport BatchesPage from './pages/BatchesPage'\\nimport MovesPage from './pages/MovesPage'" src/router.tsx
    say "import lines added to src/router.tsx"
  fi
  if grep -q "<Routes>" src/router.tsx; then
    inject_routes
  else
    warn "无法自动注入路由：未检测到 <Routes> 标签，请手动加入 3 条路由（/tasks,/batches,/moves）"
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
import TasksPage from './pages/TasksPage'
import BatchesPage from './pages/BatchesPage'
import MovesPage from './pages/MovesPage'

export default function AppRouter(){
  return (
    <BrowserRouter>
      <div className="p-3 border-b flex items-center gap-3 bg-white sticky top-0 z-40">
        <Link to="/" className="font-semibold">WMS</Link>
        <nav className="flex gap-2 text-sm">
          <Link to="/inbound" className="rounded px-2 py-1 hover:bg-neutral-100">Inbound</Link>
          <Link to="/putaway" className="rounded px-2 py-1 hover:bg-neutral-100">Putaway</Link>
          <Link to="/outbound" className="rounded px-2 py-1 hover:bg-neutral-100">Outbound</Link>
          <Link to="/tasks" className="rounded px-2 py-1 hover:bg-neutral-100">Tasks</Link>
          <Link to="/batches" className="rounded px-2 py-1 hover:bg-neutral-100">Batches</Link>
          <Link to="/moves" className="rounded px-2 py-1 hover:bg-neutral-100">Moves</Link>
          <Link to="/tools/stock" className="rounded px-2 py-1 hover:bg-neutral-100">Stock</Link>
          <Link to="/tools/ledger" className="rounded px-2 py-1 hover:bg-neutral-100">Ledger</Link>
        </nav>
      </div>
      <Routes>
        <Route path="/" element={<SnapshotPage/>} />
        <Route path="/inbound" element={<InboundPage/>} />
        <Route path="/putaway" element={<PutawayPage/>} />
        <Route path="/outbound" element={<OutboundPage/>} />
        <Route path="/tasks" element={<TasksPage/>} />
        <Route path="/batches" element={<BatchesPage/>} />
        <Route path="/moves" element={<MovesPage/>} />
        <Route path="/tools/stock" element={<StockToolPage/>} />
        <Route path="/tools/ledger" element={<LedgerToolPage/>} />
      </Routes>
    </BrowserRouter>
  )
}
TSX
)"
fi

say "Phase 2 shells patched. Restart dev server if running."
