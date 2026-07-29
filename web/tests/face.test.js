// The facial geometry, the rig and the viseme solver are deliberately free of
// any three.js import, so they can be exercised here as real behaviour rather
// than as source-text assertions. Node ≥22.18 strips the TypeScript types on
// import, which is why the face modules use explicit `.ts` specifiers.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  CANONICAL_VERTEX_COUNT,
  INNER_LIP_RING,
  LANDMARK,
  LEFT_EYE_RING,
  RIGHT_EYE_RING,
  findBoundaryLoops,
  parseCanonicalFaceObj,
} from '../src/face/canonicalFace.ts'
import {
  MODEL_SCALE, SKULL_CENTRE, SKULL_RADII, applySkin, buildFemaleHead, feminizeFace,
} from '../src/face/femaleHead.ts'
import { applyExpression, buildFaceRig, mouthAperture } from '../src/face/faceRig.ts'
import { buildHairStrands, hairlineAngle } from '../src/face/hair.ts'
import {
  azimuthField, bakeIsoScalar, evaluateIsoLines, evenLevels, heightField, planIsoLines,
} from '../src/face/contours.ts'
import { applySubdivision, buildSubdivisionLevel, computeNormals } from '../src/face/subdivide.ts'
import { hairlineAngle as hairline, scalpMask } from '../src/face/hair.ts'
import { VOICE_RANGE_HZ, advanceVisemes, binForHz, createVisemeState, visemeTargets } from '../src/face/visemes.ts'
import { remapAnalyserSpectrum } from '../src/face/audioSpectrum.ts'
import { buildBraids, buildHeadClearance } from '../src/face/braids.ts'

const objectText = readFileSync(new URL('../public/models/emefa-canonical-face.obj', import.meta.url), 'utf8')
const canonical = parseCanonicalFaceObj(objectText)
const rest = feminizeFace(canonical.positions)
const build = buildFemaleHead(canonical, rest)
const rig = buildFaceRig(rest)

const at = (positions, index) => [positions[index * 3], positions[index * 3 + 1], positions[index * 3 + 2]]
const neutral = {
  jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0,
  smile: 0, browRaise: 0, blinkLeft: 0, blinkRight: 0, squint: 0,
}
const pose = (overrides) => {
  const out = new Float32Array(CANONICAL_VERTEX_COUNT * 3)
  applyExpression(rig, { ...neutral, ...overrides }, out)
  return out
}

// --- the bundled model ------------------------------------------------------

test('the bundled model is the 468-landmark canonical face with a single face oval', () => {
  assert.equal(canonical.positions.length, CANONICAL_VERTEX_COUNT * 3)
  assert.equal(canonical.boundary.length, 36)
  // Carving leaves four open loops: the face oval plus both eyes and the mouth.
  assert.equal(findBoundaryLoops(canonical.indices).length, 4)
})

test('landmark indices land on the anatomy they are named for', () => {
  // Guards the whole rig against a silent model swap: every weight field and
  // every feature contour is addressed by these numbers.
  const lowest = [...Array(CANONICAL_VERTEX_COUNT).keys()]
    .reduce((best, i) => (canonical.positions[i * 3 + 1] < canonical.positions[best * 3 + 1] ? i : best), 0)
  const highest = [...Array(CANONICAL_VERTEX_COUNT).keys()]
    .reduce((best, i) => (canonical.positions[i * 3 + 1] > canonical.positions[best * 3 + 1] ? i : best), 0)
  const foremost = [...Array(CANONICAL_VERTEX_COUNT).keys()]
    .reduce((best, i) => (canonical.positions[i * 3 + 2] > canonical.positions[best * 3 + 2] ? i : best), 0)
  assert.equal(lowest, LANDMARK.chin)
  assert.equal(highest, LANDMARK.foreheadTop)
  assert.equal(foremost, LANDMARK.noseTip)
  assert.ok(at(canonical.positions, LANDMARK.mouthRightCorner)[0] < 0)
  assert.ok(at(canonical.positions, LANDMARK.mouthLeftCorner)[0] > 0)
  assert.ok(at(canonical.positions, LANDMARK.upperLipInner)[1] > at(canonical.positions, LANDMARK.lowerLipInner)[1])
})

