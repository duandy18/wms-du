import { Routes, Route, Link } from "react-router-dom"
import PutawayPage from "@/pages/Putaway"
export default function App() {
  return (
    <>
      <div className="border-b">
        <div className="container h-14 flex items-center gap-4">
          <Link to="/" className="text-lg font-semibold">WMS-FE</Link>
          <nav className="flex items-center gap-3 text-sm text-gray-500">
            <Link to="/putaway" className="hover:underline">Putaway</Link>
          </nav>
          <div className="ml-auto text-xs text-gray-500">API: {import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"}</div>
        </div>
      </div>
      <Routes>
        <Route path="/" element={<div className="container py-8 text-sm text-gray-500">请选择上方菜单进入功能页面。</div>} />
        <Route path="/putaway" element={<PutawayPage />} />
      </Routes>
    </>
  )
}
