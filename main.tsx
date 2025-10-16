import './index.css'

if (import.meta.env.DEV && import.meta.env.VITE_USE_MSW === '1') {
  import('./mocks/browser')
    .then(({ worker }) => {
      (window as any).__MSW_ENABLED__ = true
      return worker.start()
    })
    .catch(() => { (window as any).__MSW_ENABLED__ = false })
}
