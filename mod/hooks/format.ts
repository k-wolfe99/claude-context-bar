// Pure helpers for the context bar: no `$`, so the tests drive them directly.

// (substrings, input $/MTok, cache-read multiplier). First match wins, so a
// point release sits above its base model: "opus" would also match Opus 5.5.
// Mirrors PRICES in claude-context-bar.py; check_pricing.py checks that one.
// Source: https://platform.claude.com/docs/en/about-claude/pricing
export const PRICES: ReadonlyArray<readonly [readonly string[], number, number]> = [
  [['fable-5-1', 'fable 5.1', 'mythos-5-1', 'mythos 5.1'], 10.0, 0.025],
  [['fable', 'mythos'], 10.0, 0.1],
  [['opus-5-5', 'opus 5.5'], 4.0, 0.05],
  [['opus'], 5.0, 0.1],
  [['sonnet-5', 'sonnet 5'], 2.0, 0.1],
  [['sonnet'], 3.0, 0.1],
  [['haiku'], 1.0, 0.1],
]

// xterm-256 colors from the Python bar, as hex: 82 118 154 226 220 214 208 196.
const STOPS: ReadonlyArray<readonly [number, string]> = [
  [15, '#5fff00'],
  [28, '#87ff00'],
  [42, '#afff00'],
  [55, '#ffff00'],
  [65, '#ffd700'],
  [75, '#ffaf00'],
  [87, '#ff8700'],
  [101, '#ff0000'],
]

export const GREEN = '#5fff00'
export const RED = '#ff0000'
export const EMPTY = '#444444'
export const DIM = '#8a8a8a'

/** The gradient color for a 0-100 fill. */
export function gradient(pct: number): string {
  return (STOPS.find(([threshold]) => pct < threshold) ?? STOPS[STOPS.length - 1]!)[1]
}

/** claude-opus-5-5[1m] -> Opus 5.5, claude-haiku-4-5-20251001 -> Haiku 4.5. */
export function modelName(id: string): string {
  const ident = id.replace(/\[.*?\]$/, '').replace(/^claude-/, '')
  const parts = ident.split('-').filter(p => !/^\d{8}$/.test(p))
  const words = parts.filter(p => !/^\d+$/.test(p))
  const version = parts.filter(p => /^\d+$/.test(p)).join('.')
  if (words.length === 0) return id
  const name = words.map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  return version ? `${name} ${version}` : name
}

/** 44800 -> 44.8k, 200000 -> 200k, 1000000 -> 1M. */
export function fmtTokens(n: number): string {
  const short = (v: number, unit: string) =>
    `${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`
  if (n >= 1_000_000) return short(n / 1_000_000, 'M')
  if (n >= 1_000) return short(n / 1_000, 'k')
  return String(n)
}

/** Input $/MTok and the cache-read multiplier, or undefined for an unknown model. */
export function price(model: string): { rate: number; readMult: number } | undefined {
  const ident = model.toLowerCase()
  const hit = PRICES.find(([needles]) => needles.some(n => ident.includes(n)))
  return hit && { rate: hit[1], readMult: hit[2] }
}

/** What the next request costs over `tokens`: inside the TTL, and after it. */
export function cachePrices(
  model: string,
  tokens: number,
  writeMult: number,
): { read: number; write: number } | undefined {
  const p = price(model)
  if (!p || tokens <= 0) return undefined
  const base = (tokens / 1_000_000) * p.rate
  return { read: base * p.readMult, write: base * writeMult }
}

/** 252000 -> 4:12, 3_540_000 -> 59:00, 3_600_000 -> 1:00:00. Rounds up, so 0:00 means lapsed. */
export function countdown(ms: number): string {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/** Filled and empty cell counts for a 0-100 fill. */
export function cells(pct: number, width: number): { filled: number; empty: number } {
  const filled = Math.min(width, Math.max(0, Math.round((pct / 100) * width)))
  return { filled, empty: width - filled }
}

/** A configured bar width, or 24 for anything unusable. */
export function barWidth(raw: unknown): number {
  return typeof raw === 'number' && Number.isInteger(raw) && raw >= 1 && raw <= 200 ? raw : 24
}
