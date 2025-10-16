import { http, HttpResponse } from 'msw'

export const handlers = [
  http.post('http://127.0.0.1:8000/inbound/receive', async ({ request }) => {
    const b = await request.json()
    return HttpResponse.json({ item_id: b.item_id, batch_id: 1, accepted_qty: b.accepted_qty })
  }),
  http.post('http://127.0.0.1:8000/putaway', async ({ request }) => {
    const b = await request.json()
    if (b.location_code === 'BAD') return HttpResponse.json({ detail: '库位不存在' }, { status: 422 })
    return HttpResponse.json({ move_id: 1001, item_id: b.item_id, location_code: b.location_code, delta: b.qty, batch_code: b.batch_code ?? null })
  }),
  http.get('http://127.0.0.1:8000/stock/query', () =>
    HttpResponse.json({ rows: [{ item_id: 1, location_code: 'L12', qty: 10 }] })
  ),
  http.get('http://127.0.0.1:8000/ledger/recent', () =>
    HttpResponse.json({ rows: [{ id: 1, ts: new Date().toISOString(), item_id: 1, location_code: 'L12', delta: 10, reason: 'INBOUND', ref: 'PO-1', batch_code: 'B20251015' }] })
  ),
]
