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
