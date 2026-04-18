import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { apiGet, apiPatch } from '@/lib/api'

interface GridTemplate {
  allow_new_basket: boolean
  grid_mode: string
  seed_mode: string
  step_pips: number
  initial_lot: number
  multiplier: number
  max_trades_per_side: number
  basket_tp_currency: number
  max_gross_lots: number
  max_basket_drawdown_currency: number
  min_step_to_spread_ratio: number
  min_free_margin_percent: number
  flatten_on_strong_avoid: boolean
  confidence: number
  reason: string
}

export default function GridPolicy() {
  const [templates, setTemplates] = useState<Record<string, GridTemplate>>({})
  const [selected, setSelected] = useState<string>('')
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const t = await apiGet<Record<string, GridTemplate>>('/config/grid-templates')
    setTemplates(t)
    if (!selected && Object.keys(t).length > 0) {
      setSelected(Object.keys(t).find(k => k !== 'no_trade') || Object.keys(t)[0])
    }
  }

  useEffect(() => { load() }, [])

  const save = async (name: string, patch: Partial<GridTemplate>) => {
    setSaving(true)
    await apiPatch(`/config/grid-templates/${name}`, patch)
    await load()
    setSaving(false)
  }

  const names = Object.keys(templates).filter(k => k !== 'no_trade')

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">Grid Templates</h2>
        {saving && <Badge variant="outline" className="text-xs">Saving...</Badge>}
      </div>

      <p className="text-sm text-zinc-400">
        Edit grid templates that the optimizer uses for pair selection.
      </p>

      {/* Template selector */}
      <div className="flex flex-wrap gap-2">
        {names.map((name) => (
          <button
            key={name}
            onClick={() => setSelected(name)}
            className={`px-3 py-1.5 rounded text-sm font-mono ${
              selected === name
                ? 'bg-zinc-700 text-white'
                : 'bg-zinc-900 text-zinc-400 hover:bg-zinc-800'
            }`}
          >
            {name}
          </button>
        ))}
      </div>

      {/* Template editor */}
      {selected && templates[selected] && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-mono">{selected}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <Label className="text-xs text-zinc-400">Step (pips)</Label>
                <Input
                  type="number" min={1} value={templates[selected].step_pips}
                  onChange={(e) => save(selected, { step_pips: parseInt(e.target.value) || 1 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Initial Lot</Label>
                <Input
                  type="number" step={0.01} min={0.01} value={templates[selected].initial_lot}
                  onChange={(e) => save(selected, { initial_lot: parseFloat(e.target.value) || 0.01 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Multiplier</Label>
                <Input
                  type="number" step={0.01} min={1.0} value={templates[selected].multiplier}
                  onChange={(e) => save(selected, { multiplier: parseFloat(e.target.value) || 1.0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Max Trades/Side</Label>
                <Input
                  type="number" min={1} value={templates[selected].max_trades_per_side}
                  onChange={(e) => save(selected, { max_trades_per_side: parseInt(e.target.value) || 1 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Grid Mode</Label>
                <Input
                  value={templates[selected].grid_mode}
                  disabled
                  className="bg-zinc-800 border-zinc-700 opacity-60"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Seed Mode</Label>
                <Input
                  value={templates[selected].seed_mode}
                  disabled
                  className="bg-zinc-800 border-zinc-700 opacity-60"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Basket TP ($)</Label>
                <Input
                  type="number" step={0.5} min={0} value={templates[selected].basket_tp_currency}
                  onChange={(e) => save(selected, { basket_tp_currency: parseFloat(e.target.value) || 0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Max DD ($)</Label>
                <Input
                  type="number" step={10} min={0} value={templates[selected].max_basket_drawdown_currency}
                  onChange={(e) => save(selected, { max_basket_drawdown_currency: parseFloat(e.target.value) || 0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Max Gross Lots</Label>
                <Input
                  type="number" step={0.01} min={0} value={templates[selected].max_gross_lots}
                  onChange={(e) => save(selected, { max_gross_lots: parseFloat(e.target.value) || 0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Step/Spread Ratio</Label>
                <Input
                  type="number" step={0.5} min={0} value={templates[selected].min_step_to_spread_ratio}
                  onChange={(e) => save(selected, { min_step_to_spread_ratio: parseFloat(e.target.value) || 0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Min Free Margin %</Label>
                <Input
                  type="number" step={5} min={0} max={100} value={templates[selected].min_free_margin_percent}
                  onChange={(e) => save(selected, { min_free_margin_percent: parseFloat(e.target.value) || 0 })}
                  className="bg-zinc-800 border-zinc-700"
                />
              </div>
              <div>
                <Label className="text-xs text-zinc-400">Confidence</Label>
                <Input
                  type="number" step={0.01} min={0} max={1} value={templates[selected].confidence}
                  disabled
                  className="bg-zinc-800 border-zinc-700 opacity-60"
                />
              </div>
            </div>
            <div className="text-xs text-zinc-500">{templates[selected].reason}</div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}