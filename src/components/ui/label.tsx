import * as React from "react"
export function Label(props: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className="text-sm font-medium leading-6" {...props} />
}
