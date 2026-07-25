/**
 * Turns the canonical (androgynous, face-only) landmark model into a complete
 * feminine head.
 *
 * Two things were wrong with the previous hologram, and both are fixed here:
 *
 *  1. The anatomical face was floating *inside* an unrelated egg-shaped surface
 *     of revolution, and hand-drawn eye/nose/mouth splines floated in front of
 *     both. Three mutually inconsistent shapes overlapped, which is exactly why
 *     it read as "uncanny" rather than as a person. Here there is a single
 *     surface: the cranium, the neck and the bust are *grown from the face's own
 *     boundary loop*, so the head is anatomically continuous by construction.
 *
 *  2. The canonical model is a neutral reference face. Reading as a woman comes
 *     from a specific, well-documented set of proportions — a softer mandible, a
 *     shorter and rounder chin, a flatter supraorbital ridge with a higher brow,
 *     a more vertical forehead, a narrower nasal base, fuller lips and higher
 *     malar volume. `feminizeFace` applies exactly those, as smooth weighted
 *     fields rather than as vertex-by-vertex sculpting.
 *
 * All coordinates are the canonical model's own units (roughly millimetres of a
 * reference head: x ±7.7, y -9.4…8.3, z -2.4…7.6). No three.js import, so the
 * whole construction is unit-testable under plain Node.
 */

import type { CanonicalFace } from './canonicalFace.ts'
import { CANONICAL_VERTEX_COUNT, INNER_LIP_RING, LANDMARK, LEFT_EYE_RING, RIGHT_EYE_RING, landmarkCentroid } from './canonicalFace.ts'

export const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value)
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/** Hermite smoothstep that also accepts `edge0 > edge1` for a falling ramp. */
export function smoothstep(edge0: number, edge1: number, x: number) {
  if (edge0 === edge1) return x < edge0 ? 0 : 1
  const t = clamp01((x - edge0) / (edge1 - edge0))
  return t * t * (3 - 2 * t)
}

/** Deterministic hash in [0,1) — hair and micro-motion must not flicker. */
export function hash01(seed: number) {
  const value = Math.sin(seed * 127.1 + 311.7) * 43758.5453
  return value - Math.floor(value)
}

// ---------------------------------------------------------------------------
// Feminisation
// ---------------------------------------------------------------------------

/**
 * Returns a feminised copy of the canonical landmark positions.
 *
 * Each block is one documented sexually-dimorphic trait. They are intentionally
 * modest: overshooting any single one is what produces a caricature.
 */
