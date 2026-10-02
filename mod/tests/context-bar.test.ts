import { describe, expect, mock, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import type { On, RenderPropsOf } from 'claude-code'

import { countdown, fmtTokens, modelName } from '../hooks/format'

const OPUS = 'claude-opus-5-5'
const FIVE = { options: { cacheTtl: '5m' } }
const ABOVE = { options: { placement: 'above' } }

// What the engine draws on the hint line under the prompt.
const HINT = '? for shortcuts'
const PROMPT_HINT: RenderPropsOf['PromptHint'] = { isDraft: false, isWorking: false, hint: HINT }

const BAND: RenderPropsOf['AbovePrompt'] = {
  hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 10 }, view: {},
}

/** The engine beneath the plugin: a session, a model that answers every step, the usage figures. */
/** Where the mod looks for conversation `id`'s transcript, given the engine below. */
const transcriptOf = (id: string) => `/cfg/projects/-work-my-repo/${id}.jsonl`

/** A transcript whose last main-thread response was `at`, over `tokens`, then resume bookkeeping. */
function transcript(at: number, tokens: number) {
  return [
    { type: 'user', timestamp: new Date(at - 5_000).toISOString() },
    { type: 'assistant', timestamp: new Date(at).toISOString(), message: { model: OPUS, usage: { input_tokens: 100, cache_read_input_tokens: tokens - 100, cache_creation_input_tokens: 0 } } },
    // A subagent's row comes later but is not the main conversation's cache.
    { type: 'assistant', isSidechain: true, timestamp: new Date(at + 1_000).toISOString(), message: { model: 'claude-haiku-4-5', usage: { input_tokens: 9 } } },
    { type: 'mode' }, { type: 'permission-mode' },
  ].map(r => JSON.stringify(r)).join('\n') + '\n'
}

/** The conversation on screen, its transcripts, and whether host commands run (the CLI) or not. */
type World = {
  id: string; files: Record<string, string>; hasTail?: boolean; readLimit?: number
  /** /context's breakdown, as [row, tokens, kind]; absent, the engine gives none. */
  rows?: [string, number, string][]
  /** What a compaction comes to; absent, it stands at 18,340 tokens. */
  compaction?: { skip: string } | { tokensAfter?: number }
}

