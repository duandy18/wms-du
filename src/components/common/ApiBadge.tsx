import React, { useEffect, useState } from 'react'

export default function ApiBadge() {
  const api = import.meta.env.VITE_API_URL || '—'
  const [msw, setMsw] = useState<'on'|'off'|'starting'>(() => {
    const s = (window as any).__MSW_ENABLED__
    return s === true ? 'on' : s === 'starting' ? 'starting' : 'off'
  })

  useEffect(() => {
    const update = () => {
      const s = (window as any).__MSW_ENABLED__
      if (s === true || navigator.serviceWorker?.controller) setMsw('on')
      else if (s === 'starting') setMsw('starting')
      else setMsw('off')
    }
    update()
    const t = setInterval(update, 500)       // 轮询首屏异步完成
    window.addEventListener('MSW_READY', update)
    return () => { clearInterval(t); window.removeEventListener('MSW_READY', update) }
  }, [])

  const chip =
    msw === 'on' ? 'bg-emerald-200' :
    msw === 'starting' ? 'bg-amber-200' : 'bg-neutral-200'

  return (
    <div className="inline-flex items-center gap-2 rounded-2xl px-3 py-1 text-sm shadow bg-neutral-100">
      <span className="font-medium">API:</span>
      <code>{api}</code>
      <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${chip}`}>
        {msw === 'on' ? 'MSW: on' : msw === 'starting' ? 'MSW: starting' : 'MSW: off'}
      </span>
    </div>
  )
}
