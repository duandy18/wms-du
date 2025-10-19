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
