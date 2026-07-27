/** One-shot completion signal for Web Audio playback.
 *
 * Stopping an AudioBufferSourceNode after clearing `onended` does not resolve
 * promises that are awaiting natural playback completion. This latch gives
 * both natural completion and interruption the same idempotent exit path.
 */
export type PlaybackLatch = {
  promise: Promise<void>
  settle: () => boolean
}

export function createPlaybackLatch(): PlaybackLatch {
  let settled = false
  let resolvePromise: () => void = () => undefined
  const promise = new Promise<void>((resolve) => {
    resolvePromise = resolve
  })

  return {
    promise,
    settle: () => {
      if (settled) return false
      settled = true
      resolvePromise()
      return true
    },
  }
}
