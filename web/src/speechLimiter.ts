/** Bound how many syntheses are in flight at once.
 *
 * The queue used to call the provider for *every* sentence the moment it was
 * split off, so a six-sentence reply opened six simultaneous requests. Every
 * ElevenLabs plan caps concurrent requests — two on the entry tiers — so the
 * first sentences were synthesised, the rest were refused with
 * `too_many_concurrent_requests`, and the cloned voice gave up mid-reply.
 * That is the "it starts in my voice and then switches" symptom exactly.
 *
 * Preparing ahead is still what keeps the reply gapless; it just has to stop
 * at the number of requests the account is actually allowed to make.
 */

/** The floor across ElevenLabs plans. One request plays while the next is
 *  prepared, which is all the look-ahead the playback queue can use anyway. */
export const MAX_CONCURRENT_SYNTHESES = 2

export type Limiter = <T>(job: () => Promise<T>) => Promise<T>

export function createLimiter(max: number = MAX_CONCURRENT_SYNTHESES): Limiter {
  let active = 0
  const waiting: (() => void)[] = []

  return async function run<T>(job: () => Promise<T>): Promise<T> {
    // `while`, not `if`: a woken waiter must re-check, because several can be
    // released before any of them takes its slot.
    while (active >= max) {
      await new Promise<void>((resolve) => waiting.push(resolve))
    }
    active += 1
    try {
      return await job()
    } finally {
      active -= 1
      waiting.shift()?.()
    }
  }
}
