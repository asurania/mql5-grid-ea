import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { apiGet, apiPatch, type AccountConfig } from '@/lib/api'

interface RiskConfig {
  budget_pct: Record<string, number>
  target_profit_pct: Record<string, number>
  max_basket_dd_pct: Record<string, number>
  min_step_to_spread_ratio: Record<string, number>
  min_free_margin_percent: Record<string, number>
}

export default function RiskControls() {
  const [account, setAccount] = useState<AccountConfig | null>(null)
  const [risk, setRisk] = useState<RiskConfig | null>(null)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const a = await apiGet<AccountConfig>('/config/account')
    setAccount(a)
    const r = await apiGet<RiskConfig>('/config/risk')
    setRisk(r)
  }

  useEffect(() => { load() }, [])

  const saveAccount = async (patch: Partial<AccountConfig>) => {
    setSaving(true)
    await apiPatch('/config/account', patch)
    await load()
    setSaving(false)
  }

  const saveRisk = async (patch: Partial<RiskConfig>) => {
    setSaving(true)
    await apiPatch('/config/risk', patch)
    await load()
    setSaving(false)
  }

  if (!account || !risk) return <div className="text-zinc-400">Loading...</div>

  const modes = ['low', 'medium', 'high']

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">Risk Controls</h2>
        {saving && <Badge variant="outline" className="text-xs">Saving...</Badge>}
      </div>

      {/* Account */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2"><CardTitle className="text-sm">Account</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-zinc-400">Equity ($)</Label>
              <Input
                type="number" step={100} min={0} value={account.equity}
                onChange={(e) => saveAccount({ equity: parseFloat(e.target.value) || 0 })}
                className="bg-zinc-800 border-zinc-700"
              />
            </div>
            <div>
              <Label className="text-xs text-zinc-400">Risk Mode</Label>
              <div className="flex gap-2 mt-1">
                {modes.map((m) => (
                  <button
                    key={m}
                    onClick={() => saveAccount({ risk_mode: m })}
                    className={`px-3 py-1.5 rounded text-sm capitalize ${
                      account.risk_mode === m
                        ? 'bg-zinc-700 text-white'
                        : 'bg-zinc-900 text-zinc-400 hover:bg-zinc-800'
                    }`}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Risk mode table */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2"><CardTitle className="text-sm">Risk Mode Parameters</CardTitle></CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-zinc-400 border-b border-zinc-800">
                  <th className="text-left py-2 pr-4">Parameter</th>
                  {modes.map(m => (
                    <th key={m} className="text-center py-2 px-2 capitalize">{m}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="text-zinc-300">
                <tr className="border-b border-zinc-800">
                  <td className="py-2 pr-4 text-zinc-400">DD Budget %</td>
                  {modes.map(m => (
                    <td key={m} className="text-center py-2">
                      <Input
                        type="number" step={0.005} min={0} max={0.1}
                        value={risk.budget_pct[m]}
                        onChange={(e) => saveRisk({ budget_pct: { [m]: parseFloat(e.target.value) || 0 } })}
                        className="w-20 text-center bg-zinc-800 border-zinc-700 mx-auto"
                      />
                    </td>
                  ))}
                </tr>
                <tr className="border-b border-zinc-800">
                  <td className="py-2 pr-4 text-zinc-400">Max Basket DD %</td>
                  {modes.map(m => (
                    <td key={m} className="text-center py-2">
                      <Input
                        type="number" step={0.005} min={0} max={0.1}
                        value={risk.max_basket_dd_pct[m]}
                        onChange={(e) => saveRisk({ max_basket_dd_pct: { [m]: parseFloat(e.target.value) || 0 } })}
                        className="w-20 text-center bg-zinc-800 border-zinc-700 mx-auto"
                      />
                    </td>
                  ))}
                </tr>
                <tr className="border-b border-zinc-800">
                  <td className="py-2 pr-4 text-zinc-400">Min Step/Spread</td>
                  {modes.map(m => (
                    <td key={m} className="text-center py-2">
                      <Input
                        type="number" step={0.5} min={0}
                        value={risk.min_step_to_spread_ratio[m]}
                        onChange={(e) => saveRisk({ min_step_to_spread_ratio: { [m]: parseFloat(e.target.value) || 0 } })}
                        className="w-20 text-center bg-zinc-800 border-zinc-700 mx-auto"
                      />
                    </td>
                  ))}
                </tr>
                <tr className="border-b border-zinc-800">
                  <td className="py-2 pr-4 text-zinc-400">Min Free Margin %</td>
                  {modes.map(m => (
                    <td key={m} className="text-center py-2">
                      <Input
                        type="number" step={5} min={0} max={100}
                        value={risk.min_free_margin_percent[m]}
                        onChange={(e) => saveRisk({ min_free_margin_percent: { [m]: parseFloat(e.target.value) || 0 } })}
                        className="w-20 text-center bg-zinc-800 border-zinc-700 mx-auto"
                      />
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="pb-2"><CardTitle className="text-sm">Actions</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={async () => {
                setSaving(true)
                await fetch('/api/actions/refresh-policy', { method: 'POST' })
                await load()
                setSaving(false)
              }}
              className="px-3 py-1.5 rounded bg-blue-900 text-blue-200 hover:bg-blue-800 text-sm"
            >
              🔄 Refresh Policy
            </button>
            <button
              onClick={async () => {
                setSaving(true)
                await fetch('/api/actions/copy-to-mt5', { method: 'POST' })
                setSaving(false)
              }}
              className="px-3 py-1.5 rounded bg-green-900 text-green-200 hover:bg-green-800 text-sm"
            >
              📋 Copy to MT5
            </button>
            <button
              onClick={async () => {
                setSaving(true)
                await fetch('/api/actions/validate-config', { method: 'POST' })
                setSaving(false)
              }}
              className="px-3 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:bg-zinc-700 text-sm"
            >
              ✅ Validate Config
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}