test('the eye sockets and the mouth are carved open so they are not painted on', () => {
  const isPatch = (ring) => (a, b, c) => ring.includes(a) && ring.includes(b) && ring.includes(c)
  for (const ring of [RIGHT_EYE_RING, LEFT_EYE_RING, INNER_LIP_RING]) {
    const test = isPatch(ring)
    let remaining = 0
    for (let i = 0; i < canonical.indices.length; i += 3) {
      if (test(canonical.indices[i], canonical.indices[i + 1], canonical.indices[i + 2])) remaining += 1
    }
    assert.equal(remaining, 0)
  }
  // 14 per eye plus 18 across the mouth.
  assert.equal((898 * 3 - canonical.indices.length) / 3, 46)
})

// --- feminisation -----------------------------------------------------------

test('feminisation applies the dimorphic traits it claims to', () => {
  const source = canonical.positions
  const width = (positions, index) => Math.abs(positions[index * 3])

  // Shorter lower third.
  assert.ok(at(rest, LANDMARK.chin)[1] > at(source, LANDMARK.chin)[1] + 1)
  // Narrower mandible.
  assert.ok(width(rest, LANDMARK.mouthLeftCorner) < width(source, LANDMARK.mouthLeftCorner))
  // Flatter supraorbital ridge, higher brow line.
  assert.ok(at(rest, 105)[2] < at(source, 105)[2])
  assert.ok(at(rest, 105)[1] > at(source, 105)[1])
  // Narrower nasal base.
  assert.ok(width(rest, 48) < width(source, 48))
  // Larger palpebral aperture.
  const aperture = (positions) => positions[159 * 3 + 1] - positions[145 * 3 + 1]
  assert.ok(aperture(rest) > aperture(source) * 1.2)
  // And it stays a face: no landmark is thrown across the head.
  for (let i = 0; i < CANONICAL_VERTEX_COUNT * 3; i += 1) {
    assert.ok(Math.abs(rest[i] - source[i]) < 2.5, `landmark ${Math.floor(i / 3)} moved too far`)
  }
})

// --- head construction ------------------------------------------------------

test('the head is grown from the face rather than wrapped around it', () => {
  // Canonical landmarks lead the buffer untouched, so the rig can address them.
  for (let i = 0; i < CANONICAL_VERTEX_COUNT * 3; i += 1) {
    assert.equal(build.basePositions[i], rest[i])
  }
  // The cranium closes above the forehead and behind the ears.
  let crown = -Infinity
  let back = Infinity
  for (let i = 0; i < build.vertexCount; i += 1) {
    crown = Math.max(crown, build.basePositions[i * 3 + 1])
    back = Math.min(back, build.basePositions[i * 3 + 2])
  }
  assert.ok(crown > at(rest, LANDMARK.foreheadTop)[1] + 1.5, 'skull must rise above the hairline')
  assert.ok(back < -8, 'the back of the head must sit well behind the ears')
  assert.ok(build.scale === MODEL_SCALE)
})

test('the cranium seam is welded to the face oval', () => {
  // Ring 0 of the sweep *is* the boundary loop, and the first generated ring
  // keeps almost all of its parent's influence — otherwise an opening jaw tears
  // the head open along the jawline.
  const seamInfluences = []
  for (let i = CANONICAL_VERTEX_COUNT; i < CANONICAL_VERTEX_COUNT + canonical.boundary.length; i += 1) {
    assert.ok(canonical.boundary.includes(build.skin.parent[i]))
    seamInfluences.push(build.skin.influence[i])
  }
  assert.ok(Math.min(...seamInfluences) > 0.95)
})

