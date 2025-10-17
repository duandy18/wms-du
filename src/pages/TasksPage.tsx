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