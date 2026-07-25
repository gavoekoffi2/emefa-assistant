/**
 * Procedural hair, generated as luminous strands rather than as a solid shell.
 *
 * Hair is doing real work here. A bare cranium reads as a medical scan no
 * matter how good the face is; a shoulder-length silhouette that frames the
 * cheekbones is what makes a viewer read "woman" before they have consciously
 * looked at any single feature. Strands also suit the medium — they are lines,
 * so they belong to the same visual language as the rest of the hologram
 * instead of fighting it.
 *
 * Every strand hugs the skull to a release point on the hairline, then falls
 * free with a per-strand length, wave and phase so the mass has a layered edge.
 */

import { SKULL_CENTRE, SKULL_RADII, hash01, lerp, smoothstep } from './femaleHead.ts'

/** Segments per strand; 18 is enough for the fall to read as a curve. */
const STRAND_SEGMENTS = 18
/** Fraction of a strand that hugs the scalp before it falls free. */
const SCALP_FRACTION = 0.4

/**
 * Polar angle of the hairline for a given azimuth (0 = facing forward). Fitted
 * to a female hairline: high across the forehead, dropping to just in front of
 * the ears and lower again at the nape.
 */
export function hairlineAngle(azimuth: number) {
  const u = (1 - Math.cos(azimuth)) / 2
  return 0.78 + 2.15 * u - 0.75 * u * u
}

/**
 * How much of a vertex is *face* rather than scalp, in `0…1`.
 *
 * The grid has to stop at the hairline. Running it over the whole cranium is
 * what made the forehead look enormous: with no visual boundary between scalp
 * and face, a viewer reads the entire skull as forehead however low the
 * hairline actually sits.
 */
export function scalpMask(positions: Float32Array): Float32Array {
  const mask = new Float32Array(positions.length / 3)
  for (let vertex = 0; vertex < mask.length; vertex += 1) {
    const dx = positions[vertex * 3] - SKULL_CENTRE[0]
    const dy = positions[vertex * 3 + 1] - SKULL_CENTRE[1]
    const dz = positions[vertex * 3 + 2] - SKULL_CENTRE[2]
    const polar = Math.atan2(Math.hypot(dx / SKULL_RADII[0], dz / SKULL_RADII[2]) * SKULL_RADII[1], dy)
    const hairline = hairlineAngle(Math.atan2(dx, dz))
    mask[vertex] = smoothstep(hairline - 0.07, hairline + 0.07, polar)
  }
  return mask
}

function scalpPoint(polar: number, azimuth: number, swell: number): [number, number, number] {
  // Hair sits close to the skull. An inflated shell turns the silhouette into a
  // bell far wider than the face inside it.
  const shell = 1 + 0.015 + swell
  // The cranial ellipsoid runs ahead of the real forehead and temples, and the
  // gap widens the further down the skull you go — so the set-back grows with
  // the polar angle. Without it the strands nearest the hairline sit in front
  // of the skin and read as hair hanging over the face.
  const setBack = Math.max(0, Math.cos(azimuth)) * (0.7 + 3.4 * smoothstep(0.4, 1.35, polar))
  return [
    SKULL_CENTRE[0] + Math.sin(polar) * Math.sin(azimuth) * SKULL_RADII[0] * shell,
    SKULL_CENTRE[1] + Math.cos(polar) * SKULL_RADII[1] * shell,
    SKULL_CENTRE[2] + Math.sin(polar) * Math.cos(azimuth) * SKULL_RADII[2] * shell - setBack,
  ]
}

export type HairBuild = {
  /** Line-segment pairs, in model units. */
  positions: Float32Array
  /** 0 at the root, 1 at the tip — the shader fades strands out towards the end. */
  fade: Float32Array
  strandCount: number
}

/**
 * @param strandCount lowered on small screens; the silhouette survives it.
 */
export function buildHairStrands(strandCount = 460): HairBuild {
  const positions: number[] = []
  const fade: number[] = []

  for (let strand = 0; strand < strandCount; strand += 1) {
    // Azimuths are spread with a golden-ratio walk so no seam or stripe forms,
    // then nudged away from dead-centre-front to open a natural parting.
    const spread = (strand * 0.6180339887) % 1
    // Offset so the parting falls off-centre, the way hair is actually worn.
    const rootAzimuth = ((spread * 2 - 1) * Math.PI) + 0.34
    const wrapped = Math.atan2(Math.sin(rootAzimuth), Math.cos(rootAzimuth))
    const frontness = Math.max(0, Math.cos(wrapped))
    const side = wrapped < 0 ? -1 : 1

    const hairline = hairlineAngle(wrapped)
    // Capped short of the hairline so no root lands on the forehead itself.
    const rootPolar = hairline * Math.pow(hash01(strand * 3.1 + 0.5), 0.6) * 0.88
    // A wide spread of lengths gives the mass a layered edge instead of a
    // blunt hemline.
    const length = lerp(6.5, 18, hash01(strand * 7.7 + 2.3) ** 0.8) * lerp(0.72, 1, 1 - frontness * 0.55)
    const wave = lerp(0.5, 1.9, hash01(strand * 11.3 + 5.1))
    const phase = hash01(strand * 5.9 + 9.4) * Math.PI * 2
    // Front strands sweep outwards instead of falling across the face.
    const sweep = side * frontness * 1.15

    // Resolved up front rather than captured mid-loop, so the fall always
    // starts exactly where the scalp phase ends whatever the segment count is.
    const releaseAzimuth = wrapped + sweep
    const releasePolar = hairlineAngle(releaseAzimuth)
    const releasePoint = scalpPoint(releasePolar, releaseAzimuth, smoothstep(0.5, 1.9, releasePolar) * 0.05)
    const outward: [number, number, number] = [Math.sin(releaseAzimuth), 0, Math.cos(releaseAzimuth)]
    let previous: [number, number, number] | null = null

    for (let step = 0; step <= STRAND_SEGMENTS; step += 1) {
      const t = step / STRAND_SEGMENTS
      let point: [number, number, number]

      if (t <= SCALP_FRACTION) {
        const local = t / SCALP_FRACTION
        // The azimuth has to lead the polar angle: swinging sideways *before*
        // descending is what keeps a front strand from diving straight down
        // over the forehead on its way to the temple.
        const azimuth = lerp(wrapped, releaseAzimuth, Math.sqrt(local))
        const polar = lerp(rootPolar, releasePolar, local * local)
        // The mass thickens towards the nape, which is where hair volume sits.
        point = scalpPoint(polar, azimuth, smoothstep(0.5, 1.9, polar) * 0.05)
      } else {
        const local = (t - SCALP_FRACTION) / (1 - SCALP_FRACTION)
        const drop = length * local
        // Flare out just below the release, then curl back in at the tip.
        const flare = Math.sin(local * Math.PI) * 0.55 - local * local * 1.5
        const lateral = Math.sin(local * Math.PI * 1.6 + phase) * wave * local
        point = [
          releasePoint[0] + outward[0] * flare + lateral * 0.6 + side * local * 0.7,
          releasePoint[1] - drop,
          // Bias the fall backwards so no strand drifts across the face.
          releasePoint[2] + outward[2] * flare - local * 2.2 - frontness * local * 1.6,
        ]
      }

      if (previous) {
        positions.push(previous[0], previous[1], previous[2], point[0], point[1], point[2])
        fade.push((step - 1) / STRAND_SEGMENTS, t)
      }
      previous = point
    }
  }

  return {
    positions: new Float32Array(positions),
    fade: new Float32Array(fade),
    strandCount,
  }
}