test('every triangle in the assembled head winds outwards', () => {
  // Consistent winding is what lets the hologram shade with FrontSide and one
  // set of normals; a flipped patch shows up as a hole in the face.
  let inverted = 0
  for (let i = 0; i < build.indices.length; i += 3) {
    const [a, b, c] = [build.indices[i], build.indices[i + 1], build.indices[i + 2]].map((v) => at(build.basePositions, v))
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
    const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]]
    const normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    const centroidY = (a[1] + b[1] + c[1]) / 3
    const referenceY = Math.min(4, Math.max(-18, centroidY))
    const referenceZ = centroidY > 0 ? -0.5 : centroidY < -14 ? -1.2 : -0.85
    const outward = [
      (a[0] + b[0] + c[0]) / 3,
      centroidY - referenceY,
      (a[2] + b[2] + c[2]) / 3 - referenceZ,
    ]
    if (normal[0] * outward[0] + normal[1] * outward[1] + normal[2] * outward[2] < 0) inverted += 1
  }
  assert.ok(inverted / (build.indices.length / 3) < 0.02, `${inverted} inverted triangles`)
})

test('skinning carries the face into the generated geometry without drift', () => {
  const face = pose({ jawOpen: 1 })
  const out = new Float32Array(build.vertexCount * 3)
  applySkin(build.basePositions, face, build.skin, out)

  for (let i = 0; i < CANONICAL_VERTEX_COUNT * 3; i += 1) assert.equal(out[i], face[i])
  for (let i = CANONICAL_VERTEX_COUNT; i < build.vertexCount; i += 1) {
    const parent = build.skin.parent[i]
    const influence = build.skin.influence[i]
    if (parent < 0 || influence === 0) {
      assert.equal(out[i * 3 + 1], build.basePositions[i * 3 + 1], 'static geometry must not move')
      continue
    }
    const expected = build.basePositions[i * 3 + 1] + influence * (face[parent * 3 + 1] - rest[parent * 3 + 1])
    assert.ok(Math.abs(out[i * 3 + 1] - expected) < 1e-4)
  }
})

// --- the rig ----------------------------------------------------------------

test('an opening jaw parts the lips instead of just lowering the whole face', () => {
  const open = pose({ jawOpen: 1 })
  const aperture = mouthAperture(open) - mouthAperture(rest)
  // Roughly 8–14 mm at a wide vowel, in the model's ~1 unit ≈ 1 cm scale.
  assert.ok(aperture > 0.7 && aperture < 1.5, `aperture opened by ${aperture.toFixed(2)}`)
  // The upper lip belongs to the maxilla and must stay put.
  assert.ok(Math.abs(open[LANDMARK.upperLipInner * 3 + 1] - rest[LANDMARK.upperLipInner * 3 + 1]) < 0.12)
  // The brow is nowhere near the mandible.
  assert.ok(Math.abs(open[LANDMARK.foreheadTop * 3 + 1] - rest[LANDMARK.foreheadTop * 3 + 1]) < 1e-6)
})

test('the mandible rotates about the condyle without retracting the chin into the neck', () => {
  // Regression: rotating about a pivot far behind the ear swung the chin ~3.5
  // units backwards, which drove the jaw through the neck on every wide vowel.
  const open = pose({ jawOpen: 1 })
  const drop = rest[LANDMARK.chin * 3 + 1] - open[LANDMARK.chin * 3 + 1]
  const retraction = rest[LANDMARK.chin * 3 + 2] - open[LANDMARK.chin * 3 + 2]
  assert.ok(drop > 0.6 && drop < 1.6, `chin dropped ${drop.toFixed(2)}`)
  assert.ok(retraction > -0.4 && retraction < 0.9, `chin retracted ${retraction.toFixed(2)}`)
})

test('rounded and spread lips are distinguishable shapes, not one shape scaled', () => {
  const cornerWidth = (positions) =>
    positions[LANDMARK.mouthLeftCorner * 3] - positions[LANDMARK.mouthRightCorner * 3]
  const projection = (positions) => positions[LANDMARK.upperLipOuter * 3 + 2]

  const round = pose({ lipRound: 1 })
  const wide = pose({ lipWide: 1 })
  assert.ok(cornerWidth(round) < cornerWidth(rest), 'rounding purses the commissures inwards')
  assert.ok(cornerWidth(wide) > cornerWidth(rest), 'spreading pulls them outwards')
  assert.ok(projection(round) > projection(rest), 'rounding protrudes the vermilion')
  assert.ok(projection(wide) < projection(rest), 'spreading flattens it')
})

