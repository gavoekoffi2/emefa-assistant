/** Text chunking for low-latency cloned speech playback. */

const SENTENCE_CHARS = 12
export const EARLY_COMMA_CHARS = 24
export const MAX_UNPUNCTUATED_CHARS = 96
const IDEAL_UNPUNCTUATED_CHARS = 84
const MIN_UNPUNCTUATED_CHARS = 48

/**
 * Extracts complete speakable chunks while keeping an unfinished tail.
 *
 * Full punctuation remains the preferred boundary. A sufficiently developed
 * comma may start speech early, matching ElevenLabs' own realtime behaviour.
 * The hard length boundary prevents a punctuation-free LLM stream from holding
 * the cloned voice until the whole answer has been generated.
 */
export function splitSpeakableText(text: string, force = false) {
  const segments: string[] = []
  let remainder = text
  while (remainder.length > 0) {
    const sentence = remainder.match(new RegExp(`^([\\s\\S]{${SENTENCE_CHARS},}?[.!?…;:])(?:\\s+|$)`))
    if (sentence) {
      segments.push(sentence[1].trim())
      remainder = remainder.slice(sentence[0].length)
      continue
    }

    const comma = remainder.match(new RegExp(`^([\\s\\S]{${EARLY_COMMA_CHARS},}?,)(?:\\s+|$)`))
    if (comma) {
      segments.push(comma[1].trim())
      remainder = remainder.slice(comma[0].length)
      continue
    }

    if (remainder.length > MAX_UNPUNCTUATED_CHARS) {
      const boundary = remainder.lastIndexOf(' ', IDEAL_UNPUNCTUATED_CHARS)
      const cut = boundary >= MIN_UNPUNCTUATED_CHARS ? boundary : IDEAL_UNPUNCTUATED_CHARS
      segments.push(remainder.slice(0, cut).trim())
      remainder = remainder.slice(cut).trimStart()
      continue
    }
    break
  }
  if (force && remainder.trim()) {
    const tail = remainder.trim()
    // Streaming providers can emit punctuation as a final standalone delta.
    // Sending "." or "…" to TTS wastes a request and can produce unusable
    // audio, so only enqueue tails containing actual speech characters.
    if (/[\p{L}\p{N}]/u.test(tail)) segments.push(tail)
    remainder = ''
  }
  return { segments, remainder }
}
