/**
 * Parsing and landmark topology for the bundled MediaPipe canonical face model
 * (468 landmarks, Apache-2.0). See `public/models/README.md` for provenance.
 *
 * three's `OBJLoader` returns a *non-indexed* geometry, which destroys the
 * landmark numbering the whole facial rig depends on. So the model is parsed
 * here instead: every vertex keeps its canonical index, which is what lets us
 * address the eyelids, the lips and the jaw by name rather than by guessing at
 * coordinates.
 *
 * This module is deliberately free of any three.js import so the geometry can
 * be unit-tested under plain Node.
 */

/** Landmark indices verified against the bundled model's coordinates. */
export const LANDMARK = {
  chin: 152,
  noseTip: 4,
  noseBase: 1,
  foreheadTop: 10,
  rightEyeOuter: 33,
  rightEyeInner: 133,
  leftEyeOuter: 263,
  leftEyeInner: 362,
  upperLipOuter: 0,
  lowerLipOuter: 17,
  upperLipInner: 13,
  lowerLipInner: 14,
  mouthRightCorner: 61,
  mouthLeftCorner: 291,
  rightTemple: 234,
  leftTemple: 454,
} as const

/**
 * Eyelid contours. The canonical model fills each contour with a flat patch of
 * triangles; removing that patch turns a painted-on eye into a real socket that
 * an eyeball can sit behind. That single change is most of the difference
 * between "mask" and "face".
 */
export const RIGHT_EYE_RING = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
export const LEFT_EYE_RING = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466]

/** Inner lip contour — its patch is removed so the mouth actually opens. */
export const INNER_LIP_RING = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
export const OUTER_LIP_RING = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]

/**
 * MediaPipe stores each brow as two arcs, both ordered outer → inner: the lower
 * brow line first, then the upper. Walking the lower arc outward-to-inward and
 * the upper one back gives a single closed outline that can be drawn as one
 * loop.
 */
export const RIGHT_BROW_OUTLINE = [46, 53, 52, 65, 55, 107, 66, 105, 63, 70]
export const LEFT_BROW_OUTLINE = [276, 283, 282, 295, 285, 336, 296, 334, 293, 300]

/**
 * Contours that have to be drawn as explicit lines rather than left to shading:
 * the lash line, the brows and the vermilion border are what a viewer actually
 * uses to locate a face, and an additive surface renders none of them on its
 * own. They index the shared vertex buffer, so they blink and speak for free.
 */
export const FEATURE_LOOPS: readonly (readonly number[])[] = [
  RIGHT_EYE_RING,
  LEFT_EYE_RING,
  RIGHT_BROW_OUTLINE,
  LEFT_BROW_OUTLINE,
  OUTER_LIP_RING,
  INNER_LIP_RING,
]

/** Closed loops of landmark indices flattened into line-segment index pairs. */
export function loopEdges(loops: readonly (readonly number[])[]): Uint32Array {
  const edges: number[] = []
  for (const loop of loops) {
    for (let i = 0; i < loop.length; i += 1) edges.push(loop[i], loop[(i + 1) % loop.length])
  }
  return new Uint32Array(edges)
}

export const CANONICAL_VERTEX_COUNT = 468

export type CanonicalFace = {
  /** Flat xyz triplets, one per canonical landmark, in the model's own units. */
  positions: Float32Array
  /** Skin triangles with the eye and inner-mouth patches removed. */
  indices: Uint32Array
  /** The ordered face-oval boundary loop of the *complete* model. */
  boundary: number[]
}

function isPatchTriangle(a: number, b: number, c: number, ring: readonly number[]) {
  return ring.includes(a) && ring.includes(b) && ring.includes(c)
}

/**
 * Walks the half-edge counts of a triangle soup and returns every open boundary
 * loop, longest first. The canonical model has exactly one: the face oval that
 * the procedural cranium is grown from.
 */
export function findBoundaryLoops(indices: ArrayLike<number>): number[][] {
  const useCount = new Map<number, number>()
  const key = (a: number, b: number) => (a < b ? a * 100000 + b : b * 100000 + a)
  for (let i = 0; i < indices.length; i += 3) {
    for (let edge = 0; edge < 3; edge += 1) {
      const a = indices[i + edge]
      const b = indices[i + (edge + 1) % 3]
      const id = key(a, b)
      useCount.set(id, (useCount.get(id) ?? 0) + 1)
    }
  }

  const neighbours = new Map<number, number[]>()
  for (const [id, count] of useCount) {
    if (count !== 1) continue
    const a = Math.floor(id / 100000)
    const b = id % 100000
    if (!neighbours.has(a)) neighbours.set(a, [])
    if (!neighbours.has(b)) neighbours.set(b, [])
    neighbours.get(a)!.push(b)
    neighbours.get(b)!.push(a)
  }

  const visited = new Set<number>()
  const loops: number[][] = []
  for (const start of neighbours.keys()) {
    if (visited.has(start)) continue
    const loop = [start]
    visited.add(start)
    let current = start
    let previous = -1
    for (;;) {
      const next = neighbours.get(current)!.find((candidate) => candidate !== previous && !visited.has(candidate))
      if (next === undefined) break
      loop.push(next)
      visited.add(next)
      previous = current
      current = next
    }
    loops.push(loop)
  }
  return loops.sort((a, b) => b.length - a.length)
}

/** Parses the canonical `.obj` and opens the eye sockets and the mouth. */
export function parseCanonicalFaceObj(text: string): CanonicalFace {
  const coordinates: number[] = []
  const triangles: number[] = []

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()
    if (line.startsWith('v ')) {
      const parts = line.split(/\s+/)
      coordinates.push(Number(parts[1]), Number(parts[2]), Number(parts[3]))
    } else if (line.startsWith('f ')) {
      const corners = line.split(/\s+/).slice(1).map((token) => Number.parseInt(token.split('/')[0], 10) - 1)
      // Fan-triangulate so the parser survives a quad-based re-export.
      for (let corner = 2; corner < corners.length; corner += 1) {
        triangles.push(corners[0], corners[corner - 1], corners[corner])
      }
    }
  }

  if (coordinates.length !== CANONICAL_VERTEX_COUNT * 3) {
    throw new Error(`Modèle facial invalide : ${coordinates.length / 3} sommets au lieu de ${CANONICAL_VERTEX_COUNT}.`)
  }

  // The oval must be read from the intact model: carving the sockets first
  // would make the eyelids look like additional boundaries.
  const boundary = findBoundaryLoops(triangles)[0] ?? []

  const skin: number[] = []
  for (let i = 0; i < triangles.length; i += 3) {
    const [a, b, c] = [triangles[i], triangles[i + 1], triangles[i + 2]]
    if (isPatchTriangle(a, b, c, RIGHT_EYE_RING)) continue
    if (isPatchTriangle(a, b, c, LEFT_EYE_RING)) continue
    if (isPatchTriangle(a, b, c, INNER_LIP_RING)) continue
    skin.push(a, b, c)
  }

  return {
    positions: new Float32Array(coordinates),
    indices: new Uint32Array(skin),
    boundary,
  }
}

/** Mean position of a set of landmarks, as a plain triplet. */
export function landmarkCentroid(positions: ArrayLike<number>, ring: readonly number[]): [number, number, number] {
  let x = 0
  let y = 0
  let z = 0
  for (const index of ring) {
    x += positions[index * 3]
    y += positions[index * 3 + 1]
    z += positions[index * 3 + 2]
  }
  return [x / ring.length, y / ring.length, z / ring.length]
}