export function feminizeFace(source: Float32Array): Float32Array {
  const positions = new Float32Array(source)
  const lipCentreY = (source[LANDMARK.upperLipInner * 3 + 1] + source[LANDMARK.lowerLipInner * 3 + 1]) / 2

  for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
    let x = positions[index * 3]
    let y = positions[index * 3 + 1]
    let z = positions[index * 3 + 2]
    const side = x < 0 ? -1 : 1
    const absX = Math.abs(x)

    // 1. Mandible — narrower and less flared than a male jaw.
    const jaw = smoothstep(-0.5, -7, y)
    x *= lerp(1, 0.925, jaw)

    // 2. Gonial angle — the square rear corner of the jaw is the single
    //    strongest masculine cue, so it is pulled in and up into a soft curve.
    const gonial = smoothstep(2.6, 6.4, absX) * smoothstep(-0.8, -4.6, y) * smoothstep(4, -0.5, z)
    x -= side * 0.5 * gonial
    y += 0.62 * gonial

    // 3. Chin — a female lower third is shorter and rounder, not just narrower.
    //    Under-doing the vertical shortening is what leaves the face looking
    //    long and elvish however narrow the jaw gets.
    const chin = smoothstep(-5, -9.4, y)
    y += 1.45 * chin
    z -= 0.3 * chin
    x *= lerp(1, 0.93, chin)

    // 4. Supraorbital ridge — flattened, with the brow line lifted above the
    //    orbital rim instead of sitting on it.
    const brow = smoothstep(2.8, 4.6, y) * smoothstep(7.4, 5.2, y) * smoothstep(1.4, 3.4, z)
    z -= 0.46 * brow
    y += 0.34 * brow

    // 5. Forehead — more vertical and rounder, less backward slope.
    const forehead = smoothstep(4.8, 8.3, y)
    z += 0.6 * forehead
    x *= lerp(1, 0.975, forehead)

    // 6. Nose — narrower alar base and a slightly shallower dorsum.
    const nose = smoothstep(2, 4.4, z) * smoothstep(3.8, 2.4, y) * smoothstep(-3.8, -2.4, y) * smoothstep(3.4, 1.6, absX)
    x *= lerp(1, 0.8, nose)
    z -= 0.38 * nose * smoothstep(1, -2.6, y)

    // 7. Lips — fuller vertically and more projected, with a smooth transition
    //    across the lip line so the vermilion border does not crease.
    const lips = smoothstep(3.8, 1.5, absX) * smoothstep(-6.8, -5.7, y) * smoothstep(-1.9, -3, y)
    y += Math.tanh((y - lipCentreY) * 1.15) * 0.36 * lips
    z += 0.32 * lips

    // 8. Malar volume — higher and fuller cheekbones.
    const malar = smoothstep(2, 4.8, absX) * smoothstep(7.2, 4.6, absX) * smoothstep(-3.6, -0.6, y) * smoothstep(3.8, 1.2, y)
    z += 0.66 * malar
    y += 0.38 * malar

    positions[index * 3] = x
    positions[index * 3 + 1] = y
    positions[index * 3 + 2] = z
  }

  // 9. Palpebral aperture — marginally larger eyes with a lifted outer canthus.
  for (const ring of [RIGHT_EYE_RING, LEFT_EYE_RING]) {
    const [cx, cy, cz] = landmarkCentroid(positions, ring)
    for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
      const dx = positions[index * 3] - cx
      const dy = positions[index * 3 + 1] - cy
      const dz = positions[index * 3 + 2] - cz
      const near = smoothstep(3.6, 1.2, Math.hypot(dx, dy, dz))
      if (near <= 0) continue
      // The canonical model's palpebral fissure is ~6 mm tall, which reads as a
      // squint; a female eye opening is nearer 9–10 mm. The opening is made
      // upwards, not symmetrically — dropping the lower lid by the same amount
      // exposes sclera under the iris and the eye reads as startled.
      const stretch = dy > 0 ? 1.55 : 1.1
      positions[index * 3] = cx + dx * lerp(1, 1.42, near)
      positions[index * 3 + 1] = cy + dy * lerp(1, stretch, near)
      positions[index * 3 + 2] = cz + dz
      // Outer canthus sits a little above the inner one.
      positions[index * 3 + 1] += near * smoothstep(1.4, 3.4, Math.abs(dx)) * 0.26
    }
  }

  return positions
}

// ---------------------------------------------------------------------------
// Head construction
// ---------------------------------------------------------------------------

/**
 * Every generated vertex is bound to one canonical landmark, so when the rig
 * moves the jaw or the eyelids the cranium and neck follow instead of tearing
 * away from the face. Linear blend skinning with a single influence is enough
 * here and costs one subtract-multiply-add per vertex per frame.
 */
export type HeadSkin = {
  parent: Int32Array
  influence: Float32Array
}

export type HeadBuild = {
  basePositions: Float32Array
  indices: Uint32Array
  vertexCount: number
  skin: HeadSkin
  /** Index count of the canonical face triangles, which lead the buffer. */
  faceIndexCount: number
  /** Index range of the oral cavity, drawn with a darker material. */
  cavityIndexStart: number
  cavityIndexCount: number
  /** Eye socket centres and outward normals, for placing the eyeballs. */
  eyes: Array<{ centre: [number, number, number]; forward: [number, number, number]; radius: number }>
  /** Uniform scale that maps model units into the scene's working units. */
  scale: number
}

/**
 * Skull ellipsoid the cranium is swept over, and the single source of truth the
 * hair also builds against.
 *
 * A female skull is widest across the parietals — wider than the cheekbones —
 * so `x` has to exceed the face's own half-width or the crown tapers into an
 * egg. The height matters just as much in the other direction: a cranium that
 * is tall relative to the face is the defining *infant* proportion, and it is
 * what made the earlier head read as a doll rather than as an adult.
 */
export const SKULL_CENTRE: [number, number, number] = [0, 0.95, -1]
export const SKULL_RADII: [number, number, number] = [7.6, 8.4, 9.5]
const CRANIUM_RINGS = 14

/** Maps model units to scene units; the head ends up ~3.6 units tall. */
export const MODEL_SCALE = 0.118

