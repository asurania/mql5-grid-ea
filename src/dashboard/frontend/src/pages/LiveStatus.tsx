import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { apiGet, type StatusSummary } from '@/lib/api'

export default function LiveStatus() {
  const [status, setStatus] = useState<StatusSummary | null>(null)
  const [error, setError] = useState('')

  const refresh = async () => {
    try {
      const data = await apiGet<StatusSummary>('/status/summary')
      setStatus(data)
      setError('')
    } catch (e: any) {
      setError(e.message)
    }
  }

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 10000)
    return () => clearInterval(interval)
  }, [])

  if (error) return <div className="text-red-400">Error: {error}</div>
  if (!status) return <div className="text-zinc-400">Loading...</div>

  const sessionName = status.session?.name || '—'
  const riskMode = status.session?.risk_mode || '—'
  const equity = status.session?.account_equity || 0

  return (
    <div className="space-y-4">
      {/* System overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-zinc-400">Session</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold capitalize">{sessionName}</div></CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-zinc-400">Risk Mode</CardTitle></CardHeader>
          <CardContent>
            <Badge variant={riskMode === 'high' ? 'destructive' : riskMode === 'medium' ? 'secondary' : 'outline'}>
              {riskMode}
            </Badge>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-zinc-400">Account Equity</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">${equity.toLocaleString()}</div></CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-zinc-400">Bridge</CardTitle></CardHeader>
          <CardContent>
            <Badge variant={status.bridge?.status === 'running' ? 'secondary' : 'outline'}>
              {status.bridge?.status || 'offline'}
            </Badge>
            {status.bridge?.last_run_utc && (
              <div className="text-xs text-zinc-500 mt-1">Last: {new Date(status.bridge.last_run_utc).toLocaleTimeString()}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Pair status */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader><CardTitle>Pair Status</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-3">
            {status.pairs.map((p) => (
              <div key={p.pair} className="flex items-center justify-between border-b border-zinc-800 pb-3 last:border-0 last:pb-0">
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-lg">{p.pair}</span>
                  <Badge variant={p.allow_new_basket ? 'secondary' : 'outline'} className="text-xs">
                    {p.allow_new_basket ? 'TRADING' : 'BLOCKED'}
                  </Badge>
                  {p.entry_direction && p.entry_direction !== 'none' && (
                    <Badge variant={p.entry_direction === 'buy' ? 'secondary' : 'destructive'} className="text-xs">
                      {p.entry_direction.toUpperCase()}
                    </Badge>
                  )}
                </div>
                <div className="text-right text-sm text-zinc-400">
                  <div>Grid: {p.grid_mode} · Lot: {p.initial_lot} · Step: {p.step_pips}p · Mult: {p.multiplier}x · Depth: {p.max_trades_per_side}</div>
                  <div>TP: {p.basket_tp_pips}p · SL: {p.basket_sl_pips}p · {p.policy_id}</div>
                  {p.entry_reason && <div className="text-xs text-zinc-500">{p.entry_reason}</div>}
                </div>
              </div>
            ))}
            {status.pairs.length === 0 && (
              <div className="text-zinc-500 text-sm">No pairs — bridge not running yet</div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Timestamp */}
      <div className="text-xs text-zinc-600 text-right">
        Updated: {new Date(status.timestamp_utc).toLocaleTimeString()} · Auto-refresh 10s
      </div>
    </div>
  )
}