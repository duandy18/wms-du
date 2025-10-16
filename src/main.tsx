import React from 'react'
import ReactDOM from 'react-dom/client'
import AppRouter from './router'
import './index.css'

if (import.meta.env.DEV && import.meta.env.VITE_USE_MSW === '1') {
  (window as any).__MSW_ENABLED__ = 'starting'       // 提前标记
  import('./mocks/browser')
    .then(async ({ worker }) => {
      console.log('[MSW] starting…')
      await worker.start({
        serviceWorker: { url: '/mockServiceWorker.js' },
        onUnhandledRequest: 'bypass',
      })
      ;(window as any).__MSW_ENABLED__ = true
      window.dispatchEvent(new Event('MSW_READY'))    // 启动完成事件
      console.log('[MSW] started')
    })
    .catch((e) => {
      console.warn('[MSW] failed', e)
      ;(window as any).__MSW_ENABLED__ = false
    })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppRouter />
  </React.StrictMode>
)
