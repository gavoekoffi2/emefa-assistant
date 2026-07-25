/**
 * Braided hair: cornrows over the scalp gathering at the crown, plus a few
 * loose braids falling in front of the ears.
 *
 * Loose strands falling from a hairline gave a flat curtain that read as a wig.
 * Braids read as a *style* — they have direction, they follow the skull, and
 * they carry the silhouette. They also suit the medium: a braid is three lines
 * twisting around a spine, so it belongs to the same visual language as the
 * grid instead of fighting it.
 *
 * The trick that makes the cornrow paths come out right is the coordinate
 * frame. Parametrising the scalp about the usual vertical axis makes hair run
 * around the head like latitude lines. Cornrows run front-to-back over the
 * crown, which is exactly what a *meridian* is if you put the poles at the
 * ears — so the whole thing is parametrised about the ear-to-ear axis instead.
 */

import { SKULL_CENTRE, SKULL_RADII, hash01, lerp, smoothstep } from './femaleHead.ts'
import { hairlineAngle } from './hair.ts'

export type BraidBuild = {
  /** Line-segment pairs, in model units. */
  positions: Float32Array
  /** 0 at the root, 1 at the tip. */
  fade: Float32Array
}

/** Sub-strands per braid. Three is what a braid is. */
const PLAITS = 3
const SPINE_STEPS = 34

const CLEARANCE_AZIMUTH = 48
const CLEARANCE_ELEVATION = 24

/**
 * How far the head reaches in each direction, in units of the skull ellipsoid.
 *
 * Sizing the hair shell against the ellipsoid is not enough: the cranium is
 * *swept from the face's boundary loop*, so it runs about 1.1x the ellipsoid
 * over the front of the scalp and tapers to 1.0 at the back. A constant shell
 * therefore buries part of the hairstyle in the skull, where the depth prepass
 * culls it — which is invisible in the geometry and only shows up on screen.
 * Braid points are projected out past this instead.
 */
export type HeadClearance = (unit: readonly [number, number, number]) => number

export function buildHeadClearance(positions: Float32Array, vertexCount: number): HeadClearance {
  const grid = new Float32Array(CLEARANCE_AZIMUTH * CLEARANCE_ELEVATION)
  const cell = (unit: readonly [number, number, number]) => {
    const azimuth = Math.floor(
      ((Math.atan2(unit[0], unit[2]) + Math.PI) / (Math.PI * 2)) * CLEARANCE_AZIMUTH,
    ) % CLEARANCE_AZIMUTH
    const elevation = Math.min(
      CLEARANCE_ELEVATION - 1,
      Math.floor((Math.acos(Math.max(-1, Math.min(1, unit[1]))) / Math.PI) * CLEARANCE_ELEVATION),
    )
    return elevation * CLEARANCE_AZIMUTH + azimuth
  }

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    // Head only. Including the neck and bust would record radii of nearly 3x
    // the skull in the downward directions, and every falling braid would be
    // flung out to meet them.
    if (positions[vertex * 3 + 1] < -1) continue
    const d: [number, number, number] = [
      (positions[vertex * 3] - SKULL_CENTRE[0]) / SKULL_RADII[0],
      (positions[vertex * 3 + 1] - SKULL_CENTRE[1]) / SKULL_RADII[1],
      (positions[vertex * 3 + 2] - SKULL_CENTRE[2]) / SKULL_RADII[2],
    ]
    const radius = Math.hypot(d[0], d[1], d[2])
    if (radius < 1e-4) continue
    const index = cell([d[0] / radius, d[1] / radius, d[2] / radius])
    if (radius > grid[index]) grid[index] = radius
  }

  // Dilate once: an empty cell between two full ones would otherwise let a
  // braid dip straight through the surface.
  const dilated = Float32Array.from(grid)
  for (let elevation = 0; elevation < CLEARANCE_ELEVATION; elevation += 1) {
    for (let azimuth = 0; azimuth < CLEARANCE_AZIMUTH; azimuth += 1) {
      let best = 0
      for (let de = -1; de <= 1; de += 1) {
        const e = elevation + de
        if (e < 0 || e >= CLEARANCE_ELEVATION) continue
        for (let da = -1; da <= 1; da += 1) {
          const a = (azimuth + da + CLEARANCE_AZIMUTH) % CLEARANCE_AZIMUTH
          best = Math.max(best, grid[e * CLEARANCE_AZIMUTH + a])
        }
      }
      dilated[elevation * CLEARANCE_AZIMUTH + azimuth] = best
    }
  }

  return (unit) => dilated[cell(unit)]
}

