import React from 'react'
import type { InventoryDistribution } from '../../types/inventory'

export function InventoryDrawer({ open, onClose, data }: { open: boolean; onClose: () => void; data?: InventoryDistribution }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="w-[440px] max-w-[90vw] h-full bg-white shadow-xl p-5 overflow-y-auto">
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">{data?.name ?? '库存分布'}</div>
          <button className="rounded-xl px-3 py-1 bg-neutral-100 hover:bg-neutral-200" onClick={onClose}>关闭</button>
        </div>
        <div className="mt-4 space-y-6">
          <section>
            <div className="text-sm font-medium mb-2">库位分布</div>
            <div className="space-y-1 text-sm">
              {data?.locations?.length ? data!.locations.map((l, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-24 text-neutral-600">{l.location}</div>
                  <div className="flex-1 h-2 bg-neutral-100 rounded-full overflow-hidden">
                    <div className="h-full bg-neutral-400" style={{ width: 'calc(min(100%, ' + l.qty + ' * 1%))' }} />
                  </div>
                  <div className="w-10 text-right tabular-nums">{l.qty}</div>
                </div>
              )) : <div className="text-neutral-400">无数据</div>}
            </div>
          </section>
          <section>
            <div className="text-sm font-medium mb-2">批次（FEFO）</div>
            <div className="space-y-1 text-sm">
              {data?.batches?.length ? data!.batches.map((b, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{b.batch}</div>
                    <div className="text-xs text-neutral-500">生产 {b.production_date || '—'} · 到期 {b.expiry_date || '—'}</div>
                  </div>
                  <div className="tabular-nums">{b.qty}</div>
                </div>
              )) : <div className="text-neutral-400">无数据</div>}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}