import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { apiGet, apiPatch, apiPut, type SessionsConfig } from '@/lib/api'
import { nyToCalgary, utcToCalgary } from '@/lib/api'

export default function SessionSchedule() {
  const [sessions, setSessions] = useState<SessionsConfig | null>(null)
  const [dailyLiq, setDailyLiq] = useState<[number, number]>([20, 50])
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const s = await apiGet<SessionsConfig>('/config/sessions')
    setSessions(s)
    const cfg = await apiGet<{ daily_liquidation_utc: [number, number] }>('/config/daily-liquidation')
    setDailyLiq(cfg.daily_liquidation_utc)
  }

  useEffect(() => { load() }, [])

  const saveSession = async (name: string, patch: Partial<any>) => {
    setSaving(true)
    await apiPatch(`/config/sessions/${name}`, patch)
    await load()
    setSaving(false)
  }

  const saveDailyLiq = async (h: number, m: number) => {
    setSaving(true)
    await apiPut('/config/daily-liquidation', { daily_liquidation_utc: [h, m] })
    setDailyLiq([h, m])
    setSaving(false)
  }

  if (!sessions) return <div className="text-zinc-400">Loading...</div>

  const sessionOrder = ['asia', 'london', 'new_york'] as const

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">Session Schedule</h2>
        {saving && <Badge variant="outline" className="text-xs">Saving...</Badge>}
      </div>

      <p className="text-sm text-zinc-400">
        All times shown in Calgary (MDT). Changes take effect on next bridge refresh.
      </p>

      {/* Daily Liquidation */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            🔴 Daily Forced Liquidation
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div>
              <Label className="text-xs text-zinc-400">Hour (UTC)</Label>
              <Input
                type="number" min={0} max={23} value={dailyLiq[0]}
                onChange={(e) => saveDailyLiq(parseInt(e.target.value) || 0, dailyLiq[1])}
                className="w-20 bg-zinc-800 border-zinc-700"
              />
            </div>
            <div>
              <Label className="text-xs text-zinc-400">Minute (UTC)</Label>
              <Input
                type="number" min={0} max={59} value={dailyLiq[1]}
                onChange={(e) => saveDailyLiq(dailyLiq[0], parseInt(e.target.value) || 0)}
                className="w-20 bg-zinc-800 border-zinc-700"
              />
            </div>
            <div className="text-sm text-zinc-300">
              = {utcToCalgary(dailyLiq[0], dailyLiq[1])} Calgary
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Per-session cards */}
      {sessionOrder.map((name) => {
        const s = sessions[name]
        if (!s) return null
        return (
          <Card key={name} className="bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Switch
                  checked={s.enabled}
                  onCheckedChange={(v) => saveSession(name, { enabled: v })}
                />
                <span className="capitalize">{name} Session</span>
                {s.enabled ? <Badge variant="secondary">Active</Badge> : <Badge variant="outline">Disabled</Badge>}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* Start time (NY) */}
                <div>
                  <Label className="text-xs text-zinc-400">Start Hour (NY)</Label>
                  <Input
                    type="number" min={0} max={23} value={s.start_ny_time[0]}
                    onChange={(e) => saveSession(name, { start_ny_time: [parseInt(e.target.value) || 0, s.start_ny_time[1]] })}
                    className="w-20 bg-zinc-800 border-zinc-700"
                  />
                  <div className="text-xs text-zinc-500 mt-1">{nyToCalgary(s.start_ny_time[0], s.start_ny_time[1])} Calgary</div>
                </div>

                {/* Close UTC */}
                <div>
                  <Label className="text-xs text-zinc-400">Managed Close Hour (UTC)</Label>
                  <Input
                    type="number" min={0} max={23} value={s.close_utc[0]}
                    onChange={(e) => saveSession(name, { close_utc: [parseInt(e.target.value) || 0, s.close_utc[1]] })}
                    className="w-20 bg-zinc-800 border-zinc-700"
                  />
                  <div className="text-xs text-zinc-500 mt-1">{utcToCalgary(s.close_utc[0], s.close_utc[1])} Calgary</div>
                </div>

                {/* TP pips */}
                <div>
                  <Label className="text-xs text-zinc-400">TP (pips)</Label>
                  <Input
                    type="number" step={0.5} min={0} value={s.tp_pips}
                    onChange={(e) => saveSession(name, { tp_pips: parseFloat(e.target.value) || 0 })}
                    className="w-20 bg-zinc-800 border-zinc-700"
                  />
                </div>

                {/* SL pips */}
                <div>
                  <Label className="text-xs text-zinc-400">SL (pips)</Label>
                  <Input
                    type="number" step={1} min={0} value={s.sl_pips}
                    onChange={(e) => saveSession(name, { sl_pips: parseInt(e.target.value) || 0 })}
                    className="w-20 bg-zinc-800 border-zinc-700"
                  />
                </div>
              </div>

              <Separator className="bg-zinc-800" />

              <div className="text-xs text-zinc-500">
                Managed close minutes before: {s.managed_close_minutes_before}
                {s.liquidate_minutes_before !== undefined && ` · Liquidate minutes before: ${s.liquidate_minutes_before}`}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}