/**
 * A point on the scalp shell, in the ear-axis frame.
 *
 * @param beta  angle from the +x ear axis; π/2 is the row over the midline.
 * @param gamma sweep front (0) → crown (π/2) → nape (π).
 */
function scalpPoint(
  beta: number,
  gamma: number,
  swell: number,
  clearance: HeadClearance,
): [number, number, number] {
  const direction: [number, number, number] = [
    Math.cos(beta),
    Math.sin(beta) * Math.sin(gamma),
    Math.sin(beta) * Math.cos(gamma),
  ]
  const shell = 1.04 + swell
  // The cranial ellipsoid runs ahead of the real forehead, so front-facing
  // points are pulled back or the braids sit off the brow.
  const setBack = Math.max(0, direction[2]) * 1.7
  return pushOutside([
    SKULL_CENTRE[0] + direction[0] * SKULL_RADII[0] * shell,
    SKULL_CENTRE[1] + direction[1] * SKULL_RADII[1] * shell,
    SKULL_CENTRE[2] + direction[2] * SKULL_RADII[2] * shell - setBack,
  ], clearance, swell)
}

/**
 * Lifts a point out past the head surface in its own direction.
 *
 * Applied to plait points as well as to spine points: a plait is offset from
 * its spine by up to its own thickness, so a spine that just clears the skull
 * still leaves the inward third of the braid buried.
 *
 * Below the jaw there is no scalp to clear — and the clearance field there
 * describes the bust — so points that low are left alone.
 */
function pushOutside(
  point: [number, number, number],
  clearance: HeadClearance,
  margin: number,
): [number, number, number] {
  if (point[1] < 2) return point
  const d: [number, number, number] = [
    (point[0] - SKULL_CENTRE[0]) / SKULL_RADII[0],
    (point[1] - SKULL_CENTRE[1]) / SKULL_RADII[1],
    (point[2] - SKULL_CENTRE[2]) / SKULL_RADII[2],
  ]
  const radius = Math.hypot(d[0], d[1], d[2]) || 1
  const unit: [number, number, number] = [d[0] / radius, d[1] / radius, d[2] / radius]
  const required = clearance(unit) * 1.04 + margin
  if (radius >= required) return point
  return [
    SKULL_CENTRE[0] + unit[0] * SKULL_RADII[0] * required,
    SKULL_CENTRE[1] + unit[1] * SKULL_RADII[1] * required,
    SKULL_CENTRE[2] + unit[2] * SKULL_RADII[2] * required,
  ]
}

/** Where a row at `beta` crosses the hairline, found once per row. */
function hairlineGamma(beta: number) {
  for (let step = 0; step <= 40; step += 1) {
    const gamma = (step / 40) * (Math.PI / 2)
    const direction: [number, number, number] = [
      Math.cos(beta),
      Math.sin(beta) * Math.sin(gamma),
      Math.sin(beta) * Math.cos(gamma),
    ]
    const polar = Math.atan2(Math.hypot(direction[0], direction[2]), direction[1])
    if (polar <= hairlineAngle(Math.atan2(direction[0], direction[2]))) return gamma
  }
  return Math.PI / 2
}

function normalise(v: [number, number, number]): [number, number, number] {
  const length = Math.hypot(v[0], v[1], v[2]) || 1
  return [v[0] / length, v[1] / length, v[2] / length]
}

