import { atom, read, update } from 'claude-code'
import type { Elements, EngineInterface, Register } from 'claude-code'

import type { Snapshot } from '../types'
import {
  DIM, EMPTY, GREEN, RED,
  barWidth, cachePrices, cells, countdown, fmtTokens, gradient, modelName,
} from './format'

const snap = atom({ plugin: 'context-bar', key: 'snap' } as const, null)
const now = atom({ plugin: 'context-bar', key: 'now' } as const, 0)

/**
 * The conversation's last main-thread response, read from its transcript: what
 * it was answered over and when. Claude Code names the transcript after the
 * session id, under projects/ in its config directory, in a folder named for
 * the working directory with every other character replaced by '-'. The
 * response's own timestamp is used, not the file's mtime, because resuming
 * appends bookkeeping rows that would make a cold cache look fresh. A
 * compaction since that response stands in for it: nothing after it is cached.
 */
async function lastResponse($: EngineInterface): Promise<Snapshot | null> {
  const id = await $.session.id()
  const config = (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await $.env.get('HOME')}/.claude`
  const project = (await $.session.cwd()).replace(/[^A-Za-z0-9]/g, '-')
  const text = await tail($, `${config}/projects/${project}/${id}.jsonl`)
  if (text === null) return null
  // The tail may start mid-row; that row fails to parse and is skipped.
  const rows = text.split('\n')
  for (let i = rows.length - 1; i >= 0; i--) {
    let row: TranscriptRow
    try {
      row = JSON.parse(rows[i] ?? '')
    } catch {
      continue
    }
    if (row.type === 'system' && row.subtype === 'compact_boundary') {
      return compacted($, row.compactMetadata?.postTokens)
    }
    const usage = row.message?.usage
    if (row.type !== 'assistant' || row.isSidechain || !usage || !row.timestamp) continue
    const tokens =
      (usage.input_tokens ?? 0) + (usage.cache_read_input_tokens ?? 0) + (usage.cache_creation_input_tokens ?? 0)
    const { context } = await $.session.usage()
    return {
      model: row.message?.model ?? (await $.session.model()),
      tokens,
      window: context.window,
      percent: context.window > 0 ? (tokens / context.window) * 100 : undefined,
      sentAt: Date.parse(row.timestamp),
    }
  }
  return null
}

/**
 * The end of a transcript, where its last response is. A long session's file
 * outgrows $.fs.read's 4 MiB limit (7 MB is ordinary), so the CLI reads the
 * last 4 MB with tail. $.process.run is CLI-only, so elsewhere the whole file
 * is read, which works while it is under the limit.
 */
async function tail($: EngineInterface, path: string): Promise<string | null> {
  try {
    const { exitCode, stdout } = await $.process.run(['tail', '-c', '4000000', path], { timeoutMs: 5_000 })
    if (exitCode === 0) return stdout
  } catch {
    // No host commands here: fall through to a whole-file read.
  }
  try {
    return await $.fs.read(path)
  } catch {
    return null
  }
}

/**
 * The conversation just compacted, sized as the summary (`summary`, the
 * compaction's own count) plus what it leaves in place: the system prompt,
 * tools and memory, from /context's breakdown. Neither count is what the next
 * request will send, so the bar marks it an estimate until that request.
 *
 * The breakdown's own total doesn't serve. Its Messages row is fitted to the
 * last response, which is the conversation before compaction while the hook
 * runs, and a local count after; that came out 40% high on 2.1.287.
 */
async function compacted($: EngineInterface, summary: number | undefined): Promise<Snapshot | null> {
  if (!summary) return null
  const { context } = await $.session.usage({ breakdown: 'summary' })
  const used = context.breakdown?.categories.filter(c => c.kind === 'used') ?? []
  // The one row with no kind of its own; without it, the summary alone.
  const messages = used.find(c => c.name === 'Messages')
  const kept = messages ? used.reduce((n, c) => n + c.tokens, 0) - messages.tokens : 0
  const tokens = kept + summary
  return {
    model: await $.session.model(), tokens, window: context.window,
    percent: context.window > 0 ? (tokens / context.window) * 100 : undefined, sentAt: 0, compacted: true,
  }
}

/** The bar for the conversation now on screen, after a load, /clear or /resume. */
async function snapshotFor($: EngineInterface): Promise<Snapshot | null> {
  const resumed = await lastResponse($)
  if (resumed) return resumed
  // No transcript to read: the window's figures alone, the clock unknown.
  const { context } = await $.session.usage()
  if (!context.tokens) return null
  return {
    model: await $.session.model(), tokens: context.tokens, window: context.window,
    percent: context.percent, sentAt: 0,
  }
}

/** The fields of a transcript row this reads. */
type TranscriptRow = {
  type?: string
  subtype?: string
  isSidechain?: boolean
  compactMetadata?: { postTokens?: number }
  timestamp?: string
  message?: {
    model?: string
    usage?: { input_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number }
  }
}

export const register: Register = (on, options) => {
  const ttlMs = options.cacheTtl === '5m' ? 300_000 : 3_600_000
  // Cache writes bill at 1.25x input for the 5-minute TTL, 2x for 1-hour.
  const writeMult = ttlMs > 300_000 ? 2 : 1.25
  const width = barWidth(options.barWidth)
  const placement = options.placement === 'above' ? 'above' : 'below'

  // When the last main-thread request was sent. Module state, so a reload
  // restores it from $.state in session.start.
  let sentAt = 0

  // The conversation the bar describes. /clear and /resume switch it inside a
  // running session without any event a mod receives (SessionStart reaches
  // settings hooks only, and an in-session /resume raises none), and the
  // switch drops this plugin's $.state. So the clock checks every tick.
  let sessionId = ''

  // The status line repaints on conversation events only, so it could never
  // count down. This clock ticks on its own, and stops writing once the cache
  // has lapsed, so an idle session isn't redrawn every second for nothing.
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    sessionId = await $.session.id()
    // A reload keeps $.state, and its send time is more exact than the
    // transcript's response time. A fresh process starts from the transcript.
    const prior = (await read($, snap)) ?? (await snapshotFor($))
    sentAt = prior?.sentAt ?? 0
    await update($, snap, () => prior)
    const started = await $.clock.now()
    await update($, now, () => started)
    $.clock.every(1000, async () => {
      const t = await $.clock.now()
      const id = await $.session.id()
      if (id !== sessionId) {
        sessionId = id
        const switched = await snapshotFor($)
        sentAt = switched?.sentAt ?? 0
        await update($, snap, () => switched)
        await update($, now, () => t)
      } else if (sentAt && t <= sentAt + ttlMs + 1000) {
        await update($, now, () => t)
      }
    })
    return result
  })

  // Every request renews the cache, tool-call steps included. It is renewed
  // when the request is read, so the clock starts at send, not when a long
  // response finishes streaming. Subagents cache their own prefix and are
  // left out: they don't keep the main conversation's cache warm.
  on('turn.step', async function* ($, e, next) {
    if (e.agentId !== undefined) return yield* next(e)

    const at = await $.clock.now()
    const result = yield* next(e)
    const usage = result.usage
    if (usage) {
      const { context } = await $.session.usage()
      const tokens =
        context.tokens ??
        usage.input_tokens + usage.cache_read_input_tokens + usage.cache_creation_input_tokens
      const fresh: Snapshot = {
        model: usage.model, tokens, window: context.window, percent: context.percent, sentAt: at,
      }
      sentAt = at
      await update($, snap, () => fresh)
      await update($, now, () => at)
    }
    return result
  })

  // A compaction replaces the conversation with a summary between requests, so
  // the bar would show the old size until the next one. Redraw it as soon as
  // the compaction stands. A subagent's or fork's own compaction, a precompute
  // (kept for later, installs nothing) and a vetoed one leave it alone.
  on('session.compact', async ($, e, next) => {
    const result = await next(e)
    if (e.agentId !== undefined || e.trigger === 'precompute' || result.skip !== undefined) return result
    const after = await compacted($, result.tokensAfter)
    if (after) {
      sentAt = 0
      await update($, snap, () => after)
    }
    return result
  })

  // Below the prompt (the default) is where the status line drew: the bar on
  // its own row, then Claude Code's hint line with the mode pills, kept live by
  // wrapping the engine's own drawing rather than replacing it.
  on('ui.render', { component: 'PromptHint' }, async ($, e, next) => {
    const hint = await next(e)
    const s = placement === 'below' ? await read($, snap) : null
    if (s === null) return hint
    const t = await read($, now)
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box flexDirection="column">
        {line({ Box, Text }, s, t)}
        {hint}
      </Box>
    )
  })

  // Above the prompt: a band of its own. The blank row between the band and
  // the prompt is the prompt's own margin. A band can't reach it: content
  // offset into that row (position relative, top 1) is clipped to the band's
  // area and draws nothing.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = placement === 'above' ? await read($, snap) : null
    if (e.props.hasSurvey || s === null) return next(e)
    const t = await read($, now)
    const { Box, Text } = $.ui.resolve(e)
    return line({ Box, Text }, s, t)
  })

  /**
   * The bar as one row. Model and tokens are dim, as Claude Code draws
   * status-line text. No indent of its own: the hint line's container already
   * pads it, so the model name lines up with the mode arrows.
   */
  function line({ Box, Text }: Pick<Elements['terminal'], 'Box' | 'Text'>, s: Snapshot, now: number) {
    const t = Math.max(now, s.sentAt)
    const pct = s.percent ?? (s.window > 0 ? (s.tokens / s.window) * 100 : 0)
    const bar = cells(pct, width)
    const isKnown = s.sentAt > 0 || s.compacted === true
    const remaining = s.sentAt + ttlMs - t
    const isWarm = s.sentAt > 0 && remaining > 0
    const cost = cachePrices(s.model, s.tokens, writeMult)

    return (
      <Box flexDirection="row">
        <Text dimColor>{modelName(s.model)}  [</Text>
        <Text color={gradient(pct)}>{'█'.repeat(bar.filled)}</Text>
        <Text color={EMPTY}>{'░'.repeat(bar.empty)}</Text>
        <Text dimColor>
          ]  {s.compacted ? '~' : ''}{fmtTokens(s.tokens)}
          {s.window > 0 ? ` / ${fmtTokens(s.window)}` : ''} ({pct.toFixed(1)}%)
        </Text>
        {s.compacted ? (
          <Text color={DIM}>  ⏱ compacted</Text>
        ) : !isKnown ? (
          <Text color={DIM}>  ⏱ --:--</Text>
        ) : isWarm ? (
          <Text color={gradient(100 - (remaining / ttlMs) * 100)}>  ⏱ {countdown(remaining)}</Text>
        ) : (
          <Text color={RED}>  ⏱ lapsed</Text>
        )}
        {cost && (isWarm || !isKnown) && <Text color={GREEN}>  ${cost.read.toFixed(3)}</Text>}
        {cost && (isWarm || !isKnown) && <Text color={DIM}>→</Text>}
        {cost && (
          <Text color={RED} bold={isKnown && !isWarm && !s.compacted}>
            {isKnown && !isWarm ? '  ' : ''}${cost.write.toFixed(3)}
          </Text>
        )}
      </Box>
    )
  }
}