test('a blink closes the palpebral aperture and leaves the other eye alone', () => {
  const closed = pose({ blinkRight: 1 })
  const rightAperture = closed[159 * 3 + 1] - closed[145 * 3 + 1]
  const leftAperture = closed[386 * 3 + 1] - closed[374 * 3 + 1]
  const restRight = rest[159 * 3 + 1] - rest[145 * 3 + 1]
  const restLeft = rest[386 * 3 + 1] - rest[374 * 3 + 1]
  assert.ok(rightAperture < restRight * 0.25, 'the closing lid must actually meet the lower one')
  assert.ok(Math.abs(leftAperture - restLeft) < 1e-6)
})

test('the neutral expression is a no-op', () => {
  const still = pose({})
  for (let i = 0; i < CANONICAL_VERTEX_COUNT * 3; i += 1) {
    assert.ok(Math.abs(still[i] - rest[i]) < 1e-5)
  }
})

// --- subdivision ------------------------------------------------------------

const level = buildSubdivisionLevel(build.vertexCount, build.indices)
const baseSmooth = new Float32Array(level.vertexCount * 3)
applySubdivision(level, build.basePositions, baseSmooth)

test('the subdivision operator is a valid affine stencil', () => {
  // Every row must sum to one, or the head drifts and shrinks each level.
  for (let vertex = 0; vertex < level.vertexCount; vertex += 1) {
    let total = 0
    for (let entry = level.rowStart[vertex]; entry < level.rowStart[vertex + 1]; entry += 1) {
      total += level.weights[entry]
    }
    assert.ok(Math.abs(total - 1) < 1e-5, `row ${vertex} sums to ${total}`)
  }
  assert.equal(level.indices.length, build.indices.length * 4)
  assert.ok(level.vertexCount > build.vertexCount * 3)
})

test('subdivision keeps the landmark numbering the rig depends on', () => {
  // Original vertices must stay at their own indices, and stay close to where
  // they were — every feature contour and every rig weight is addressed by
  // number, so a renumbering would silently scramble the face.
  for (let vertex = 0; vertex < CANONICAL_VERTEX_COUNT; vertex += 1) {
    const moved = Math.hypot(
      baseSmooth[vertex * 3] - build.basePositions[vertex * 3],
      baseSmooth[vertex * 3 + 1] - build.basePositions[vertex * 3 + 1],
      baseSmooth[vertex * 3 + 2] - build.basePositions[vertex * 3 + 2],
    )
    assert.ok(moved < 1, `landmark ${vertex} moved ${moved.toFixed(2)} under subdivision`)
  }
  // The eye and mouth apertures are boundaries; the boundary rule has to keep
  // them open rather than shrinking them into the surface.
  const aperture = (positions) => positions[159 * 3 + 1] - positions[145 * 3 + 1]
  assert.ok(aperture(baseSmooth) > aperture(build.basePositions) * 0.75)
})

test('subdivision smooths the surface it is given', () => {
  // Dihedral angles across the smoothed mesh must be gentler than across the
  // original: that is the whole point, and it is what removes the faceted
  // silhouette from the jaw and the nose.
  const meanDihedral = (positions, indices) => {
    const normals = computeNormals(positions, indices)
    let total = 0
    let count = 0
    for (let i = 0; i < indices.length; i += 3) {
      for (let corner = 0; corner < 3; corner += 1) {
        const a = indices[i + corner] * 3
        const b = indices[i + (corner + 1) % 3] * 3
        total += 1 - (normals[a] * normals[b] + normals[a + 1] * normals[b + 1] + normals[a + 2] * normals[b + 2])
        count += 1
      }
    }
    return total / count
  }
  assert.ok(
    meanDihedral(baseSmooth, level.indices) < meanDihedral(build.basePositions, build.indices) * 0.6,
  )
})

// --- the grid ---------------------------------------------------------------

