/** What the last main-thread request was answered over, and when it was sent. */
export type Snapshot = {
  /** Model id the API reported. */
  model: string
  /** input + cache_read + cache_creation tokens of the last response. */
  tokens: number
  /** Context window of the session's model, in tokens; 0 when unknown. */
  window: number
  /** tokens / window as a percentage, as the status line reports it. */
  percent?: number
  /** Epoch ms the request was sent: the moment it renewed the cache. */
  sentAt: number
  /**
   * Compacted since that request: `tokens` estimates the summary and what it
   * leaves in place, which the next request writes to the cache.
   */
  compacted?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'context-bar': { snap: Snapshot | null; now: number }
  }
}
