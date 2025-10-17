import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Toaster } from "@/components/ui/toaster"

const Schema = z.object({
  item_id: z.coerce.number().int().positive(),
  location_code: z.string().min(1, "必填"),
  qty: z.coerce.number().int().positive(),
  batch_code: z.string().optional().or(z.literal("")),
})
type FormValues = z.infer<typeof Schema>

export default function PutawayPage() {
  const { register, handleSubmit, formState: { errors, isSubmitting }, reset } = useForm<FormValues>({ resolver: zodResolver(Schema), defaultValues: { qty: 1 } })
  const [toast, setToast] = useState<string | undefined>()
  const onSubmit = async (v: FormValues) => {
    try {
      await api.putaway({ item_id: v.item_id, location_code: v.location_code, qty: v.qty, batch_code: v.batch_code || undefined })
      setToast("上架成功 ✅")
      reset({ qty: 1, item_id: v.item_id, location_code: v.location_code, batch_code: v.batch_code })
    } catch (e:any) { setToast(`上架失败：${e.message}`) }
  }
  return (
    <div className="container mx-auto max-w-2xl py-8">
      <Card>
        <CardHeader>
          <h1 className="text-xl font-semibold">Putaway（上架）</h1>
          <p className="text-sm text-gray-500">调用 <code>/putaway</code> 进行首次联调</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="grid gap-2">
              <Label htmlFor="item_id">Item ID</Label>
              <Input id="item_id" type="number" placeholder="例如 1" {...register("item_id")} />
              {errors.item_id && <p className="text-red-600 text-xs">{errors.item_id.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="location_code">Location Code</Label>
              <Input id="location_code" placeholder="例如 L12 / STAGE-A" {...register("location_code")} />
              {errors.location_code && <p className="text-red-600 text-xs">{errors.location_code.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="qty">Qty</Label>
              <Input id="qty" type="number" placeholder="例如 10" {...register("qty")} />
              {errors.qty && <p className="text-red-600 text-xs">{errors.qty.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="batch_code">Batch Code（可选）</Label>
              <Input id="batch_code" placeholder="例如 B20251015" {...register("batch_code")} />
            </div>
            <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "提交中…" : "提交上架"}</Button>
          </form>
        </CardContent>
      </Card>
      <Toaster msg={toast} />
    </div>
  )
}