test('the grid is re-evaluated from the deformed mesh, not baked at rest', () => {
  const plan = planIsoLines(level.indices, heightField(baseSmooth), evenLevels(-11, 9, 12))
  assert.ok(plan.segmentCount > 100)

  const restPoints = new Float32Array(plan.segmentCount * 6)
  evaluateIsoLines(plan, baseSmooth, restPoints)

  const face = pose({ jawOpen: 1 })
  const deformed = new Float32Array(build.vertexCount * 3)
  applySkin(build.basePositions, face, build.skin, deformed)
  const smooth = new Float32Array(level.vertexCount * 3)
  applySubdivision(level, deformed, smooth)
  const movedPoints = new Float32Array(plan.segmentCount * 6)
  evaluateIsoLines(plan, smooth, movedPoints)

  let moved = 0
  for (let i = 0; i < restPoints.length; i += 1) if (Math.abs(restPoints[i] - movedPoints[i]) > 1e-4) moved += 1
  assert.ok(moved > 0, 'the grid must follow the jaw')
  // But only where the jaw actually reaches: the crown must be untouched.
  let crownMoved = false
  for (let i = 0; i < plan.segmentCount * 2; i += 1) {
    if (restPoints[i * 3 + 1] > 6 && Math.abs(restPoints[i * 3 + 1] - movedPoints[i * 3 + 1]) > 1e-4) crownMoved = true
  }
  assert.equal(crownMoved, false)
})

test('the meridians wrap the head without a seam artefact', () => {
  const field = azimuthField(baseSmooth, -1)
  const seamless = planIsoLines(level.indices, field, evenLevels(-Math.PI, Math.PI, 16), true)
  const seamed = planIsoLines(level.indices, field, evenLevels(-Math.PI, Math.PI, 16), false)
  // Without the wrap guard, every triangle straddling ±π reports a spurious
  // crossing at *every* level, which draws a fan across the back of the head.
  assert.ok(seamless.segmentCount < seamed.segmentCount)
  assert.ok(seamless.segmentCount > 400)
})

test('the grid stops at the hairline so the scalp is left to the hair', () => {
  const mask = scalpMask(baseSmooth)
  let onFace = 0
  let onScalp = 0
  for (let vertex = 0; vertex < level.vertexCount; vertex += 1) {
    const y = baseSmooth[vertex * 3 + 1]
    const z = baseSmooth[vertex * 3 + 2]
    // Chin, unambiguously face.
    if (y < -6 && z > 2) onFace = Math.max(onFace, mask[vertex])
    // Crown, unambiguously scalp.
    if (y > 8) onScalp = Math.max(onScalp, mask[vertex])
  }
  assert.ok(onFace > 0.95, 'the face must keep its grid')
  assert.ok(onScalp < 0.05, 'the crown must not')
  assert.ok(hairline(0) < hairline(Math.PI))
})

test('baked line shading interpolates the vertex term it is given', () => {
  const plan = planIsoLines(level.indices, heightField(baseSmooth), evenLevels(-11, 9, 6))
  const uniform = new Float32Array(level.vertexCount).fill(0.5)
  for (const value of bakeIsoScalar(plan, uniform)) assert.ok(Math.abs(value - 0.5) < 1e-6)
})

// --- hair -------------------------------------------------------------------

test('the hairline drops from the forehead to the nape and no strand crosses the face', () => {
  assert.ok(hairlineAngle(0) < hairlineAngle(Math.PI / 2))
  assert.ok(hairlineAngle(Math.PI / 2) < hairlineAngle(Math.PI))

  const hair = buildHairStrands(200)
  assert.equal(hair.positions.length / 3, hair.fade.length)

  // "Across the face" means in front of skin that actually faces the viewer.
  // A cuboid test clips the temples, where the hairline legitimately passes and
  // the skin sits well forward; a plain depth test flags the strands falling
  // beside the ears, where the surface is edge-on and "in front in z" means
  // nothing. Both are correct hair, so the predicate needs the surface normal.
  const skinNormals = computeNormals(rest, canonical.indices)
  let overFace = 0
  for (let i = 0; i < hair.positions.length; i += 3) {
    const [x, y, z] = [hair.positions[i], hair.positions[i + 1], hair.positions[i + 2]]
    let nearest = -1
    let nearestDistance = Infinity
    for (let vertex = 0; vertex < CANONICAL_VERTEX_COUNT; vertex += 1) {
      const distance = Math.hypot(rest[vertex * 3] - x, rest[vertex * 3 + 1] - y)
      if (distance < nearestDistance) {
        nearestDistance = distance
        nearest = vertex
      }
    }
    if (nearestDistance > 1.2) continue
    if (skinNormals[nearest * 3 + 2] < 0.5) continue
    if (z > rest[nearest * 3 + 2] + 0.35) overFace += 1
  }
  assert.equal(overFace, 0, `${overFace} hair vertices hang in front of the face`)
})

