/**
 * Drives the facial rig from the assistant's own output audio.
 *
 * The band edges here are in **hertz**, and that matters more than anything
 * else in this file. `getOutputByteFrequencyData()` does not hand back a raw
 * FFT: the ElevenLabs client resamples the analyser into a *voice range* and
 * stretches it across the whole buffer, so bin `i` is
 *
 *     100 Hz + (i / binCount) * (8000 Hz - 100 Hz)
 *
 * Treating that buffer as if it spanned 0 Hz…Nyquist — which is the obvious
 * reading, and what this module did before — puts every band roughly three
 * times too low. The "first formant" band ends up measuring the pitch
 * fundamental and the "sibilance" band ends up measuring F2, so the articulation
 * contrasts are computed from the wrong things entirely and the mouth mostly
 * flaps with volume. Everything below is derived from `VOICE_RANGE_HZ`.
 *
 * Smoothing is expressed as time constants and integrated against the real
 * frame delta, so articulation looks identical at 60 Hz and at 120 Hz.
 */

export type VisemeTargets = {
  jawOpen: number
  lipRound: number
  lipWide: number
  lipPress: number
}

export type VisemeState = VisemeTargets & { level: number }

export const createVisemeState = (): VisemeState => ({
  jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0, level: 0,
})

/** The span the client's `getOutputByteFrequencyData` buffer actually covers. */
export const VOICE_RANGE_HZ: readonly [number, number] = [100, 8000]

/**
 * Speech bands, in hertz.
 *
 *   F1        how open the jaw is
 *   F2 low    back/rounded vowels — "ou", "o"
 *   F2 high   front/spread vowels — "i", "é"
 *   sibilance "s", "ch", "f"
 */
const BANDS: ReadonlyArray<readonly [number, number]> = [
  [250, 900],
  [700, 1300],
  [1500, 2800],
  [4000, 7800],
]

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value)

/** Bin index for a frequency, given the client's voice-range mapping. */
export function binForHz(hz: number, binCount: number) {
  const [low, high] = VOICE_RANGE_HZ
  const position = (hz - low) / (high - low)
  return Math.round(position * binCount)
}

/** Mean normalised energy in each speech band. */
export function bandEnergies(spectrum: ArrayLike<number>): [number, number, number, number] {
  const length = spectrum.length
  const energies: [number, number, number, number] = [0, 0, 0, 0]
  if (length === 0) return energies

  for (let band = 0; band < BANDS.length; band += 1) {
    const [lowHz, highHz] = BANDS[band]
    const from = Math.max(0, Math.min(length - 1, binForHz(lowHz, length)))
    const to = Math.max(from + 1, Math.min(length, binForHz(highHz, length)))
    let total = 0
    for (let index = from; index < to; index += 1) total += spectrum[index] / 255
    energies[band] = total / (to - from)
  }
  return energies
}

/** Maps the band energies and the output level onto rig targets. */
export function visemeTargets(spectrum: ArrayLike<number>, level: number): VisemeTargets {
  const loud = clamp01(level)
  if (loud <= 0.01) return { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0 }

  const [f1, f2Low, f2High, sibilance] = bandEnergies(spectrum)
  const voiced = f1 + f2Low + f2High
  const total = voiced + sibilance

  // Nothing in the speech bands while the stream is still running: that is a
  // stop or a bilabial closure, not silence. Closing the lips there is what
  // makes "m", "b" and "p" legible.
  if (total < 0.012) {
    return { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: clamp01(loud * 3) }
  }

  // Openness follows F1 against the rest of the voiced energy, scaled by how
  // loud the utterance actually is so quiet consonants do not gape.
  const openness = clamp01((f1 / (voiced + 1e-4)) * 1.9 - 0.18)
  const jawOpen = clamp01((openness * 0.82 + loud * 0.5) * clamp01(loud * 4.5))

  // Front/back contrast, normalised so it is independent of overall loudness.
  const contrast = (f2High - f2Low) / (f2High + f2Low + 1e-4)
  const sibilant = clamp01(sibilance / (total + 1e-4) * 2.6 - 0.25)

  const lipRound = clamp01(-contrast * 1.7) * clamp01(loud * 3.4) * (1 - sibilant * 0.7)
  const lipWide = clamp01(clamp01(contrast * 1.5) + sibilant * 0.75) * clamp01(loud * 3.4)

  return {
    jawOpen: jawOpen * (1 - sibilant * 0.55),
    lipRound,
    lipWide,
    lipPress: 0,
  }
}

/** Frame-rate independent one-pole coefficient for a given time constant. */
const coefficient = (dt: number, tau: number) => 1 - Math.exp(-Math.max(dt, 1e-4) / tau)

/**
 * Integrates `targets` into `state`. Attack is faster than release on every
 * channel: mouths open quickly and relax slowly, and doing the reverse is the
 * single most common reason synthetic lip-sync looks mechanical.
 *
 * The constants are deliberately short. The analyser reports what is playing
 * *now*, so any smoothing here is pure delay against the audio the listener is
 * already hearing.
 */
export function advanceVisemes(state: VisemeState, targets: VisemeTargets, level: number, dt: number): VisemeState {
  const blend = (current: number, target: number, attack: number, release: number) =>
    current + (target - current) * coefficient(dt, target > current ? attack : release)

  state.level = blend(state.level, clamp01(level), 0.025, 0.1)
  state.jawOpen = blend(state.jawOpen, targets.jawOpen, 0.022, 0.075)
  state.lipRound = blend(state.lipRound, targets.lipRound, 0.04, 0.11)
  state.lipWide = blend(state.lipWide, targets.lipWide, 0.036, 0.1)
  state.lipPress = blend(state.lipPress, targets.lipPress, 0.025, 0.06)
  return state
}
