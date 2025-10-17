import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'

// Phase 1
import SnapshotPage from './pages/SnapshotPage'
import InboundPage from './pages/InboundPage'
import PutawayPage from './pages/PutawayPage'
import OutboundPage from './pages/OutboundPage'
import StockToolPage from './pages/tools/StockToolPage'
import LedgerToolPage from './pages/tools/LedgerToolPage'

// Phase 2 (shells)
import TasksPage from './pages/TasksPage'
import BatchesPage from './pages/BatchesPage'
import MovesPage from './pages/MovesPage'

export default function AppRouter() {
  return (
    <BrowserRouter>
      {/* 顶部导航 */}
      <div className="p-3 border-b flex items-center gap-3 bg-white sticky top-0 z-40">
        <Link to="/" className="font-semibold">WMS</Link>
        <nav className="flex gap-2 text-sm">
          <Link to="/inbound" className="rounded px-2 py-1 hover:bg-neutral-100">Inbound</Link>
          <Link to="/putaway" className="rounded px-2 py-1 hover:bg-neutral-100">Putaway</Link>
          <Link to="/outbound" className="rounded px-2 py-1 hover:bg-neutral-100">Outbound</Link>
          <Link to="/tasks" className="rounded px-2 py-1 hover:bg-neutral-100">Tasks</Link>
          <Link to="/batches" className="rounded px-2 py-1 hover:bg-neutral-100">Batches</Link>
          <Link to="/moves" className="rounded px-2 py-1 hover:bg-neutral-100">Moves</Link>
          <Link to="/tools/stock" className="rounded px-2 py-1 hover:bg-neutral-100">Stock</Link>
          <Link to="/tools/ledger" className="rounded px-2 py-1 hover:bg-neutral-100">Ledger</Link>
        </nav>
      </div>

      {/* 路由声明区 */}
      <Routes>
        {/* Phase 1 */}
        <Route path="/" element={<SnapshotPage />} />
        <Route path="/inbound" element={<InboundPage />} />
        <Route path="/putaway" element={<PutawayPage />} />
        <Route path="/outbound" element={<OutboundPage />} />
        <Route path="/tools/stock" element={<StockToolPage />} />
        <Route path="/tools/ledger" element={<LedgerToolPage />} />

        {/* Phase 2 shells（用 Fragment 包裹，避免“Adjacent JSX elements”错误） */}
        <>
          <Route path="/tasks" element={<TasksPage />} />
          <Route path="/batches" element={<BatchesPage />} />
          <Route path="/moves" element={<MovesPage />} />
        </>

        {/* 兜底：未知路径回首页 */}
        <Route path="*" element={<SnapshotPage />} />
      </Routes>
    </BrowserRouter>
  )
}