function slerpDirection(from: [number, number, number], to: [number, number, number], t: number): [number, number, number] {
  const raw = from[0] * to[0] + from[1] * to[1] + from[2] * to[2]
  // The face oval points forward and the pole points backward, so the dot
  // product is routinely negative — clamping it to [0,1] would silently fold
  // the whole cranium into a hemisphere.
  const dot = raw < -1 ? -1 : raw > 1 ? 1 : raw
  const angle = Math.acos(dot)
  if (angle < 1e-4) return [from[0], from[1], from[2]]
  const sin = Math.sin(angle)
  const a = Math.sin((1 - t) * angle) / sin
  const b = Math.sin(t * angle) / sin
  return [from[0] * a + to[0] * b, from[1] * a + to[1] * b, from[2] * a + to[2] * b]
}

/**
 * Grows the cranium, the neck and the bust out of the face's boundary loop and
 * returns one continuous, consistently wound head mesh.
 */
export function buildFemaleHead(face: CanonicalFace, facePositions: Float32Array): HeadBuild {
  const positions: number[] = Array.from(facePositions)
  const indices: number[] = Array.from(face.indices)
  const parents: number[] = []
  const influences: number[] = []
  for (let index = 0; index < CANONICAL_VERTEX_COUNT; index += 1) {
    parents.push(index)
    influences.push(1)
  }

  const push = (x: number, y: number, z: number, parent: number, influence: number) => {
    positions.push(x, y, z)
    parents.push(parent)
    influences.push(influence)
    return positions.length / 3 - 1
  }

  // --- Cranium -------------------------------------------------------------
  // Each boundary vertex is swept along the skull ellipsoid towards a single
  // pole behind the head. Because ring 0 *is* the face's own boundary loop, the
  // seam is exact rather than approximate.
  const loop = face.boundary
  const backPole: [number, number, number] = [0, 0, -1]
  const directions: Array<[number, number, number]> = []
  const radii: number[] = []
  for (const vertex of loop) {
    const dx = (facePositions[vertex * 3] - SKULL_CENTRE[0]) / SKULL_RADII[0]
    const dy = (facePositions[vertex * 3 + 1] - SKULL_CENTRE[1]) / SKULL_RADII[1]
    const dz = (facePositions[vertex * 3 + 2] - SKULL_CENTRE[2]) / SKULL_RADII[2]
    const length = Math.hypot(dx, dy, dz) || 1
    directions.push([dx / length, dy / length, dz / length])
    radii.push(length)
  }

  let previousRing = loop.slice()
  for (let ring = 1; ring <= CRANIUM_RINGS; ring += 1) {
    const t = ring / CRANIUM_RINGS
    const eased = smoothstep(0, 1, t)
    const currentRing: number[] = []
    if (ring === CRANIUM_RINGS) {
      // Converge to a single pole so the skull closes cleanly.
      const pole = push(
        SKULL_CENTRE[0],
        SKULL_CENTRE[1],
        SKULL_CENTRE[2] - SKULL_RADII[2],
        loop[0],
        0,
      )
      for (let i = 0; i < previousRing.length; i += 1) {
        indices.push(previousRing[i], previousRing[(i + 1) % previousRing.length], pole)
      }
      break
    }
    for (let i = 0; i < loop.length; i += 1) {
      const direction = slerpDirection(directions[i], backPole, eased)
      const radius = lerp(radii[i], 1, eased)
      currentRing.push(push(
        SKULL_CENTRE[0] + direction[0] * SKULL_RADII[0] * radius,
        SKULL_CENTRE[1] + direction[1] * SKULL_RADII[1] * radius,
        SKULL_CENTRE[2] + direction[2] * SKULL_RADII[2] * radius,
        loop[i],
        1 - eased,
      ))
    }
    for (let i = 0; i < loop.length; i += 1) {
      const next = (i + 1) % loop.length
      indices.push(previousRing[i], previousRing[next], currentRing[i])
      indices.push(previousRing[next], currentRing[next], currentRing[i])
    }
    previousRing = currentRing
  }

  // --- Neck and bust -------------------------------------------------------
  // Static geometry: the neck's top ring starts inside the skull, so it is
  // always hidden behind the jaw and never needs to follow it.
  const neckSegments = 30
  const neckRings: number[][] = []
  const neckLevels = [-5, -8.4, -11.6, -14.2, -16.2, -18, -19.7, -22]
  // Set back behind the chin: a column drawn under the face rather than behind
  // it is what made the previous open-mouth pose show a ledge across the jaw.
  const NECK_AXIS_Z = -2.3
  neckLevels.forEach((level, step) => {
    const t = step / (neckLevels.length - 1)
    const spread = smoothstep(0.42, 1, t)
    const halfWidth = lerp(3.55, 4.25, smoothstep(0, 0.5, t)) + spread * 7.6
    const depth = lerp(3, 3.6, smoothstep(0, 0.5, t)) + spread * 2.4
    const ring: number[] = []
    for (let i = 0; i < neckSegments; i += 1) {
      const angle = i / neckSegments * Math.PI * 2
      // Deltoid slope: the shoulders fall away towards the arms.
      const shoulderDrop = spread * Math.abs(Math.sin(angle)) * 3.4
      ring.push(push(
        Math.sin(angle) * halfWidth,
        level - shoulderDrop,
        Math.cos(angle) * depth + NECK_AXIS_Z,
        -1,
        0,
      ))
    }
    neckRings.push(ring)
  })
  for (let step = 0; step < neckRings.length - 1; step += 1) {
    const top = neckRings[step]
    const bottom = neckRings[step + 1]
    for (let i = 0; i < neckSegments; i += 1) {
      const next = (i + 1) % neckSegments
      indices.push(top[i], top[next], bottom[i])
      indices.push(top[next], bottom[next], bottom[i])
    }
  }
  // Cap the bust so the hologram is a closed volume rather than an open tube.
  const bustRing = neckRings[neckRings.length - 1]
  const bustCentre = push(0, neckLevels[neckLevels.length - 1] - 1.4, NECK_AXIS_Z, -1, 0)
  for (let i = 0; i < neckSegments; i += 1) {
    indices.push(bustRing[i], bustRing[(i + 1) % neckSegments], bustCentre)
  }

  // --- Mouth cavity --------------------------------------------------------
  // A shallow dome behind the lips: without it the open mouth is a hole
  // straight through the head, which instantly breaks the illusion.
  const lipCentre = landmarkCentroid(facePositions, INNER_LIP_RING)
  const cavityIndexStart = indices.length
  const cavityDepth = 2.6
  const cavityBack = push(lipCentre[0], lipCentre[1], lipCentre[2] - cavityDepth, LANDMARK.upperLipInner, 0.35)
  const cavityRing = INNER_LIP_RING.map((vertex) => {
    const x = facePositions[vertex * 3]
    const y = facePositions[vertex * 3 + 1]
    const z = facePositions[vertex * 3 + 2]
    return push(
      lipCentre[0] + (x - lipCentre[0]) * 0.94,
      lipCentre[1] + (y - lipCentre[1]) * 0.94,
      z - 0.7,
      vertex,
      0.9,
    )
  })
  for (let i = 0; i < cavityRing.length; i += 1) {
    const next = (i + 1) % cavityRing.length
    indices.push(INNER_LIP_RING[i], INNER_LIP_RING[next], cavityRing[i])
    indices.push(INNER_LIP_RING[next], cavityRing[next], cavityRing[i])
    indices.push(cavityRing[i], cavityRing[next], cavityBack)
  }

  const vertexCount = positions.length / 3
  const basePositions = new Float32Array(positions)
  orientTriangles(basePositions, indices)

  const eyes = [RIGHT_EYE_RING, LEFT_EYE_RING].map((ring) => {
    const centre = landmarkCentroid(facePositions, ring)

    // Outward normal of the orbit, biased forward: the globe sits behind the
    // aperture and its equator is what shows through the eyelids.
    // Eyes diverge by only a few degrees. Pointing them 47° outwards — which is
    // what scaling the socket's own x gave — pushed each globe sideways and
    // left the medial corner of the socket empty, so the viewer saw straight
    // through the head at the inner canthus.
    const forward = normalise([centre[0] * 0.055, 0.04, 1])
    // A 12 mm globe seated so its cornea is level with the palpebral aperture.
    // Seating it too far forward is what made the previous eyes read as beads
    // stuck onto the face.
    // A 12 mm globe seated so its cornea clears the lid margins without
    // bulging through the skin around the orbit.
    const radius = 1.32
    const seat = 0.98
    return {
      centre: [
        centre[0] - forward[0] * seat,
        centre[1] - forward[1] * seat,
        centre[2] - forward[2] * seat,
      ] as [number, number, number],
      forward,
      radius,
    }
  })

  return {
    basePositions,
    indices: new Uint32Array(indices),
    vertexCount,
    skin: { parent: new Int32Array(parents), influence: new Float32Array(influences) },
    faceIndexCount: face.indices.length,
    cavityIndexStart,
    cavityIndexCount: indices.length - cavityIndexStart,
    eyes,
    scale: MODEL_SCALE,
  }
}

