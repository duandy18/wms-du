export const API_BASE = import.meta.env.VITE_API_URL || ''
export const isMSW = (window as any).__MSW_ENABLED__ === true

function _base(): string {
  const api = (import.meta?.env?.VITE_API_URL || '').replace(/\/$/, '')
  return ((window as any).__MSW_ENABLED__ === true || !api) ? '' : api
}
function joinPath(p: string): string { const s = String(p||''); return s.startsWith('/') ? s : '/' + s }

export async function apiGet<T>(path: string): Promise<T> {
  const url = _base() + joinPath(path)
  const res = await fetch(url)
  if (!res.ok) throw new Error(`[GET ${url}] ${res.status}`)
  return res.json() as Promise<T>
}

export async function apiPost<T>(path: string, body: any): Promise<T> {
  const url = _base() + joinPath(path)
  const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`[POST ${url}] ${res.status}`)
  return res.json() as Promise<T>
}
