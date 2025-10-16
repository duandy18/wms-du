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