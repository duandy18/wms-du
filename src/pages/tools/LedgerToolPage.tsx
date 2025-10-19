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
