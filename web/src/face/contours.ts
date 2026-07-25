/**
 * Horizontal iso-height contour slices across the head.
 *
 * These are the lines that make a hologram legible: shading alone is flat on an
 * additive surface, but contours read as topography and let a viewer see the
 * nose, the brow and the lips as *volume*. The junior implementation drew them
 * as fixed latitude rings around a sphere, so they described the sphere and not
 * the face, and they never moved when the face did.
 *
 * Here each slice is solved once against the rest pose and stored as edge
 * crossings — a pair of vertex indices and the position along that edge. A
 * frame then only has to re-interpolate those crossings from the deformed
 * vertices, so the contours stay welded to the skin while the jaw moves, at a
 * cost proportional to the number of visible segments rather than to the mesh.
 */

export type ContourPlan = {
  /** Four vertex indices per segment: (a0,b0) and (a1,b1). */
  edges: Uint32Array
  /** Two interpolation factors per segment. */
  factors: Float32Array
  segmentCount: number
}

/**
 * @param maxY exclusive upper bound; slices below `minY` are skipped so the
 *             bust does not accumulate rings the head does not need.
 */
export function planContours(
  positions: Float32Array,
  indices: ArrayLike<number>,
  sliceCount: number,
  minY: number,
  maxY: number,
): ContourPlan {
  const edges: number[] = []
  const factors: number[] = []

  for (let slice = 0; slice < sliceCount; slice += 1) {
    // Offset by half a step so no plane lands exactly on a vertex, which would
    // produce degenerate zero-length segments.
    const height = minY + (slice + 0.5) / sliceCount * (maxY - minY)

    for (let triangle = 0; triangle < indices.length; triangle += 3) {
      const corners = [indices[triangle], indices[triangle + 1], indices[triangle + 2]]
      const crossingA: number[] = []
      const crossingB: number[] = []
      const crossingT: number[] = []

      for (let edge = 0; edge < 3; edge += 1) {
        const a = corners[edge]
        const b = corners[(edge + 1) % 3]
        const ya = positions[a * 3 + 1]
        const yb = positions[b * 3 + 1]
        if ((ya < height) === (yb < height)) continue
        crossingA.push(a)
        crossingB.push(b)
        crossingT.push((height - ya) / (yb - ya))
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

/** Re-evaluates every planned crossing against the current deformed vertices. */
export function evaluateContours(plan: ContourPlan, positions: Float32Array, out: Float32Array) {
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
