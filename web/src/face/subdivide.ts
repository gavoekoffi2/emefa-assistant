/**
 * Loop subdivision, expressed as a reusable *linear operator*.
 *
 * The landmark model is 468 vertices. That is enough to place anatomy but not
 * nearly enough to look like skin: at that density the jaw, the nose and the
 * lips all have visibly straight edges, and no amount of shading hides a
 * faceted silhouette. Subdividing fixes it — but the face has to stay
 * animatable, and re-running a subdivision algorithm every frame would not fit
 * in a frame budget shared with a live voice session.
 *
 * Loop subdivision is linear in the vertex positions, so the topology work is
 * done once at build time and stored as a sparse matrix. A frame then costs one
 * sparse multiply against the deformed base mesh. The same operator also
 * carries per-vertex scalars (the baked occlusion term) for free.
 *
 * The original vertices keep their indices in the output, so every landmark the
 * rig and the feature contours address by number stays addressable.
 */

export type SubdivisionLevel = {
  vertexCount: number
  indices: Uint32Array
  /** CSR sparse matrix: row `i` spans `rowStart[i] … rowStart[i + 1]`. */
  rowStart: Uint32Array
  columns: Uint32Array
  weights: Float32Array
}

const edgeKey = (a: number, b: number) => (a < b ? a * 1000000 + b : b * 1000000 + a)

/**
 * Warren's approximation of Loop's β. Both are standard; Warren's avoids a
 * trigonometric call per valence and is visually indistinguishable.
 */
function beta(valence: number) {
  return valence === 3 ? 3 / 16 : 3 / (8 * valence)
}

export function buildSubdivisionLevel(vertexCount: number, indices: ArrayLike<number>): SubdivisionLevel {
  type Edge = { id: number; a: number; b: number; opposite: number[] }
  const edges = new Map<number, Edge>()
  const neighbours: Set<number>[] = Array.from({ length: vertexCount }, () => new Set<number>())

  for (let i = 0; i < indices.length; i += 3) {
    const corners = [indices[i], indices[i + 1], indices[i + 2]]
    for (let corner = 0; corner < 3; corner += 1) {
      const a = corners[corner]
      const b = corners[(corner + 1) % 3]
      const opposite = corners[(corner + 2) % 3]
      neighbours[a].add(b)
      neighbours[b].add(a)
      const key = edgeKey(a, b)
      const existing = edges.get(key)
      if (existing) existing.opposite.push(opposite)
      else edges.set(key, { id: -1, a, b, opposite: [opposite] })
    }
  }

  let nextId = vertexCount
  for (const edge of edges.values()) edge.id = nextId++

  // Boundary vertices need their two boundary neighbours, not their whole ring.
  const boundaryNeighbours: number[][] = Array.from({ length: vertexCount }, () => [])
  for (const edge of edges.values()) {
    if (edge.opposite.length !== 1) continue
    boundaryNeighbours[edge.a].push(edge.b)
    boundaryNeighbours[edge.b].push(edge.a)
  }

  const rowStart = new Uint32Array(nextId + 1)
  const columns: number[] = []
  const weights: number[] = []
  const emit = (column: number, weight: number) => { columns.push(column); weights.push(weight) }

  for (let vertex = 0; vertex < vertexCount; vertex += 1) {
    rowStart[vertex] = columns.length
    const boundary = boundaryNeighbours[vertex]
    if (boundary.length === 2) {
      // Boundary rule keeps the eye and mouth apertures from collapsing.
      emit(vertex, 3 / 4)
      emit(boundary[0], 1 / 8)
      emit(boundary[1], 1 / 8)
      continue
    }
    const ring = [...neighbours[vertex]]
    if (ring.length === 0) {
      emit(vertex, 1)
      continue
    }
    const b = beta(ring.length)
    emit(vertex, 1 - ring.length * b)
    for (const neighbour of ring) emit(neighbour, b)
  }

  for (const edge of edges.values()) {
    rowStart[edge.id] = columns.length
    if (edge.opposite.length === 1) {
      emit(edge.a, 1 / 2)
      emit(edge.b, 1 / 2)
      continue
    }
    emit(edge.a, 3 / 8)
    emit(edge.b, 3 / 8)
    // A non-manifold edge (three or more incident faces) would otherwise skew
    // the stencil; averaging the opposites keeps the row summing to one.
    const share = (1 / 4) / edge.opposite.length
    for (const opposite of edge.opposite) emit(opposite, share)
  }
  rowStart[nextId] = columns.length

  const output: number[] = []
  for (let i = 0; i < indices.length; i += 3) {
    const [a, b, c] = [indices[i], indices[i + 1], indices[i + 2]]
    const ab = edges.get(edgeKey(a, b))!.id
    const bc = edges.get(edgeKey(b, c))!.id
    const ca = edges.get(edgeKey(c, a))!.id
    output.push(a, ab, ca, b, bc, ab, c, ca, bc, ab, bc, ca)
  }

  return {
    vertexCount: nextId,
    indices: new Uint32Array(output),
    rowStart,
    columns: new Uint32Array(columns),
    weights: new Float32Array(weights),
  }
}

