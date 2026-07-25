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
import { MODEL_SCALE, applySkin, buildFemaleHead, feminizeFace } from '../src/face/femaleHead.ts'
import { applyExpression, buildFaceRig, mouthAperture } from '../src/face/faceRig.ts'
import { buildHairStrands, hairlineAngle } from '../src/face/hair.ts'
import { evaluateContours, planContours } from '../src/face/contours.ts'
import { advanceVisemes, createVisemeState, visemeTargets } from '../src/face/visemes.ts'

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

// --- contours ---------------------------------------------------------------

test('contours are re-evaluated from the deformed mesh, not baked at rest', () => {
  const plan = planContours(build.basePositions, build.indices, 12, -11, 10.4)
  assert.ok(plan.segmentCount > 100)

  const restPoints = new Float32Array(plan.segmentCount * 6)
  evaluateContours(plan, build.basePositions, restPoints)

  const face = pose({ jawOpen: 1 })
  const deformed = new Float32Array(build.vertexCount * 3)
  applySkin(build.basePositions, face, build.skin, deformed)
  const movedPoints = new Float32Array(plan.segmentCount * 6)
  evaluateContours(plan, deformed, movedPoints)

  let moved = 0
  for (let i = 0; i < restPoints.length; i += 1) if (Math.abs(restPoints[i] - movedPoints[i]) > 1e-4) moved += 1
  assert.ok(moved > 0, 'contours must follow the jaw')
  // But only where the jaw actually reaches: the crown must be untouched.
  let crownMoved = false
  for (let i = 0; i < plan.segmentCount * 2; i += 1) {
    if (restPoints[i * 3 + 1] > 6 && Math.abs(restPoints[i * 3 + 1] - movedPoints[i * 3 + 1]) > 1e-4) crownMoved = true
  }
  assert.equal(crownMoved, false)
})

// --- hair -------------------------------------------------------------------

test('the hairline drops from the forehead to the nape and no strand crosses the face', () => {
  assert.ok(hairlineAngle(0) < hairlineAngle(Math.PI / 2))
  assert.ok(hairlineAngle(Math.PI / 2) < hairlineAngle(Math.PI))

  const hair = buildHairStrands(200)
  assert.equal(hair.positions.length / 3, hair.fade.length)
  let overFace = 0
  for (let i = 0; i < hair.positions.length; i += 3) {
    const [x, y, z] = [hair.positions[i], hair.positions[i + 1], hair.positions[i + 2]]
    // In front of the face plane, at face height, near the midline.
    if (z > 4 && y < 7 && y > -9 && Math.abs(x) < 5) overFace += 1
  }
  assert.equal(overFace, 0, `${overFace} hair vertices fall across the face`)
})

// --- visemes ----------------------------------------------------------------

const spectrumFrom = (peaks) => {
  const spectrum = new Uint8Array(512)
  for (let index = 0; index < spectrum.length; index += 1) {
    const f = index / spectrum.length
    let value = 0
    for (const [centre, gain, width] of peaks) value += gain * Math.exp(-((f - centre) ** 2) / (2 * width * width))
    spectrum[index] = Math.min(255, Math.round(value * 255))
  }
  return spectrum
}
const OPEN_A = spectrumFrom([[0.012, 0.9, 0.008], [0.03, 0.5, 0.012], [0.07, 0.25, 0.02]])
const ROUND_OU = spectrumFrom([[0.012, 0.8, 0.008], [0.032, 0.85, 0.012], [0.075, 0.1, 0.02]])
const SPREAD_I = spectrumFrom([[0.01, 0.45, 0.006], [0.03, 0.12, 0.01], [0.085, 0.9, 0.03]])
const SIBILANT_S = spectrumFrom([[0.01, 0.03, 0.006], [0.25, 0.8, 0.2]])

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
  const silent = visemeTargets(new Uint8Array(512), 0)
  assert.deepEqual(silent, { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0 })

  // Audio still flowing but nothing in the speech bands: a bilabial stop.
  const closure = visemeTargets(new Uint8Array(512), 0.4)
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
