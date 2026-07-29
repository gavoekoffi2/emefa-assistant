/**
 * Normalises a raw Web Audio analyser FFT into ElevenLabs' voice spectrum.
 *
 * An AnalyserNode spans 0 Hz to Nyquist. ElevenLabs' realtime accessor instead
 * exposes 100 Hz–8 kHz across its whole array. The facial viseme solver consumes
 * the latter contract, so cloned audio must be remapped before it reaches it.
 */

import { VOICE_RANGE_HZ } from './visemes.ts'

export function remapAnalyserSpectrum(
  source: ArrayLike<number>,
  sampleRate: number,
  outputLength = 128,
): Uint8Array {
  const output = new Uint8Array(Math.max(0, outputLength))
  if (source.length === 0 || output.length === 0 || sampleRate <= 0) return output

  const nyquist = sampleRate / 2
  const [lowHz, highHz] = VOICE_RANGE_HZ
  for (let index = 0; index < output.length; index += 1) {
    const hz = lowHz + (index / output.length) * (highHz - lowHz)
    const sourcePosition = Math.min(source.length - 1, (hz / nyquist) * source.length)
    const left = Math.floor(sourcePosition)
    const right = Math.min(source.length - 1, left + 1)
    const fraction = sourcePosition - left
    output[index] = Math.round(source[left] * (1 - fraction) + source[right] * fraction)
  }
  return output
}