// --- visemes ----------------------------------------------------------------

test('raw Web Audio FFT is remapped into the same 100 Hz–8 kHz range as ElevenLabs', () => {
  const sampleRate = 48_000
  const raw = new Uint8Array(256)
  const sourceBin = Math.round(600 / (sampleRate / (raw.length * 2)))
  raw[sourceBin] = 255

  const mapped = remapAnalyserSpectrum(raw, sampleRate, 128)
  const expected = binForHz(600, mapped.length)
  const strongest = mapped.indexOf(Math.max(...mapped))
  assert.ok(Math.abs(strongest - expected) <= 2, `${strongest} should be near ${expected}`)
  assert.ok(mapped[expected] > 100, 'the speech-band peak must survive remapping')
})

// Spectra are built in *hertz*, because the analyser buffer this code consumes
// is not a raw FFT: the client resamples it into a 100 Hz–8 kHz voice range
// stretched across every bin. Treating it as 0 Hz–Nyquist put every band about
// three times too low, so "F1" measured the pitch fundamental and "sibilance"
// measured F2 — which is why the mouth only ever flapped with volume.
const spectrumAtHz = (peaks) => {
  const spectrum = new Uint8Array(1024)
  const [low, high] = VOICE_RANGE_HZ
  for (let index = 0; index < spectrum.length; index += 1) {
    const hz = low + (index / spectrum.length) * (high - low)
    let value = 0
    for (const [centreHz, gain, widthHz] of peaks) {
      value += gain * Math.exp(-((hz - centreHz) ** 2) / (2 * widthHz * widthHz))
    }
    spectrum[index] = Math.min(255, Math.round(value * 255))
  }
  return spectrum
}

// Formant pairs for real French vowels (F1, F2), plus a sibilant.
const OPEN_A = spectrumAtHz([[750, 1, 110], [1350, 0.6, 160]])
const ROUND_OU = spectrumAtHz([[320, 0.9, 90], [800, 0.95, 130], [2200, 0.06, 200]])
const SPREAD_I = spectrumAtHz([[300, 0.5, 80], [900, 0.12, 130], [2400, 1, 260]])
const SIBILANT_S = spectrumAtHz([[600, 0.04, 120], [6200, 1, 1400]])

test('band edges follow the client voice range, not the Nyquist span', () => {
  assert.deepEqual([...VOICE_RANGE_HZ], [100, 8000])
  assert.equal(binForHz(100, 1024), 0)
  assert.equal(binForHz(8000, 1024), 1024)
  // The midpoint of the range lands mid-buffer — the property that a
  // 0-to-Nyquist reading gets wrong.
  assert.equal(binForHz(4050, 1024), 512)
})

test('the viseme solver separates rounded, spread and sibilant articulation', () => {
  const round = visemeTargets(ROUND_OU, 0.8)
  const spread = visemeTargets(SPREAD_I, 0.8)
  const sibilant = visemeTargets(SIBILANT_S, 0.6)
  const open = visemeTargets(OPEN_A, 0.9)

  assert.ok(round.lipRound > round.lipWide, 'back vowels purse')
  assert.ok(spread.lipWide > spread.lipRound, 'front vowels spread')
  assert.ok(sibilant.lipWide > sibilant.lipRound, 'sibilants spread')
  assert.ok(sibilant.jawOpen < open.jawOpen, 'a fricative is not a wide vowel')
  assert.ok(open.jawOpen > 0.4, 'an open vowel must actually open the jaw')
})

test('silence and closure are told apart', () => {
  const silent = visemeTargets(new Uint8Array(1024), 0)
  assert.deepEqual(silent, { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0 })

  // Audio still flowing but nothing in the speech bands: a bilabial stop.
  const closure = visemeTargets(new Uint8Array(1024), 0.4)
  assert.ok(closure.lipPress > 0.5)
  assert.equal(closure.jawOpen, 0)
})

