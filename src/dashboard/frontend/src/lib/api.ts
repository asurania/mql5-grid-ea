const API = '/api'

export async function apiGet<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`GET ${path}: ${res.status}`)
  return res.json()
}

export async function apiPatch<T = any>(path: string, data: any): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`PATCH ${path}: ${res.status}`)
  return res.json()
}

export async function apiPut<T = any>(path: string, data: any): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`PUT ${path}: ${res.status}`)
  return res.json()
}

export async function apiPost<T = any>(path: string, data?: any): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: 'POST',
    headers: data ? { 'Content-Type': 'application/json' } : {},
    body: data ? JSON.stringify(data) : undefined,
  })
  if (!res.ok) throw new Error(`POST ${path}: ${res.status}`)
  return res.json()
}

export interface SessionConfig {
  enabled: boolean
  start_ny_time: [number, number]
  managed_close_ny_time?: [number, number]
  close_utc: [number, number]
  managed_close_minutes_before: number
  liquidate_minutes_before?: number
  tp_pips: number
  sl_pips: number
}

export interface SessionsConfig {
  asia: SessionConfig
  london: SessionConfig
  new_york: SessionConfig
}

export interface AccountConfig {
  equity: number
  risk_mode: string
  currency: string
}

export interface PairStatus {
  pair: string
  grid_mode?: string
  initial_lot?: number
  step_pips?: number
  multiplier?: number
  max_trades_per_side?: number
  basket_tp_pips?: number
  basket_sl_pips?: number
  policy_id?: string
  allow_new_basket?: boolean
  entry_direction?: string
  entry_should_enter?: boolean
  entry_reason?: string
  risk_action?: string
  risk_band?: string
}

export interface StatusSummary {
  timestamp_utc: string
  bridge: { last_run_utc: string; run_count: number; status: string; errors: string[] } | null
  session: { name: string; close_utc: string; managed_close_utc: string; daily_liquidate_utc: string; risk_mode: string; account_equity: number } | null
  pairs: PairStatus[]
  event_risk: any
}

export function nyToCalgary(h: number, m: number): string {
  // NY time is UTC-4 (EDT) or UTC-5 (EST). Calgary is UTC-6 (MDT) or UTC-7 (MST).
  // During daylight saving: NY = UTC-4, Calgary = UTC-6, diff = 2h behind
  const calgaryH = (h - 2 + 24) % 24
  const ampm = calgaryH >= 12 ? 'PM' : 'AM'
  const h12 = calgaryH === 0 ? 12 : calgaryH > 12 ? calgaryH - 12 : calgaryH
  return `${h12}:${m.toString().padStart(2, '0')} ${ampm}`
}

export function utcToCalgary(h: number, m: number): string {
  // Calgary MDT = UTC-6
  const calgaryH = (h - 6 + 24) % 24
  const ampm = calgaryH >= 12 ? 'PM' : 'AM'
  const h12 = calgaryH === 0 ? 12 : calgaryH > 12 ? calgaryH - 12 : calgaryH
  return `${h12}:${m.toString().padStart(2, '0')} ${ampm}`
}