/** Unique undirected edges, so a wireframe overlay can share the position buffer. */
export function uniqueEdges(indices: ArrayLike<number>): Uint32Array {
  const seen = new Set<number>()
  const edges: number[] = []
  for (let i = 0; i < indices.length; i += 3) {
    for (let edge = 0; edge < 3; edge += 1) {
      const a = indices[i + edge]
      const b = indices[i + (edge + 1) % 3]
      const key = a < b ? a * 100000 + b : b * 100000 + a
      if (seen.has(key)) continue
      seen.add(key)
      edges.push(a, b)
    }
  }
  return new Uint32Array(edges)
}

function normalise(v: [number, number, number]): [number, number, number] {
  const length = Math.hypot(v[0], v[1], v[2]) || 1
  return [v[0] / length, v[1] / length, v[2] / length]
}

/**
 * Makes every triangle wind outwards, so lighting works with `FrontSide` and a
 * single set of vertex normals. The head, neck and bust are star-shaped about
 * the vertical head/neck axis rather than about any single point, so each
 * triangle is tested against the axis at *its own* height. That is what lets
 * the procedural cranium, neck and mouth cavity agree with the canonical face
 * without hand-tracking every ring's orientation.
 */
export function orientTriangles(positions: Float32Array, indices: number[]) {
  for (let i = 0; i < indices.length; i += 3) {
    const a = indices[i] * 3
    const b = indices[i + 1] * 3
    const c = indices[i + 2] * 3
    const ux = positions[b] - positions[a]
    const uy = positions[b + 1] - positions[a + 1]
    const uz = positions[b + 2] - positions[a + 2]
    const vx = positions[c] - positions[a]
    const vy = positions[c + 1] - positions[a + 1]
    const vz = positions[c + 2] - positions[a + 2]
    const nx = uy * vz - uz * vy
    const ny = uz * vx - ux * vz
    const nz = ux * vy - uy * vx
    const centroidY = (positions[a + 1] + positions[b + 1] + positions[c + 1]) / 3
    // Clamping the reference to the axis' own extent keeps the test valid on
    // the crown and on the underside of the bust, where "outward" is ±y.
    const referenceY = centroidY > 4 ? 4 : centroidY < -18 ? -18 : centroidY
    const referenceZ = lerp(-0.5, -2.3, smoothstep(0, -14, centroidY))
    const ox = (positions[a] + positions[b] + positions[c]) / 3
    const oy = centroidY - referenceY
    const oz = (positions[a + 2] + positions[b + 2] + positions[c + 2]) / 3 - referenceZ
    if (nx * ox + ny * oy + nz * oz < 0) {
      const swap = indices[i + 1]
      indices[i + 1] = indices[i + 2]
      indices[i + 2] = swap
    }
  }
}

/** Propagates the rig's canonical-vertex deformation to the whole head. */
export function applySkin(base: Float32Array, face: Float32Array, skin: HeadSkin, out: Float32Array) {
  const count = skin.parent.length
  for (let index = 0; index < count; index += 1) {
    if (index < CANONICAL_VERTEX_COUNT) {
      out[index * 3] = face[index * 3]
      out[index * 3 + 1] = face[index * 3 + 1]
      out[index * 3 + 2] = face[index * 3 + 2]
      continue
    }
    const parent = skin.parent[index]
    const influence = skin.influence[index]
    if (parent < 0 || influence === 0) {
      out[index * 3] = base[index * 3]
      out[index * 3 + 1] = base[index * 3 + 1]
      out[index * 3 + 2] = base[index * 3 + 2]
      continue
    }
    out[index * 3] = base[index * 3] + influence * (face[parent * 3] - base[parent * 3])
    out[index * 3 + 1] = base[index * 3 + 1] + influence * (face[parent * 3 + 1] - base[parent * 3 + 1])
    out[index * 3 + 2] = base[index * 3 + 2] + influence * (face[parent * 3 + 2] - base[parent * 3 + 2])
  }
}
