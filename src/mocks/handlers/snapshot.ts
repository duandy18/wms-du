import { http, HttpResponse } from 'msw'
const tiles = [
  { item_id:1, name:'双拼猫粮', spec:'1.5kg', qty_total:100, top_locations:[{location:'A1', qty:60},{location:'B3', qty:40}], main_batch:'B202509', earliest_expiry:'2026-01-10', flags:{} },
  { item_id:2, name:'冻干三文鱼', spec:'500g', qty_total:42, top_locations:[{location:'C2', qty:20},{location:'A2', qty:22}], main_batch:'S202510', earliest_expiry:'2026-02-01', flags:{} },
  { item_id: 3,  name: '全价成猫粮',   spec: '8kg',     qty_total: 75,  top_locations:[{location:'D1',qty:50},{location:'A1',qty:25}], main_batch:'C202510', earliest_expiry:'2026-03-15', flags:{ near_expiry:false } },
    { item_id: 4,  name: '幼猫奶糕',     spec: '2kg',     qty_total: 28,  top_locations:[{location:'B2',qty:18},{location:'STAGE',qty:10}], main_batch:'M202509', earliest_expiry:'2026-01-05', flags:{ near_expiry:true } },
    { item_id: 5,  name: '化毛配方',     spec: '1.8kg',   qty_total: 63,  top_locations:[{location:'A3',qty:40},{location:'C1',qty:23}], main_batch:'H202508', earliest_expiry:'2025-12-20', flags:{ near_expiry:true } },
    { item_id: 6,  name: '室内控便',     spec: '3kg',     qty_total: 33,  top_locations:[{location:'E2',qty:20},{location:'A2',qty:13}], main_batch:'I202510', earliest_expiry:'2026-04-01', flags:{} },
    { item_id: 7,  name: '无谷精选',     spec: '5kg',     qty_total: 17,  top_locations:[{location:'B4',qty:12},{location:'C3',qty:5}],  main_batch:'G202506', earliest_expiry:'2025-11-28', flags:{ near_expiry:true } },
    { item_id: 8,  name: '鸡胸冻干粒',   spec: '300g',    qty_total: 90,  top_locations:[{location:'F1',qty:60},{location:'F2',qty:30}], main_batch:'FD202510',earliest_expiry:'2026-05-12', flags:{} },
    { item_id: 9,  name: '金枪鱼罐头',   spec: '170g×12', qty_total: 54,  top_locations:[{location:'G1',qty:36},{location:'STAGE',qty:18}],main_batch:'CAN202509',earliest_expiry:'2026-02-20', flags:{} },
    { item_id: 10, name: '鸡肝罐头',     spec: '170g×12', qty_total: 22,  top_locations:[{location:'G2',qty:16},{location:'B1',qty:6}],  main_batch:'CAN202508',earliest_expiry:'2026-01-02', flags:{ near_expiry:true } },
    { item_id: 11, name: '化毛膏',       spec: '120g',    qty_total: 48,  top_locations:[{location:'H1',qty:20},{location:'A4',qty:28}], main_batch:'P202510', earliest_expiry:'2026-06-30', flags:{} },
    { item_id: 12, name: '营养膏',       spec: '100g',    qty_total: 35,  top_locations:[{location:'H2',qty:20},{location:'H3',qty:15}], main_batch:'N202510', earliest_expiry:'2026-06-05', flags:{} }
  
]
export const snapshotHandlers = [
  http.get('*/snapshot/inventory', () => HttpResponse.json(tiles)),
  http.get('*/snapshot/location-heat', ({ request }) => {
    const u = new URL(request.url); const id = Number(u.searchParams.get('item_id')||'0')
    const t = tiles.find(x=>x.item_id===id)
    return HttpResponse.json(t ? {
      item_id: t.item_id, name: t.name,
      locations: [{location:'A1',qty:60},{location:'B3',qty:40},{location:'STAGE',qty:5}],
      batches: [{batch:'B202509',production_date:'2025-09-01',expiry_date:'2026-01-10',qty:70},
                {batch:'B202510',production_date:'2025-10-01',expiry_date:'2026-02-01',qty:35}]
    } : { item_id:id, name:'未知', locations:[], batches:[] })
  }),
]
