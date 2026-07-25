/**
 * A compact anatomical rig over the canonical landmarks.
 *
 * The previous hologram animated the mouth by scaling two floating ellipses,
 * which is why it read as a puppet: real speech is a *jaw rotation* plus lip
 * shaping, and it drags the cheeks and the chin with it. Here the mandible
 * rotates about the condyles, the lips purse and spread around the oral
 * commissure, and the eyelids close onto the palpebral line. Every deformation
 * is a smooth weight field computed once from the rest pose, so a frame costs
 * one pass over 468 vertices.
 *
 * No three.js import: the rig is plain array maths and is unit-testable.
 */

import {
  CANONICAL_VERTEX_COUNT,
  LANDMARK,
  LEFT_EYE_RING,
  RIGHT_EYE_RING,
  landmarkCentroid,
} from './canonicalFace.ts'
import { clamp01, lerp, smoothstep } from './femaleHead.ts'

/** Rig inputs, all in 0…1 unless noted. */
export type Expression = {
  /** Mandible rotation. Peaks around 17°, which is a wide spoken vowel. */
  jawOpen: number
  /** Rounded vowels (ou, o) — lips purse forward and inward. */
  lipRound: number
  /** Spread vowels and sibilants (i, é, s) — commissures pull outward. */
  lipWide: number
  /** Bilabial closure (m, b, p) — the lips press onto the lip line. */
  lipPress: number
  smile: number
  browRaise: number
  blinkLeft: number
  blinkRight: number
  /** Lower-lid raise; it accompanies a genuine smile and softens a dead stare. */
  squint: number
}

export const NEUTRAL_EXPRESSION: Expression = {
  jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0,
  smile: 0, browRaise: 0, blinkLeft: 0, blinkRight: 0, squint: 0,
}

export type EyeField = {
  /** Height the lid margins meet at — low in the aperture, as real lids do. */
  closureY: number
  /** Distance the upper and lower margins travel to reach it. */
  travelUpper: number
  travelLower: number
  upper: Float32Array
  lower: Float32Array
}

export type FaceRig = {
  rest: Float32Array
  jaw: Float32Array
  lip: Float32Array
  lipSign: Float32Array
  corner: Float32Array
  cheek: Float32Array
  brow: Float32Array
  eyes: [EyeField, EyeField]
  lipCentreY: number
  /** Mandibular condyle, the real pivot of the jaw. */
  jawPivot: [number, number]
}

// ~11° at full opening. A real mandible also *translates* forward and down as
// the condyle rides the articular eminence; pure rotation about a fixed pivot
// swings the chin far back into the neck, which is exactly what the previous
// wide-vowel pose did.
const JAW_MAX_ANGLE = 0.2
const JAW_SLIDE_Z = 1.65
const JAW_SLIDE_Y = -0.12

