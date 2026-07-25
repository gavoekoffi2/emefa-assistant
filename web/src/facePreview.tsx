// Development-only harness for eyeballing the hologram in isolation.
// Query params: ?state=speaking&vol=0.7&vowel=a|ou|i|s
import { createRoot } from 'react-dom/client'
import { EMEFAFace } from './EMEFAFace'
import type { VoiceState } from './App'

const params = new URLSearchParams(location.search)
const state = (params.get('state') ?? 'idle') as VoiceState
const volume = Number(params.get('vol') ?? 0)
const vowel = params.get('vowel') ?? 'a'
document.documentElement.style.setProperty('--zoom', params.get('zoom') ?? '1.6')

// Rough formant profiles so lip shapes can be inspected without a live call.
const PROFILES: Record<string, Array<[number, number, number]>> = {
  a: [[0.012, 0.9, 0.008], [0.03, 0.5, 0.012], [0.07, 0.25, 0.02]],
  ou: [[0.012, 0.8, 0.008], [0.032, 0.85, 0.012], [0.075, 0.1, 0.02]],
  i: [[0.01, 0.45, 0.006], [0.03, 0.12, 0.01], [0.085, 0.9, 0.03]],
  s: [[0.01, 0.03, 0.006], [0.25, 0.8, 0.2]],
  m: [[0.008, 0.05, 0.004]],
}

const spectrum = new Uint8Array(512)
const peaks = PROFILES[vowel] ?? PROFILES.a
for (let index = 0; index < spectrum.length; index += 1) {
  const f = index / spectrum.length
  let value = 0
  for (const [centre, gain, width] of peaks) {
    value += gain * Math.exp(-((f - centre) ** 2) / (2 * width * width))
  }
  spectrum[index] = Math.min(255, Math.round(value * 255))
}

createRoot(document.getElementById('root')!).render(
  <EMEFAFace
    state={state}
    onClick={() => undefined}
    getOutputVolume={() => volume}
    getOutputFrequencyData={() => spectrum}
  />,
)
