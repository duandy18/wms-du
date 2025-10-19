import React from 'react'
import { useEffect, useMemo, useState } from 'react'
import { apiGet } from '../lib/api'
import type { InventoryTile, InventoryDistribution } from '../types/inventory'
import { TileCard } from '../components/snapshot/TileCard'
import { InventoryDrawer } from '../components/snapshot/InventoryDrawer'
import ApiBadge from '../components/common/ApiBadge'

function useQuery<T>(key: string, loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setLoading(true)
    loader().then(d => alive && setData(d)).catch(e => alive && setError(String(e))).finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [key])
  return { data, error, loading }
}

export default function SnapshotPage() {
  const [view, setView] = useState<'tile' | 'table'>('tile')
  const q = useQuery('snapshot', () => apiGet<InventoryTile[]>('/snapshot/inventory'))
  const [openId, setOpenId] = useState<number | null>(null)
  const [dist, setDist] = useState<InventoryDistribution | undefined>()

  useEffect(() => {
    if (openId != null) {
      apiGet<InventoryDistribution>(`/snapshot/location-heat?item_id=${openId}`).then(setDist).catch(() => setDist(undefined))
    }
  }, [openId])

  const table = useMemo(() => q.data || [], [q.data])

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-xl font-semibold">库存快照</div>
        <ApiBadge />
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => setView('tile')} className={"rounded-xl px-3 py-1 " + (view==='tile' ? 'bg-black text-white' : 'bg-neutral-100')}>图块</button>
        <button onClick={() => setView('table')} className={"rounded-xl px-3 py-1 " + (view==='table' ? 'bg-black text-white' : 'bg-neutral-100')}>表格</button>
      </div>

      {q.loading && <div className="text-neutral-500">加载中…</div>}
      {q.error && <div className="text-red-600">加载失败：{q.error}</div>}
      {!q.loading && !q.error && !q.data?.length && <div className="text-neutral-400">空空如也，去收一批货吧。</div>}

      {view === 'tile' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {table.map(t => (
            <TileCard key={t.item_id} t={t} onOpen={() => setOpenId(t.item_id)} />
          ))}
        </div>
      )}

      {view === 'table' && (
        <div className="overflow-x-auto">
          <table className="min-w-[720px] w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-600">
                <th className="py-2 pr-3">ID</th>
                <th className="py-2 pr-3">名称</th>
                <th className="py-2 pr-3">规格</th>
                <th className="py-2 pr-3">总量</th>
                <th className="py-2 pr-3">Top2 库位</th>
                <th className="py-2 pr-3">主批次</th>
                <th className="py-2 pr-3">最早到期</th>
                <th className="py-2 pr-3">状态</th>
              </tr>
            </thead>
            <tbody>
              {table.map(t => (
                <tr key={t.item_id} className="border-t hover:bg-neutral-50 cursor-pointer" onClick={() => setOpenId(t.item_id)}>
                  <td className="py-2 pr-3 tabular-nums">{t.item_id}</td>
                  <td className="py-2 pr-3">{t.name}</td>
                  <td className="py-2 pr-3">{t.spec}</td>
                  <td className="py-2 pr-3 tabular-nums">{t.qty_total}</td>
                  <td className="py-2 pr-3">{t.top_locations.map(l => `${l.location}(${l.qty})`).join('、')}</td>
                  <td className="py-2 pr-3">{t.main_batch || '—'}</td>
                  <td className="py-2 pr-3">{t.earliest_expiry || '—'}</td>
                  <td className="py-2 pr-3">{t.flags?.expired ? '已过期' : t.flags?.near_expiry ? '临期' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <InventoryDrawer open={openId != null} onClose={() => setOpenId(null)} data={dist} />
    </div>
  )
}
