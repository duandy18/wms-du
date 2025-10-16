import React from 'react'
import type { InventoryTile } from '../../types/inventory'

export function TileCard({ t, onOpen }: { t: InventoryTile; onOpen: () => void }) {
  return (
    <div className="rounded-2xl shadow p-4 hover:shadow-lg transition cursor-pointer bg-white" onClick={onOpen}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-base font-semibold">{t.name}</div>
          <div className="text-xs text-neutral-500">#{t.item_id} · {t.spec}</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold tabular-nums">{t.qty_total}</div>
          {t.flags?.expired ? (
            <span className="mt-1 inline-block rounded px-2 py-0.5 text-xs bg-red-100 text-red-700">已过期</span>
          ) : t.flags?.near_expiry ? (
            <span className="mt-1 inline-block rounded px-2 py-0.5 text-xs bg-amber-100 text-amber-700">临期</span>
          ) : null}
        </div>
      </div>
      <div className="mt-3 text-xs text-neutral-600">
        <div>Top 库位：{t.top_locations.map(l => `${l.location}(${l.qty})`).join('、') || '—'}</div>
        <div>主批次：{t.main_batch || '—'}，最早到期：{t.earliest_expiry || '—'}</div>
      </div>
    </div>
  )
}