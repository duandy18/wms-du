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
