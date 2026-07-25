/**
 * Short derived strokes that sit on the face: eyebrow tufts and the upper lid
 * crease.
 *
 * Drawing an eyebrow as a closed outline is what makes a rendered face read as
 * a colouring book. A real brow is a *patch of hair*, and a real adult eye has
 * a supratarsal crease above the lash line — both are strokes, not borders.
 *
 * Every stroke endpoint is defined as a blend of two landmarks plus a fixed
 * offset, so the strokes are re-evaluated from the *deformed* face each frame:
 * brows rise with the brow rig, creases fold with the blink, at the cost of one
 * lerp per endpoint.
 */

import { LEFT_BROW_OUTLINE, LEFT_EYE_RING, RIGHT_BROW_OUTLINE, RIGHT_EYE_RING } from './canonicalFace.ts'
import { smoothstep } from './femaleHead.ts'
import { hash01, lerp } from './femaleHead.ts'

export type FaceDetail = {
  /** Two landmark indices per endpoint. */
  taps: Int32Array
  /** Blend factor between them, per endpoint. */
  blend: Float32Array
  /** Fixed model-space offset, three floats per endpoint. */
  offsets: Float32Array
  /** Per-endpoint brightness, so strokes fade out at their tips. */
  fade: Float32Array
  endpointCount: number
}

/** Samples a polyline of landmarks at `t ∈ [0,1]`, returning the tap and blend. */
function sampleArc(arc: readonly number[], t: number): [number, number, number] {
  const span = (arc.length - 1) * Math.min(0.9999, Math.max(0, t))
  const first = Math.floor(span)
  return [arc[first], arc[first + 1], span - first]
}

export function buildFaceDetail(): FaceDetail {
  const taps: number[] = []
  const blend: number[] = []
  const offsets: number[] = []
  const fade: number[] = []

  const endpoint = (tap: [number, number, number], offset: [number, number, number], strength: number) => {
    taps.push(tap[0], tap[1])
    blend.push(tap[2])
    offsets.push(offset[0], offset[1], offset[2])
    fade.push(strength)
  }

  // --- Eyebrows -------------------------------------------------------------
  // Each brow outline stores the lower arc then the upper arc, both ordered
  // outer → inner. Tufts are drawn across the gap between them, angled the way
  // brow hair actually grows: steeply upward at the head, flat at the tail.
  const brows = [RIGHT_BROW_OUTLINE, LEFT_BROW_OUTLINE]
  brows.forEach((outline, side) => {
    // Only the lower arc is used as a spine. Spanning the gap to the upper arc
    // made the brow as tall as whatever that gap happened to be — about 1.5
    // units, which reads as a caterpillar sitting high on the forehead.
    const lower = outline.slice(0, outline.length / 2)
    const direction = side === 0 ? -1 : 1

    for (let hair = 0; hair < 48; hair += 1) {
      // Trimmed at both ends: the outermost landmark sits past where a brow
      // actually stops, and running tufts out to it reads as a fringe.
      const t = 0.14 + ((hair + 0.5) / 48) * 0.8
      const jitter = hash01(hair * 3.7 + side * 41)
      // Brows sit on the orbital rim, not halfway up the forehead.
      // `t` runs outer → inner, so the tail of the brow is at t ≈ 0.
      const tail = 1 - t
      const rootT = Math.min(0.995, t + (jitter - 0.5) * 0.05)
      const tipT = Math.min(0.995, Math.max(0, rootT - 0.05 - tail * 0.04))
      // Hair grows steeply at the head of the brow and lies flat at the tail.
      const rise = lerp(0.34, 0.72, jitter) * lerp(0.55, 1, t)

      endpoint(sampleArc(lower, rootT), [direction * 0.05, -0.3, 0.08], 0.45 + 0.55 * smoothstep(0, 0.32, t))
      endpoint(sampleArc(lower, tipT), [direction * 0.13, -0.3 + rise, 0.08], 0.12)
    }
  })

  // --- Eyelashes ------------------------------------------------------------
  // A lid margin drawn as a single line is a wire. Real lashes thicken it and
  // grow longer towards the outer corner, which is most of what gives an adult
  // eye its shape from the front.
  const lidArcs = [RIGHT_EYE_RING, LEFT_EYE_RING]
  lidArcs.forEach((ring, side) => {
    const upperLid = ring.slice(ring.length / 2)
    const direction = side === 0 ? -1 : 1
    for (let lash = 0; lash < 18; lash += 1) {
      const t = 0.12 + (lash / 17) * 0.86
      const length = 0.07 + 0.14 * t * t
      endpoint(sampleArc(upperLid, t), [0, 0, 0.04], 1)
      endpoint(sampleArc(upperLid, t), [
        direction * length * 0.9,
        length * 0.3,
        0.04,
      ], 0.08)
    }
  })

  // --- Upper lid crease -----------------------------------------------------
  // Traced from the upper lid margin and lifted, so it folds down with a blink
  // instead of hovering over a closed eye.
  const eyes = [RIGHT_EYE_RING, LEFT_EYE_RING]
  eyes.forEach((ring, side) => {
    // The second half of each eye ring is the upper lid, inner → outer.
    const upperLid = ring.slice(ring.length / 2)
    const direction = side === 0 ? -1 : 1
    for (let step = 0; step < upperLid.length - 1; step += 1) {
      const strength = Math.sin(((step + 0.5) / (upperLid.length - 1)) * Math.PI) ** 0.5
      endpoint(sampleArc(upperLid, step / (upperLid.length - 1)), [direction * 0.02, 0.46, -0.16], strength * 0.55)
      endpoint(sampleArc(upperLid, (step + 1) / (upperLid.length - 1)), [direction * 0.02, 0.46, -0.16], strength * 0.55)
    }
  })

  return {
    taps: new Int32Array(taps),
    blend: new Float32Array(blend),
    offsets: new Float32Array(offsets),
    fade: new Float32Array(fade),
    endpointCount: blend.length,
  }
}

/** Re-evaluates every stroke against the current deformed landmarks. */
export function evaluateFaceDetail(detail: FaceDetail, positions: Float32Array, out: Float32Array) {
  for (let endpoint = 0; endpoint < detail.endpointCount; endpoint += 1) {
    const a = detail.taps[endpoint * 2] * 3
    const b = detail.taps[endpoint * 2 + 1] * 3
    const t = detail.blend[endpoint]
    for (let axis = 0; axis < 3; axis += 1) {
      out[endpoint * 3 + axis] = lerp(positions[a + axis], positions[b + axis], t) + detail.offsets[endpoint * 3 + axis]
    }
  }
}