/** Applies the operator to an interleaved attribute of `components` floats. */
export function applySubdivision(
  level: SubdivisionLevel,
  source: Float32Array,
  out: Float32Array,
  components = 3,
) {
  for (let vertex = 0; vertex < level.vertexCount; vertex += 1) {
    const from = level.rowStart[vertex]
    const to = level.rowStart[vertex + 1]
    for (let component = 0; component < components; component += 1) {
      let total = 0
      for (let entry = from; entry < to; entry += 1) {
        total += level.weights[entry] * source[level.columns[entry] * components + component]
      }
      out[vertex * components + component] = total
    }
  }
}

/**
 * Cheap per-vertex obscurance, baked once against the rest pose.
 *
 * An additively blended surface has no shadows, so concave regions — the eye
 * sockets, the alar creases, under the lower lip, under the jaw — render at
 * exactly the same brightness as the cheeks. That flatness is most of what
 * makes a rendered face look drawn rather than lit. Counting how much geometry
 * sits inside each vertex's own hemisphere approximates the missing occlusion
 * closely enough to restore the modelling.
 */
export function bakeOcclusion(positions: Float32Array, normals: Float32Array, radius: number): Float32Array {
  const count = positions.length / 3
  const occlusion = new Float32Array(count)
  const radiusSquared = radius * radius

  for (let vertex = 0; vertex < count; vertex += 1) {
    const px = positions[vertex * 3]
    const py = positions[vertex * 3 + 1]
    const pz = positions[vertex * 3 + 2]
    const nx = normals[vertex * 3]
    const ny = normals[vertex * 3 + 1]
    const nz = normals[vertex * 3 + 2]
    let blocked = 0
    let total = 0

    for (let other = 0; other < count; other += 1) {
      if (other === vertex) continue
      const dx = positions[other * 3] - px
      const dy = positions[other * 3 + 1] - py
      const dz = positions[other * 3 + 2] - pz
      const distanceSquared = dx * dx + dy * dy + dz * dz
      if (distanceSquared > radiusSquared) continue
      const falloff = 1 - distanceSquared / radiusSquared
      total += falloff
      // Only geometry in front of the tangent plane can occlude.
      const facing = (dx * nx + dy * ny + dz * nz) / Math.sqrt(distanceSquared)
      if (facing > 0.15) blocked += falloff * facing
    }

    occlusion[vertex] = total > 0 ? 1 - Math.min(1, (blocked / total) * 2.1) : 1
  }
  return occlusion
}

/** Area-weighted vertex normals, needed before occlusion can be baked. */
export function computeNormals(positions: Float32Array, indices: ArrayLike<number>): Float32Array {
  const normals = new Float32Array(positions.length)
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
    for (const corner of [a, b, c]) {
      normals[corner] += nx
      normals[corner + 1] += ny
      normals[corner + 2] += nz
    }
  }
  for (let i = 0; i < normals.length; i += 3) {
    const length = Math.hypot(normals[i], normals[i + 1], normals[i + 2]) || 1
    normals[i] /= length
    normals[i + 1] /= length
    normals[i + 2] /= length
  }
  return normals
}
