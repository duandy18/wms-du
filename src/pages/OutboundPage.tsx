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