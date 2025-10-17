import { useEffect, useState } from "react"
export function Toaster({ msg }: { msg?: string }) {
  const [show, setShow] = useState(false)
  useEffect(() => { if (!msg) return; setShow(true); const t=setTimeout(()=>setShow(false),2400); return ()=>clearTimeout(t) }, [msg])
  if (!show) return null
  return <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl bg-black/80 text-white px-4 py-2 text-sm shadow-lg">{msg}</div>
}
