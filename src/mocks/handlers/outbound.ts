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