function engine(on: On, { tokens = 44_800, world = { id: 'conv-a', files: {} } }: { tokens?: number; world?: World } = {}) {
  // A real epoch: the bar reads a send time of 0 as unknown, so "an hour ago" must stay positive.
  const clock = mock.clock(on, { now: Date.UTC(2026, 9, 2, 14, 0) })
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.step', async function* ($, e) {
    return {
      turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as const,
      usage: {
        model: OPUS, input_tokens: 800, cache_read_input_tokens: 44_000,
        cache_creation_input_tokens: 0, output_tokens: 10,
      },
    }
  })
  on('session.usage', ($, e) => {
    const categories = world.rows?.map(([name, n, kind]) => ({ name, tokens: n, kind }))
    const breakdown = e.breakdown && categories ? { categories } : undefined
    const context = { tokens, window: 1_000_000, percent: (tokens / 1_000_000) * 100, ...(breakdown ? { breakdown } : {}) }
    // The breakdown carries a grid and totals too; the bar reads only its rows.
    return { value: { startedAt: 0, context, rateLimits: [] } as never }
  })
  on('session.compact', () => {
    const c = world.compaction ?? { tokensAfter: 18_340 }
    return 'skip' in c ? c : { messages: [SUMMARY], ...c }
  })
  on('session.model', () => ({ value: OPUS }))
  on('session.id', () => ({ value: world.id }))
  on('session.cwd', () => ({ value: '/work/my repo' }))
  mock.env(on, { CLAUDE_CONFIG_DIR: '/cfg' })
  // $.fs.read rejects past its limit (4 MiB live); tail reads the end of any size.
  on('fs.read', ($, e) => {
    const text = world.files[e.path]
    if (text === undefined) throw new Error(`ENOENT: ${e.path}`)
    if (text.length > (world.readLimit ?? Infinity)) throw new Error('over 4 MiB')
    return { value: text }
  })
  on('process.run', ($, e) => {
    if (world.hasTail === false) throw new Error('no host commands on this surface')
    const [cmd, flag, bytes, path] = e.argv
    if (cmd !== 'tail' || flag !== '-c' || path === undefined) throw new Error(`unexpected ${e.argv.join(' ')}`)
    const text = world.files[path]
    if (text === undefined) return { value: { exitCode: 1, stdout: '', stderr: 'No such file', isStdoutTruncated: false, isStderrTruncated: false } }
    return { value: { exitCode: 0, stdout: text.slice(-Number(bytes)), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  // The engine draws nothing of its own in the band, and its hint line under the prompt.
  on('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'Box' as const }))
  on('ui.render', { component: 'PromptHint' }, () => ({ type: 'Text' as const, children: [HINT] }))
  return clock
}

/** One main-thread (or subagent) request, read to its end; resolves to its result. */
async function step($: Engine, agentId?: string) {
  const s = $.turn.step({
    turnId: 't', index: 0, model: OPUS, messageCount: 1, ...(agentId ? { agentId } : {}),
  })
  // Read by hand: `for await` drops a generator's return value, and the kit's
  // `s.result` resolves undefined once the stream has been iterated.
  let r = await s.next()
  while (!r.done) r = await s.next()
  return r.value
}

/** The window as /context breaks it down, still fitted to the response before a compaction. */
const ROWS: [string, number, string][] = [
  ['System prompt', 7_000, 'used'], ['System tools', 19_000, 'used'], ['Memory files', 1_000, 'used'],
  ['Messages', 394_000, 'used'], ['Deferred tools', 5_000, 'deferred'],
  ['Free space', 546_000, 'free'], ['Autocompact buffer', 33_000, 'buffer'],
]

const SUMMARY = { role: 'user' as const, text: 'the summary', toolUses: [] }

/** A /compact over a short conversation. The kit leaves `messages`, the engine's own, to the caller. */
async function compact($: Engine) {
  const messages = [{ role: 'user' as const, text: 'hi', toolUses: [] }, { role: 'assistant' as const, text: 'hello', toolUses: [] }]
  return $.session.compact({ messages } as never)
}

/** All the text the band draws, flattened to one line ('' when it passes). */
function flat(node: unknown): string {
  if (typeof node === 'string') return node
  if (node && typeof node === 'object' && 'children' in node && Array.isArray(node.children)) {
    return node.children.map(flat).join('')
  }
  return ''
}

/** The bar's text under the prompt, the engine's hint line left out ('' when it draws none). */
async function below($: Engine) {
  const ui = await $.ui.mount({ plugin: 'context-bar', surface: 'terminal', component: 'PromptHint', props: PROMPT_HINT })
  return async () => flat(await ui.drawn()).replace(HINT, '')
}

/** The band's text above the prompt ('' when it passes). */
async function band($: Engine, props: Partial<RenderPropsOf['AbovePrompt']> = {}) {
  const ui = await $.ui.mount({
    plugin: 'context-bar', surface: 'terminal', component: 'AbovePrompt', props: { ...BAND, ...props },
  })
  return async () => flat(await ui.drawn())
}

describe('bar', () => {
  test('draws nothing of its own in a session with no usage yet', async ($, on) => {
    engine(on, { tokens: 0 })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    expect(await line()).toBe('')
  })

  test('shows the model, the window, and a full countdown after a request', FIVE, async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    // 44.8k tokens at $4/MTok: read at 0.05x, write at 1.25x.
    expect(await line()).toBe(
      'Opus 5.5  [' + '█' + '░'.repeat(23) + ']  44.8k / 1M (4.5%)  ⏱ 5:00  $0.009→$0.224',
    )
  })

  test('counts down on its own clock, with no conversation event', FIVE, async ($, on) => {
    const clock = engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    await clock.advance(72_000)
    expect(await line()).toContain('⏱ 3:48  $0.009→$0.224')
  })

  test('says lapsed, and shows only the write price, once the TTL passes', FIVE, async ($, on) => {
    const clock = engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    await clock.advance(301_000)
    expect(await line()).toMatch(/⏱ lapsed  \$0\.224$/)
  })

  test('a request restarts the clock', FIVE, async ($, on) => {
    const clock = engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    await clock.advance(200_000)
    await step($)
    const line = await below($)
    expect(await line()).toContain('⏱ 5:00')
  })

  test("a subagent's request does not restart the main clock", FIVE, async ($, on) => {
    const clock = engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    await clock.advance(200_000)
    await step($, 'agent-1')
    const line = await below($)
    await clock.settle()
    expect(await line()).toContain('⏱ 1:40')
  })

  test('defaults to the 1h TTL: counts from an hour and prices writes at 2x', async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    expect(await line()).toContain('⏱ 1:00:00  $0.009→$0.358')
  })

  test('draws at load from the session usage, with the clock unknown until a request', FIVE, async ($, on) => {
    const clock = engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    await clock.advance(10_000)
    expect(await line()).toBe(
      'Opus 5.5  [' + '█' + '░'.repeat(23) + ']  44.8k / 1M (4.5%)  ⏱ --:--  $0.009→$0.224',
    )
    await step($)
    expect(await line()).toContain('⏱ 5:00')
  })

  test('a /resume shows the resumed context within a second, its countdown already running', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {} }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    expect(await line()).toBe('')
    // Resume a conversation whose last response came two minutes ago.
    world.files[transcriptOf('conv-b')] = transcript(clock.now() - 120_000, 300_000)
    world.id = 'conv-b'
    await clock.advance(1_000)
    // 300k tokens at $4/MTok, 2m01s of its 5 minutes gone.
    expect(await line()).toBe(
      'Opus 5.5  [' + '█'.repeat(7) + '░'.repeat(17) + ']  300k / 1M (30.0%)  ⏱ 2:59  $0.060→$1.500',
    )
    await clock.advance(60_000)
    expect(await line()).toContain('⏱ 1:59')
  })

  test('a /resume after the TTL shows the stale context as lapsed, with the re-cache price', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {} }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    world.files[transcriptOf('conv-b')] = transcript(clock.now() - 3_600_000, 300_000)
    world.id = 'conv-b'
    await clock.advance(1_000)
    expect(await line()).toMatch(/300k \/ 1M \(30\.0%\)  ⏱ lapsed  \$1\.500$/)
  })

  test('a transcript too big to read whole is read from its tail', FIVE, async ($, on) => {
    // A long session: the last response is preceded by megabytes of history.
    const world: World = { id: 'conv-a', files: {}, readLimit: 1_000 }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    const history = (JSON.stringify({ type: 'user', text: 'x'.repeat(500) }) + '\n').repeat(10)
    world.files[transcriptOf('conv-b')] = history + transcript(clock.now() - 120_000, 300_000)
    world.id = 'conv-b'
    await clock.advance(1_000)
    expect(await line()).toContain('300k / 1M (30.0%)  ⏱ 2:59')
  })

  test('without host commands (the desktop), a transcript under the read limit is read whole', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {}, hasTail: false }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    world.files[transcriptOf('conv-b')] = transcript(clock.now() - 120_000, 300_000)
    world.id = 'conv-b'
    await clock.advance(1_000)
    expect(await line()).toContain('⏱ 2:59')
  })

  test('with no transcript it can read, a resumed bar shows the window and an unknown clock', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {}, hasTail: false, readLimit: 10 }
    const clock = engine(on, { world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    world.files[transcriptOf('conv-b')] = transcript(clock.now() - 120_000, 300_000)
    world.id = 'conv-b'
    await clock.advance(1_000)
    expect(await line()).toContain('44.8k / 1M (4.5%)  ⏱ --:--')
  })

  test('a fresh process opens a resumed conversation from its transcript', FIVE, async ($, on) => {
    const world: World = { id: 'conv-b', files: {} }
    const clock = engine(on, { tokens: 0, world })
    world.files[transcriptOf('conv-b')] = transcript(clock.now() - 60_000, 300_000)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    expect(await line()).toContain('300k / 1M (30.0%)  ⏱ 4:00')
  })

  test('a /clear hides the bar until the new conversation makes a request', async ($, on) => {
    const world: World = { id: 'conv-a', files: {} }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    expect(await line()).toContain('Opus 5.5')
    // A cleared conversation: a new id, a transcript with no response yet.
    world.files[transcriptOf('conv-c')] = JSON.stringify({ type: 'user' }) + '\n'
    world.id = 'conv-c'
    await clock.advance(1_000)
    expect(await line()).toBe('')
    await step($)
    expect(await line()).toContain('⏱ 1:00:00')
  })

  test('a /compact redraws the bar at once, at the compacted size, priced as a write', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {}, rows: ROWS }
    engine(on, { tokens: 421_000, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    expect(await line()).toContain('421k / 1M')
    await compact($)
    // The 18,340-token summary plus the 27k of prompt, tools and memory it keeps.
    // None of it is cached as it now reads: the next request writes it, 1.25x of $4/MTok.
    expect(await line()).toBe(
      'Opus 5.5  [' + '█' + '░'.repeat(23) + ']  ~45.3k / 1M (4.5%)  ⏱ compacted  $0.227',
    )
    await step($)
    expect(await line()).toContain('⏱ 5:00')
  })

  test("without /context's breakdown, a compaction shows the summary's own count", FIVE, async ($, on) => {
    engine(on, { tokens: 421_000 })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    await compact($)
    expect(await line()).toContain('~18.3k / 1M (1.8%)  ⏱ compacted')
  })

  test('a vetoed compaction leaves the bar as it was', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {}, rows: ROWS, compaction: { skip: 'blocked by a hook' } }
    engine(on, { tokens: 421_000, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await below($)
    await compact($)
    expect(await line()).toContain('421k / 1M (42.1%)  ⏱ 5:00')
  })

  test('a /resume onto a compacted conversation shows the compacted size, not the last response', FIVE, async ($, on) => {
    const world: World = { id: 'conv-a', files: {}, rows: ROWS }
    const clock = engine(on, { tokens: 0, world })
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const line = await below($)
    const boundary = { type: 'system', subtype: 'compact_boundary', compactMetadata: { postTokens: 18_340 } }
    world.files[transcriptOf('conv-b')] =
      transcript(clock.now() - 120_000, 300_000) + JSON.stringify(boundary) + '\n' + JSON.stringify({ type: 'user' }) + '\n'
    world.id = 'conv-b'
    await clock.advance(1_000)
    expect(await line()).toContain('~45.3k / 1M (4.5%)  ⏱ compacted  $0.227')
  })

  type Node = { props?: Record<string, unknown>; children?: Node[] }

  test('under the prompt: the bar on its own row, then the engine\'s hint line, kept whole', async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const ui = await $.ui.mount({ plugin: 'context-bar', surface: 'terminal', component: 'PromptHint', props: PROMPT_HINT })
    const tree = (await ui.drawn()) as Node
    expect(tree.props?.flexDirection).toBe('column')
    expect(flat(tree.children?.[0])).toContain('Opus 5.5  [')
    expect(tree.children?.[1]).toEqual({ type: 'Text', children: [HINT] })
    // No indent of its own, so the model name lines up with the hint line's
    // mode arrows, as the status line did. The container already pads both.
    expect(tree.children?.[0]?.props?.paddingLeft).toBeUndefined()
  })

  test('draws the model and tokens dim, the colors only on the bar, timer and prices', async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const ui = await $.ui.mount({ plugin: 'context-bar', surface: 'terminal', component: 'PromptHint', props: PROMPT_HINT })
    const row = ((await ui.drawn()) as Node).children?.[0]
    expect(row?.children?.[0]?.props?.dimColor).toBe(true)
    expect(row?.children?.[3]?.props?.dimColor).toBe(true)
    expect(row?.children?.[1]?.props?.color).toBe('#5fff00')
  })

  test('under the prompt by default, so the band above passes', async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    expect(await (await band($))()).toBe('')
  })

  test('placement above draws the band and leaves the hint line to the engine', ABOVE, async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const above = await band($)
    expect(await above()).toContain('Opus 5.5  [')
    const ui = await $.ui.mount({ plugin: 'context-bar', surface: 'terminal', component: 'PromptHint', props: PROMPT_HINT })
    expect(await ui.drawn()).toEqual({ type: 'Text', children: [HINT] })
    // An offset row is clipped to the band and draws nothing (seen on 2.1.287).
    const tree = (await (await $.ui.mount({ plugin: 'context-bar', surface: 'terminal', component: 'AbovePrompt', props: BAND })).drawn()) as Node
    expect(tree.props?.top).toBeUndefined()
  })

  test('placement above yields the band to a survey', ABOVE, async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    await step($)
    const line = await band($, { hasSurvey: true })
    expect(await line()).toBe('')
  })

  test("passes the model's response through unchanged", async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
    const result = await step($)
    expect(result).toEqual(expect.objectContaining({ stopReason: 'end_turn', answer: '' }))
    expect(result?.usage?.cache_read_input_tokens).toBe(44_000)
  })

  test('draws the same line on the desktop', async ($, on) => {
    engine(on)
    await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
    await step($)
    const ui = await $.ui.mount({ plugin: 'context-bar', surface: 'desktop', component: 'PromptHint', props: PROMPT_HINT })
    expect(flat(await ui.drawn())).toContain('Opus 5.5  [')
  })
})

describe('format', () => {
  test('model names', () => {
    expect(modelName('claude-opus-5-5[1m]')).toBe('Opus 5.5')
    expect(modelName('claude-haiku-4-5-20251001')).toBe('Haiku 4.5')
    expect(modelName('claude-fable-5-1')).toBe('Fable 5.1')
  })

  test('token counts', () => {
    expect(fmtTokens(44_800)).toBe('44.8k')
    expect(fmtTokens(200_000)).toBe('200k')
    expect(fmtTokens(1_000_000)).toBe('1M')
    expect(fmtTokens(999)).toBe('999')
  })

  test('countdowns round up, so 0:00 only shows once lapsed', () => {
    expect(countdown(252_000)).toBe('4:12')
    expect(countdown(251_001)).toBe('4:12')
    expect(countdown(3_600_000)).toBe('1:00:00')
    expect(countdown(-5)).toBe('0:00')
  })
})
