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