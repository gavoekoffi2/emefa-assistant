/**
 * Drives the facial rig from the assistant's own output audio.
 *
 * The previous version took a spectral centroid over the *entire* analyser
 * output. Speech energy lives below roughly 4 kHz, so on a 24 kHz analyser that
 * centroid was dominated by the noise floor and barely moved — which is why the
 * mouth mostly flapped with volume. Here the spectrum is reduced to four
 * speech-relevant bands and the classic articulatory contrasts are read off
 * them:
 *
 *   F1 (≈150–600 Hz)   how open the jaw is
 *   F2 low (≈0.6–1.2k) back/rounded vowels — "ou", "o"
 *   F2 high (≈1.2–2.8k) front/spread vowels — "i", "é"
 *   sibilance (≈4–12k) "s", "ch", "f"
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

/** Band edges as a fraction of the analyser's Nyquist range. */
const BANDS: ReadonlyArray<readonly [number, number]> = [
  [0.006, 0.025],
  [0.025, 0.05],
  [0.05, 0.115],
  [0.17, 0.5],
]

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value)

/** Sums normalised energy in each speech band. */
export function bandEnergies(spectrum: ArrayLike<number>): [number, number, number, number] {
  const length = spectrum.length
  const energies: [number, number, number, number] = [0, 0, 0, 0]
  if (length === 0) return energies
  for (let band = 0; band < BANDS.length; band += 1) {
    const [low, high] = BANDS[band]
    const from = Math.max(1, Math.floor(low * length))
    const to = Math.min(length, Math.max(from + 1, Math.ceil(high * length)))
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
  const jawOpen = clamp01((openness * 0.78 + loud * 0.55) * clamp01(loud * 4.5))

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
 */
export function advanceVisemes(state: VisemeState, targets: VisemeTargets, level: number, dt: number): VisemeState {
  const blend = (current: number, target: number, attack: number, release: number) =>
    current + (target - current) * coefficient(dt, target > current ? attack : release)

  state.level = blend(state.level, clamp01(level), 0.03, 0.11)
  state.jawOpen = blend(state.jawOpen, targets.jawOpen, 0.035, 0.09)
  state.lipRound = blend(state.lipRound, targets.lipRound, 0.055, 0.13)
  state.lipWide = blend(state.lipWide, targets.lipWide, 0.05, 0.12)
  state.lipPress = blend(state.lipPress, targets.lipPress, 0.03, 0.07)
  return state
}