/** Precomputes the weight fields the rig needs, from the rest pose. */
export function buildFaceRig(rest: Float32Array): FaceRig {
  const jaw = new Float32Array(CANONICAL_VERTEX_COUNT)
  const lip = new Float32Array(CANONICAL_VERTEX_COUNT)
  const lipSign = new Float32Array(CANONICAL_VERTEX_COUNT)
  const corner = new Float32Array(CANONICAL_VERTEX_COUNT)
  const cheek = new Float32Array(CANONICAL_VERTEX_COUNT)
  const brow = new Float32Array(CANONICAL_VERTEX_COUNT)

  const lipCentreY = (rest[LANDMARK.upperLipInner * 3 + 1] + rest[LANDMARK.lowerLipInner * 3 + 1]) / 2
  const commissure = landmarkCentroid(rest, [LANDMARK.mouthLeftCorner])
  const cornerX = Math.abs(commissure[0])

  for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
    const x = rest[index * 3]
    const y = rest[index * 3 + 1]
    const z = rest[index * 3 + 2]
    const absX = Math.abs(x)

    // The mandible boundary is not a single horizontal line. Across the cheeks
    // it is a broad ramp; between the lips it has to be sharp, because the
    // upper lip belongs to the maxilla and the lower lip to the mandible. A
    // single broad ramp gives them near-identical weights, which is why the
    // mouth previously barely parted however far the jaw rotated.
    const perioral = smoothstep(3.6, 1.4, absX) * smoothstep(1.6, 3.2, z)
      * smoothstep(-7.4, -6.2, y) * smoothstep(-1.4, -2.6, y)
    const boundary = lerp(-2.2, lipCentreY, perioral)
    const halfWidth = lerp(2.5, 0.52, perioral)
    jaw[index] = smoothstep(boundary + halfWidth, boundary - halfWidth, y)

    // Perioral field: the lips plus the immediately surrounding skin.
    lip[index] = smoothstep(4.4, 1.4, absX)
      * smoothstep(-7.2, -5.9, y)
      * smoothstep(-1.6, -2.9, y)
      * smoothstep(1.6, 3.2, z)
    lipSign[index] = Math.tanh((y - lipCentreY) * 1.3)

    // Commissures: strongest at the corners, fading towards the midline.
    corner[index] = lip[index] * smoothstep(cornerX * 0.42, cornerX, absX)

    cheek[index] = smoothstep(1.8, 4.6, absX)
      * smoothstep(7.2, 4.4, absX)
      * smoothstep(-4.4, -1.4, y)
      * smoothstep(3.6, 0.8, y)

    brow[index] = smoothstep(2.9, 4.4, y) * smoothstep(7.6, 5.4, y) * smoothstep(1.2, 3.2, z)
  }

  const eyes = [RIGHT_EYE_RING, LEFT_EYE_RING].map((ring) => {
    const [cx, cy] = landmarkCentroid(rest, ring)
    // Scale the lid field to the aperture this model actually has. A fixed
    // constant here is what made a "blink" move the lid margin by a third of
    // the way and leave the eye visibly open.
    let halfWidth = 0.001
    let halfHeight = 0.001
    let upperMarginY = -Infinity
    let lowerMarginY = Infinity
    for (const vertex of ring) {
      const y = rest[vertex * 3 + 1]
      halfWidth = Math.max(halfWidth, Math.abs(rest[vertex * 3] - cx))
      halfHeight = Math.max(halfHeight, Math.abs(y - cy))
      upperMarginY = Math.max(upperMarginY, y)
      lowerMarginY = Math.min(lowerMarginY, y)
    }
    // Lids meet just above the lower margin, not at the middle of the eye.
    const closureY = lowerMarginY + halfHeight * 0.15

    const upper = new Float32Array(CANONICAL_VERTEX_COUNT)
    const lower = new Float32Array(CANONICAL_VERTEX_COUNT)
    for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
      const dx = rest[index * 3] - cx
      const dy = rest[index * 3 + 1] - cy
      // Horizontal falloff keeps the temple and the bridge of the nose out of
      // the blink; vertical falloff lets the skin above the margin fold with
      // the lid instead of collapsing onto the closure line with it.
      const lateral = smoothstep(halfWidth * 1.9, halfWidth * 0.7, Math.abs(dx))
      if (lateral <= 0) continue
      const rise = smoothstep(0, halfHeight * 0.6, dy) * smoothstep(halfHeight * 2.4, halfHeight, dy)
      const fall = smoothstep(0, halfHeight * 0.6, -dy) * smoothstep(halfHeight * 2, halfHeight, -dy)
      upper[index] = lateral * rise
      lower[index] = lateral * fall
    }
    return {
      closureY,
      travelUpper: upperMarginY - closureY,
      travelLower: (closureY - lowerMarginY) * 0.25,
      upper,
      lower,
    }
  }) as [EyeField, EyeField]

  return {
    rest: new Float32Array(rest),
    jaw, lip, lipSign, corner, cheek, brow, eyes,
    lipCentreY,
    // Condyle: just in front of the ear canal, level with the orbital floor.
    jawPivot: [1, -1.6],
  }
}

/**
 * Writes the deformed canonical landmarks for `expression` into `out`.
 * `out` may not alias `rig.rest`.
 */