test('articulation is frame-rate independent and opens faster than it relaxes', () => {
  const targets = visemeTargets(OPEN_A, 0.9)
  const coarse = createVisemeState()
  advanceVisemes(coarse, targets, 0.9, 0.1)

  const fine = createVisemeState()
  for (let step = 0; step < 10; step += 1) advanceVisemes(fine, targets, 0.9, 0.01)

  assert.ok(Math.abs(coarse.jawOpen - fine.jawOpen) < 0.02, 'a 100 ms step must match ten 10 ms steps')

  // Attack beats release: mouths open quickly and settle slowly.
  const opening = createVisemeState()
  advanceVisemes(opening, targets, 0.9, 0.03)
  const closing = createVisemeState()
  closing.jawOpen = targets.jawOpen
  advanceVisemes(closing, { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0 }, 0, 0.03)
  assert.ok(opening.jawOpen / targets.jawOpen > 1 - closing.jawOpen / targets.jawOpen)
})


test('braided hair covers the scalp and hangs clear of the face', () => {
  const braids = buildBraids(buildHeadClearance(build.basePositions, build.vertexCount), 17)
  assert.equal(braids.positions.length / 3, braids.fade.length)

  let overCrown = 0
  let acrossFace = 0
  for (let i = 0; i < braids.positions.length; i += 3) {
    const [x, y, z] = [braids.positions[i], braids.positions[i + 1], braids.positions[i + 2]]
    if (y > 6) overCrown += 1
    // In front of the face plane at face height near the midline.
    if (z > 4.5 && y < 5 && y > -9 && Math.abs(x) < 4.5) acrossFace += 1
  }
  assert.ok(overCrown > braids.fade.length * 0.3, 'cornrows must actually cover the crown')
  assert.equal(acrossFace, 0, `${acrossFace} braid vertices fall across the face`)

  // The braid shell has to clear the *swept cranium*, not the ellipsoid it was
  // derived from. The cranium is grown from the face's boundary loop, so over
  // the front of the scalp it sits well outside the ellipsoid — a shell sized
  // to the ellipsoid ends up inside the skull there and the depth prepass
  // culls the entire hairstyle. Clearance is per-direction: the head's radius
  // varies a lot between the brow and the nape, so a single global comparison
  // both misses real burial and cries wolf over the deliberately set-back
  // front rows.
  const direction = (positions, index) => {
    const d = [
      (positions[index * 3] - SKULL_CENTRE[0]) / SKULL_RADII[0],
      (positions[index * 3 + 1] - SKULL_CENTRE[1]) / SKULL_RADII[1],
      (positions[index * 3 + 2] - SKULL_CENTRE[2]) / SKULL_RADII[2],
    ]
    const radius = Math.hypot(d[0], d[1], d[2]) || 1
    return { unit: [d[0] / radius, d[1] / radius, d[2] / radius], radius }
  }
  const headDirections = []
  for (let vertex = 0; vertex < build.vertexCount; vertex += 1) {
    if (build.basePositions[vertex * 3 + 1] < 0) continue
    headDirections.push(direction(build.basePositions, vertex))
  }

  let buried = 0
  let sampled = 0
  for (let i = 0; i < braids.positions.length / 3; i += 7) {
    if (braids.positions[i * 3 + 1] < 4) continue
    const braid = direction(braids.positions, i)
    let nearest = null
    let best = -Infinity
    for (const candidate of headDirections) {
      const alignment = braid.unit[0] * candidate.unit[0]
        + braid.unit[1] * candidate.unit[1]
        + braid.unit[2] * candidate.unit[2]
      if (alignment > best) {
        best = alignment
        nearest = candidate
      }
    }
    if (best < 0.995) continue
    sampled += 1
    if (braid.radius < nearest.radius * 0.99) buried += 1
  }
  assert.ok(sampled > 40, `only ${sampled} braid vertices had head geometry behind them`)
  assert.equal(buried, 0, `${buried} of ${sampled} braid vertices sit inside the skull`)
})
