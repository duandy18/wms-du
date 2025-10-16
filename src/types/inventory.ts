export type InventoryTile = {
  item_id: number
  name: string
  spec: string
  qty_total: number
  top_locations: { location: string; qty: number }[]
  main_batch?: string
  earliest_expiry?: string
  flags?: { near_expiry?: boolean; expired?: boolean }
}

export type LocationBreakdown = {
  location: string
  qty: number
}

export type BatchBreakdown = {
  batch: string
  production_date?: string
  expiry_date?: string
  qty: number
}

export type InventoryDistribution = {
  item_id: number
  name: string
  locations: LocationBreakdown[]
  batches: BatchBreakdown[]
}