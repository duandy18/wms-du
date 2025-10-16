import { PropsWithChildren } from "react"
export function Card({ children }: PropsWithChildren) { return <div className="rounded-2xl border bg-white shadow-sm">{children}</div> }
export function CardHeader({ children }: PropsWithChildren) { return <div className="p-6 pb-2">{children}</div> }
export function CardContent({ children }: PropsWithChildren) { return <div className="p-6 pt-0">{children}</div> }
