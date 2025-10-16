import { http, HttpResponse } from 'msw'

const batches = [
  { id:1, item_id:1, item_name:'双拼猫粮', batch_code:'B202509', production_date:'2025-09-01', expiry_date:'2026-01-10', qty:70, near:false, expired:false },
  { id:2, item_id:1, item_name:'双拼猫粮', batch_code:'B202510', production_date:'2025-10-01', expiry_date:'2026-02-01', qty:35, near:true, expired:false },
  { id:3, item_id:2, item_name:'冻干三文鱼', batch_code:'S202510', production_date:'2025-10-05', expiry_date:'2026-04-01', qty:20, near:false, expired:false }
]

export const batchHandlers = [
  http.get('/batches/list', ({ request }) => {
    const u = new URL(request.url)
    const item = Number(u.searchParams.get('item_id') || '0')
    const list = item ? batches.filter(b => b.item_id === item) : batches
    return HttpResponse.json(list)
  })
]