/**
 * The wireframe grid the hologram is actually made of.
 *
 * EMEFA's face is drawn as a mesh of lines — horizontal slices and vertical
 * meridians crossing into a grid that wraps the head. That is the identity of
 * the interface and it is deliberately kept. What was wrong before was not the
 * lines but what they were wrapped around: fixed latitude rings on a surface of
 * revolution describe an egg, not a face, and they never moved when the face
 * did.
 *
 * Here the grid is cut from the real anatomical head. Each line is solved once
 * against the rest pose and stored as a list of edge crossings — a pair of
 * vertex indices and the position along that edge. A frame then only has to
 * re-interpolate those crossings from the deformed vertices, so the grid stays
 * welded to the skin while the jaw drops and the eyelids close, at a cost
 * proportional to the number of visible segments rather than to the mesh.
 */

export type IsoLinePlan = {
  /** Four vertex indices per segment: (a0,b0) and (a1,b1). */
  edges: Uint32Array
  /** Two interpolation factors per segment. */
  factors: Float32Array
  segmentCount: number
}

/**
 * Cuts `levels` iso-lines out of a mesh, given a scalar per vertex.
 *
 * @param wrapped set for an angular field, where a triangle straddling ±π is a
 *                seam artefact rather than a real crossing.
 */
export function planIsoLines(
  indices: ArrayLike<number>,
  scalars: Float32Array,
  levels: readonly number[],
  wrapped = false,
): IsoLinePlan {
  const edges: number[] = []
  const factors: number[] = []

  for (let triangle = 0; triangle < indices.length; triangle += 3) {
    const corners = [indices[triangle], indices[triangle + 1], indices[triangle + 2]]
    const values = [scalars[corners[0]], scalars[corners[1]], scalars[corners[2]]]

    if (wrapped) {
      const span = Math.max(...values) - Math.min(...values)
      if (span > Math.PI) continue
    }

    const low = Math.min(...values)
    const high = Math.max(...values)

    for (const level of levels) {
      if (level < low || level > high) continue
      const crossingA: number[] = []
      const crossingB: number[] = []
      const crossingT: number[] = []

      for (let edge = 0; edge < 3; edge += 1) {
        const a = corners[edge]
        const b = corners[(edge + 1) % 3]
        const va = values[edge]
        const vb = values[(edge + 1) % 3]
        if ((va < level) === (vb < level)) continue
        crossingA.push(a)
        crossingB.push(b)
        crossingT.push((level - va) / (vb - va))
      }

      // A plane meets a triangle in either zero or two edges; anything else is
      // a numerical edge case and is safely dropped.
      if (crossingA.length !== 2) continue
      edges.push(crossingA[0], crossingB[0], crossingA[1], crossingB[1])
      factors.push(crossingT[0], crossingT[1])
    }
  }

  return {
    edges: new Uint32Array(edges),
    factors: new Float32Array(factors),
    segmentCount: factors.length / 2,
  }
}

/** Evenly spaced levels, offset by half a step so none lands on a vertex. */
export function evenLevels(from: number, to: number, count: number): number[] {
  return Array.from({ length: count }, (_, index) => from + (index + 0.5) / count * (to - from))
}

/** Height of each vertex — the scalar field the horizontal slices cut along. */
export function heightField(positions: Float32Array): Float32Array {
  const field = new Float32Array(positions.length / 3)
  for (let vertex = 0; vertex < field.length; vertex += 1) field[vertex] = positions[vertex * 3 + 1]
  return field
}

/**
 * Azimuth about the head's own axis — the field the vertical meridians cut
 * along. Slicing on plain `x` instead would bunch every line into the middle of
 * the face and leave the sides bare.
 */
export function azimuthField(positions: Float32Array, axisZ: number): Float32Array {
  const field = new Float32Array(positions.length / 3)
  for (let vertex = 0; vertex < field.length; vertex += 1) {
    field[vertex] = Math.atan2(positions[vertex * 3], positions[vertex * 3 + 2] - axisZ)
  }
  return field
}

/**
 * Interpolates a per-vertex scalar onto the line vertices. The occlusion term
 * is baked at rest, so the grid's own shading only has to be resolved once.
 */
export function bakeIsoScalar(plan: IsoLinePlan, scalars: Float32Array): Float32Array {
  const out = new Float32Array(plan.segmentCount * 2)
  for (let segment = 0; segment < plan.segmentCount; segment += 1) {
    for (let end = 0; end < 2; end += 1) {
      const a = plan.edges[segment * 4 + end * 2]
      const b = plan.edges[segment * 4 + end * 2 + 1]
      const t = plan.factors[segment * 2 + end]
      out[segment * 2 + end] = scalars[a] + (scalars[b] - scalars[a]) * t
    }
  }
  return out
}

/**
 * Same interpolation for a three-component attribute. Used to give every line
 * vertex the surface normal of the skin it was cut from: without it the grid is
 * lit uniformly and describes a balloon, however accurate the geometry under it
 * happens to be.
 */
export function bakeIsoVector(plan: IsoLinePlan, vectors: Float32Array): Float32Array {
  const out = new Float32Array(plan.segmentCount * 6)
  for (let segment = 0; segment < plan.segmentCount; segment += 1) {
    for (let end = 0; end < 2; end += 1) {
      const a = plan.edges[segment * 4 + end * 2] * 3
      const b = plan.edges[segment * 4 + end * 2 + 1] * 3
      const t = plan.factors[segment * 2 + end]
      const target = (segment * 2 + end) * 3
      for (let axis = 0; axis < 3; axis += 1) {
        out[target + axis] = vectors[a + axis] + (vectors[b + axis] - vectors[a + axis]) * t
      }
    }
  }
  return out
}

/** Re-evaluates every planned crossing against the current deformed vertices. */
export function evaluateIsoLines(plan: IsoLinePlan, positions: Float32Array, out: Float32Array) {
  for (let segment = 0; segment < plan.segmentCount; segment += 1) {
    for (let end = 0; end < 2; end += 1) {
      const a = plan.edges[segment * 4 + end * 2] * 3
      const b = plan.edges[segment * 4 + end * 2 + 1] * 3
      const t = plan.factors[segment * 2 + end]
      const target = (segment * 2 + end) * 3
      out[target] = positions[a] + (positions[b] - positions[a]) * t
      out[target + 1] = positions[a + 1] + (positions[b + 1] - positions[a + 1]) * t
      out[target + 2] = positions[a + 2] + (positions[b + 2] - positions[a + 2]) * t
    }
  }
}