export function applyExpression(rig: FaceRig, expression: Expression, out: Float32Array) {
  const { rest } = rig
  const jawAngle = expression.jawOpen * JAW_MAX_ANGLE
  const cos = Math.cos(jawAngle)
  const sin = Math.sin(jawAngle)
  const [pivotY, pivotZ] = rig.jawPivot

  for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
    let x = rest[index * 3]
    let y = rest[index * 3 + 1]
    let z = rest[index * 3 + 2]
    const side = x < 0 ? -1 : 1

    // --- Mandible ----------------------------------------------------------
    const jawWeight = rig.jaw[index]
    if (jawWeight > 0 && jawAngle !== 0) {
      const dy = y - pivotY
      const dz = z - pivotZ
      const rotatedY = pivotY + dy * cos - dz * sin + JAW_SLIDE_Y * expression.jawOpen
      const rotatedZ = pivotZ + dy * sin + dz * cos + JAW_SLIDE_Z * expression.jawOpen
      y = lerp(y, rotatedY, jawWeight)
      z = lerp(z, rotatedZ, jawWeight)
      // The lower face narrows very slightly as the jaw drops, as real skin does.
      x *= lerp(1, 0.985, jawWeight * expression.jawOpen)
    }

    // --- Lips --------------------------------------------------------------
    const lipWeight = rig.lip[index]
    if (lipWeight > 0) {
      const cornerWeight = rig.corner[index]
      // Purse: commissures in, vermilion forward.
      x -= side * 1.05 * cornerWeight * expression.lipRound
      x -= side * 0.22 * (lipWeight - cornerWeight) * expression.lipRound
      z += 0.72 * lipWeight * expression.lipRound
      y -= rig.lipSign[index] * 0.16 * lipWeight * expression.lipRound

      // Spread: commissures out and slightly back, lips thin.
      x += side * 0.92 * cornerWeight * expression.lipWide
      z -= 0.24 * lipWeight * expression.lipWide
      y -= rig.lipSign[index] * 0.14 * lipWeight * expression.lipWide

      // Bilabial closure pulls both lips onto the lip line.
      y = lerp(y, rig.lipCentreY + rig.lipSign[index] * 0.18, lipWeight * expression.lipPress * 0.85)

      // Smile: corners up and out, upper lip thins.
      x += side * 0.62 * cornerWeight * expression.smile
      y += 0.78 * cornerWeight * expression.smile
    }

    // --- Cheeks ------------------------------------------------------------
    const cheekWeight = rig.cheek[index]
    if (cheekWeight > 0) {
      y += 0.5 * cheekWeight * expression.smile
      z += 0.34 * cheekWeight * expression.smile
    }

    // --- Brows -------------------------------------------------------------
    const browWeight = rig.brow[index]
    if (browWeight > 0) {
      y += 0.62 * browWeight * expression.browRaise
    }

    // --- Eyelids -----------------------------------------------------------
    const blink = [expression.blinkRight, expression.blinkLeft]
    for (let eye = 0; eye < 2; eye += 1) {
      const field = rig.eyes[eye]
      const upper = field.upper[index]
      const lower = field.lower[index]
      if (upper <= 0 && lower <= 0) continue
      const close = clamp01(blink[eye])
      // Translating the lid by a weighted travel — rather than lerping every
      // vertex towards one absolute line — is what lets the skin above the
      // margin fold with the lid instead of collapsing into the socket.
      if (upper > 0) {
        y -= upper * close * field.travelUpper
        // A closing lid also rolls forward over the globe.
        z -= upper * close * 0.22
        y -= upper * expression.squint * 0.34
      }
      if (lower > 0) {
        y += lower * close * field.travelLower
        y += lower * (expression.squint + expression.smile * 0.55) * 0.42
      }
    }

    out[index * 3] = x
    out[index * 3 + 1] = y
    out[index * 3 + 2] = z
  }
}

/**
 * Vertical gap between the inner lips, in model units. Positive and growing as
 * the mouth opens; used to fade the oral cavity in only when it is visible.
 */
export function mouthAperture(positions: Float32Array) {
  return positions[LANDMARK.upperLipInner * 3 + 1] - positions[LANDMARK.lowerLipInner * 3 + 1]
}