function cross(a: [number, number, number], b: [number, number, number]): [number, number, number] {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

export function buildBraids(clearance: HeadClearance, rowCount = 17): BraidBuild {
  const positions: number[] = []
  const fade: number[] = []

  const emitBraid = (
    spine: Array<[number, number, number]>,
    thickness: number,
    twist: number,
    seed: number,
    clearance: HeadClearance,
  ) => {
    // Rotation-minimising-ish frame: the scalp normal is a good enough "up" for
    // a braid, and it keeps the plaits from spinning as the spine turns.
    const previousPlaits: Array<[number, number, number] | null> = Array.from({ length: PLAITS }, () => null)

    for (let step = 0; step < spine.length; step += 1) {
      const t = step / (spine.length - 1)
      const here = spine[step]
      const next = spine[Math.min(spine.length - 1, step + 1)]
      const back = spine[Math.max(0, step - 1)]
      const tangent = normalise([next[0] - back[0], next[1] - back[1], next[2] - back[2]])
      const outward = normalise([
        (here[0] - SKULL_CENTRE[0]) / SKULL_RADII[0],
        (here[1] - SKULL_CENTRE[1]) / SKULL_RADII[1],
        (here[2] - SKULL_CENTRE[2]) / SKULL_RADII[2],
      ])
      const binormal = normalise(cross(tangent, outward))
      const normal = normalise(cross(binormal, tangent))
      // Braids taper towards the tip, the way a plait actually does.
      const radius = thickness * lerp(1, 0.35, t * t)

      for (let plait = 0; plait < PLAITS; plait += 1) {
        const angle = twist * t + (plait / PLAITS) * Math.PI * 2 + seed
        const point = pushOutside([
          here[0] + (Math.cos(angle) * normal[0] + Math.sin(angle) * binormal[0]) * radius,
          here[1] + (Math.cos(angle) * normal[1] + Math.sin(angle) * binormal[1]) * radius,
          here[2] + (Math.cos(angle) * normal[2] + Math.sin(angle) * binormal[2]) * radius,
        ], clearance, 0.02)
        const previous = previousPlaits[plait]
        if (previous) {
          positions.push(previous[0], previous[1], previous[2], point[0], point[1], point[2])
          fade.push((step - 1) / (spine.length - 1), t)
        }
        previousPlaits[plait] = point
      }
    }
  }

  // --- Cornrows -------------------------------------------------------------
  for (let row = 0; row < rowCount; row += 1) {
    // Rows are spread from ear to ear, avoiding the poles where they would
    // pile up on top of each other.
    const beta = lerp(0.46, Math.PI - 0.46, (row + 0.5) / rowCount)
    const jitter = hash01(row * 7.3 + 1.7)
    const startGamma = hairlineGamma(beta) + 0.02
    // Rows run back over the crown and stop short of the nape, where the
    // gathered mass begins.
    const endGamma = lerp(2.05, 2.35, jitter)

    const spine: Array<[number, number, number]> = []
    for (let step = 0; step <= SPINE_STEPS; step += 1) {
      const t = step / SPINE_STEPS
      const gamma = lerp(startGamma, endGamma, t)
      // The braided mass stands proud of the skull over the crown — that
      // volume is what makes an updo read as hair rather than as a skullcap.
      const swell = smoothstep(0.75, 1.7, gamma) * 0.07 + smoothstep(2.6, 1.7, gamma) * 0.03
      spine.push(scalpPoint(beta, gamma, swell, clearance))
    }

    // The tail drops from the nape and curls under, gathering into a low mass
    // rather than hanging straight.
    const last = spine[spine.length - 1]
    const tailLength = lerp(3.4, 6.2, hash01(row * 3.9 + 5.1))
    for (let step = 1; step <= 8; step += 1) {
      const t = step / 8
      spine.push([
        last[0] * lerp(1, 0.82, t),
        last[1] - tailLength * t,
        last[2] + Math.sin(t * Math.PI) * 1.6 - t * 0.8,
      ])
    }

    emitBraid(spine, lerp(0.42, 0.58, jitter), lerp(7, 10, jitter), jitter * 6.28, clearance)
  }

  // --- Loose braids in front of the ears ------------------------------------
  // Two on each side, framing the face — the detail that turns an updo into a
  // hairstyle rather than a helmet.
  for (let loose = 0; loose < 4; loose += 1) {
    const side = loose < 2 ? -1 : 1
    const jitter = hash01(loose * 11.7 + 3.3)
    const beta = side < 0 ? lerp(0.5, 0.72, jitter) : Math.PI - lerp(0.5, 0.72, jitter)
    const start = scalpPoint(beta, hairlineGamma(beta) + 0.12, 0.05, clearance)

    const spine: Array<[number, number, number]> = [start]
    const length = lerp(9, 14, jitter)
    for (let step = 1; step <= 16; step += 1) {
      const t = step / 16
      spine.push([
        start[0] + side * (0.5 + Math.sin(t * 2.4) * 0.5) * t,
        start[1] - length * t,
        start[2] - t * 1.4 - Math.sin(t * Math.PI) * 0.6,
      ])
    }
    emitBraid(spine, lerp(0.28, 0.4, jitter), lerp(9, 13, jitter), jitter * 6.28, clearance)
  }

  return { positions: new Float32Array(positions), fade: new Float32Array(fade) }
}
