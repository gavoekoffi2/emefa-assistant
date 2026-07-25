import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { VoiceState } from './App'
import {
  ACCENT_CHAINS, FEATURE_CHAINS, FEATURE_LOOPS, chainEdges, loopEdges, parseCanonicalFaceObj,
} from './face/canonicalFace.ts'
import { SKULL_CENTRE, applySkin, buildFemaleHead, feminizeFace, hash01, smoothstep } from './face/femaleHead.ts'
import { applyExpression, buildFaceRig, mouthAperture } from './face/faceRig.ts'
import type { Expression } from './face/faceRig.ts'
import { buildFaceDetail, evaluateFaceDetail } from './face/faceDetail.ts'
import { buildHairStrands, scalpMask } from './face/hair.ts'
import {
  azimuthField, bakeIsoScalar, bakeIsoVector, evaluateIsoLines, evenLevels, heightField, planIsoLines,
} from './face/contours.ts'
import { applySubdivision, bakeOcclusion, buildSubdivisionLevel, computeNormals } from './face/subdivide.ts'
import { advanceVisemes, createVisemeState, visemeTargets } from './face/visemes.ts'
import './EMEFAFace.css'

type EMEFAFaceProps = {
  state: VoiceState
  onClick: () => void
  getOutputVolume: () => number
  getOutputFrequencyData: () => Uint8Array
}

const STATE_COLORS: Record<VoiceState, number> = {
  idle: 0x63dcff,
  listening: 0x58f2d0,
  thinking: 0xa98cff,
  speaking: 0x8af7ff,
  awaiting: 0xffa765,
  success: 0x67e4b2,
  error: 0xff607c,
}

const MODEL_URL = `${import.meta.env.BASE_URL}models/emefa-canonical-face.obj`

// The bust dissolves into the projection instead of ending in a lit slab, and
// concave regions are dimmed by the baked occlusion term. Shared by the surface
// and by the grid, so both agree about where the face is in shadow.
const HOLOGRAM_COMMON = /* glsl */`
  float bodyFade(float height) { return mix(0.14, 1.0, smoothstep(-20.0, -8.0, height)); }
`

const SURFACE_VERTEX = /* glsl */`
  attribute float occlusion;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vLocal;
  varying float vOcclusion;
  void main() {
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-viewPosition.xyz);
    vLocal = position;
    vOcclusion = occlusion;
    gl_Position = projectionMatrix * viewPosition;
  }
`

// The surface is deliberately faint: it exists to give the grid something to
// wrap and to hide the far side of the head, not to become the face itself.
const SURFACE_FRAGMENT = /* glsl */`
  uniform vec3 uBase;
  uniform vec3 uGlow;
  uniform float uTime;
  uniform float uVoice;
  uniform float uOpacity;
  uniform float uRim;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vLocal;
  varying float vOcclusion;
  ${HOLOGRAM_COMMON}

  void main() {
    vec3 normal = normalize(vNormal);
    vec3 view = normalize(vView);
    float fresnel = pow(1.0 - max(dot(normal, view), 0.0), 2.3);

    vec3 key = normalize(vec3(-0.42, 0.62, 0.78));
    vec3 fill = normalize(vec3(0.76, -0.12, 0.52));
    float shade = max(dot(normal, key), 0.0) * 0.9 + max(dot(normal, fill), 0.0) * 0.3;
    float specular = pow(max(dot(normal, normalize(key + view)), 0.0), 26.0);

    float lines = 0.72 + 0.28 * sin(vLocal.y * 46.0 - uTime * 2.6);
    float shadow = mix(0.16, 1.0, vOcclusion);

    float alpha = (fresnel * uRim + shade * 0.42 + specular * 0.5 + 0.03) * lines * shadow;
    vec3 color = mix(uBase, uGlow, clamp(fresnel * 0.8 + shade * 0.6 + specular, 0.0, 1.0));
    gl_FragColor = vec4(color * (1.0 + uVoice * 0.4), alpha * uOpacity * bodyFade(vLocal.y));
  }
`

// One shader for every line in the hologram — grid, feature contours, brow
// tufts, hair. `strength` is baked per vertex: occlusion for the grid, a taper
// for the strands.
const LINE_VERTEX = /* glsl */`
  attribute float strength;
  attribute vec3 lineNormal;
  varying float vStrength;
  varying float vShade;
  varying vec3 vLocal;
  void main() {
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    vStrength = strength;
    vLocal = position;

    // Each line vertex carries the normal of the skin it was cut from, so the
    // grid is lit by the same key light as the surface. This is what makes the
    // mesh describe a nose, a brow and a lip instead of a smooth shell.
    vec3 normal = normalize(normalMatrix * lineNormal);
    vec3 view = normalize(-viewPosition.xyz);
    float key = max(dot(normal, normalize(vec3(-0.42, 0.62, 0.78))), 0.0);
    float rim = pow(1.0 - abs(dot(normal, view)), 2.0);
    vShade = 0.3 + key * 0.72 + rim * 0.55;

    gl_Position = projectionMatrix * viewPosition;
  }
`

const LINE_FRAGMENT = /* glsl */`
  uniform vec3 uBase;
  uniform vec3 uGlow;
  uniform float uOpacity;
  uniform float uShadow;
  varying float vStrength;
  varying float vShade;
  varying vec3 vLocal;
  ${HOLOGRAM_COMMON}

  void main() {
    float shaded = mix(uShadow, 1.0, vStrength) * vShade;
    gl_FragColor = vec4(mix(uBase, uGlow, clamp(vStrength * vShade, 0.0, 1.0)), uOpacity * shaded * bodyFade(vLocal.y));
  }
`

/** A real-time, locally rendered 3D holographic facial mesh. */
export function EMEFAFace({ state, onClick, getOutputVolume, getOutputFrequencyData }: EMEFAFaceProps) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef(state)
  const outputRef = useRef(getOutputVolume)
  const frequencyRef = useRef(getOutputFrequencyData)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { outputRef.current = getOutputVolume }, [getOutputVolume])
  useEffect(() => { frequencyRef.current = getOutputFrequencyData }, [getOutputFrequencyData])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' })
    } catch {
      buttonRef.current?.classList.add('wireframe-fallback')
      return
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const compact = window.innerWidth < 800
    renderer.outputColorSpace = THREE.SRGBColorSpace

    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(26, 1, .1, 40)
    camera.position.set(0, .06, 7.4)

    const bust = new THREE.Group()
    scene.add(bust)

    const uniforms = {
      uTime: { value: 0 },
      uBase: { value: new THREE.Color(0x2ea8e0) },
      uGlow: { value: new THREE.Color(0xbdf6ff) },
      uVoice: { value: 0 },
      uOpacity: { value: 1 },
      // Rim weight. Skin needs a strong fresnel to describe the silhouette, but
      // an eyeball does not: its rim is a full circle and the parts of it that
      // show through the canthi read as a ring drawn across the eye.
      uRim: { value: .34 },
    }

    const surface = (opacity: number, rim: number, side: THREE.Side = THREE.FrontSide) => new THREE.ShaderMaterial({
      uniforms: { ...uniforms, uOpacity: { value: opacity }, uRim: { value: rim } },
      vertexShader: SURFACE_VERTEX, fragmentShader: SURFACE_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side,
    })
    const lines = (opacity: number, shadow: number) => new THREE.ShaderMaterial({
      uniforms: { ...uniforms, uOpacity: { value: opacity }, uShadow: { value: shadow } },
      vertexShader: LINE_VERTEX, fragmentShader: LINE_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
    })

    const skinMaterial = surface(.3, .3)
    const cavityMaterial = surface(.1, .12)
    const globeMaterial = surface(.9, .05)
    const orbitMaterial = surface(.11, 0, THREE.BackSide)

    // Horizontal slices and vertical meridians: the grid that *is* the face.
    const latitudeMaterial = lines(.5, .2)
    const meridianMaterial = lines(.34, .22)
    // Lash line and vermilion border, kept faint — they exist because an
    // additive surface cannot render a lid margin, not to outline the face.
    const featureMaterial = lines(.95, .75)
    // Lash line and nose base, brighter than anything else on the face.
    const accentMaterial = lines(1.7, .9)
    const detailMaterial = lines(1, .7)
    const hairMaterial = lines(.34, .55)
    const landmarkMaterial = new THREE.PointsMaterial({
      color: 0xcaf8ff, size: .013, transparent: true, opacity: .4,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    })
    const irisMaterial = new THREE.MeshBasicMaterial({
      color: 0xbdf6ff, transparent: true, opacity: .62,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    })
    const catchlightMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: .8,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    })

    const rings = new THREE.Group()
    rings.rotation.x = 1.22
    rings.position.y = -2.2
    scene.add(rings)
    const ringMaterials: THREE.MeshBasicMaterial[] = []
    ;[1.05, 1.38, 1.72].forEach((radius, index) => {
      const material = new THREE.MeshBasicMaterial({
        color: index === 1 ? 0x9ff8ff : 0x3acfff, transparent: true,
        opacity: .52 - index * .1, blending: THREE.AdditiveBlending,
      })
      ringMaterials.push(material)
      rings.add(new THREE.Mesh(new THREE.TorusGeometry(radius, index === 1 ? .012 : .006, 5, 100), material))
    })

    type Grid = { plan: ReturnType<typeof planIsoLines>; attribute: THREE.BufferAttribute }
    type Head = {
      geometry: THREE.BufferGeometry
      surfacePositions: THREE.BufferAttribute
      level: ReturnType<typeof buildSubdivisionLevel>
      rig: ReturnType<typeof buildFaceRig>
      skin: ReturnType<typeof buildFemaleHead>['skin']
      base: Float32Array
      faceDeformed: Float32Array
      deformed: Float32Array
      smooth: Float32Array
      grids: Grid[]
      detail: ReturnType<typeof buildFaceDetail>
      detailPositions: THREE.BufferAttribute
      eyes: THREE.Group[]
      restAperture: number
      cavity: THREE.ShaderMaterial
    }
    let head: Head | null = null
    let disposed = false

    const controller = new AbortController()
    fetch(MODEL_URL, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.text()
      })
      .then((text) => {
        if (disposed) return
        head = assembleHead(text)
      })
      .catch(() => {
        // The hologram is decorative; the button stays usable without it.
        if (!disposed) buttonRef.current?.classList.add('wireframe-fallback')
      })

    function assembleHead(objectText: string): Head {
      const canonical = parseCanonicalFaceObj(objectText)
      const rest = feminizeFace(canonical.positions)
      const build = buildFemaleHead(canonical, rest)
      const rig = buildFaceRig(rest)
      const detail = buildFaceDetail()

      // Smooth the head once, as a reusable linear operator. The grid is cut
      // from the result, so its lines follow curves instead of tracing the
      // landmark model's facets — which is what made the earlier face read as
      // low-poly however good the proportions were.
      const level = buildSubdivisionLevel(build.vertexCount, build.indices)
      const baseSmooth = new Float32Array(level.vertexCount * 3)
      applySubdivision(level, build.basePositions, baseSmooth)

      const restNormals = computeNormals(baseSmooth, level.indices)
      // Occlusion is quadratic in vertex count, so it is baked on the *base*
      // mesh and pushed through the subdivision operator — which is exactly
      // what a linear operator is for. Baking it on the smoothed mesh instead
      // costs four times as many vertices for a term that is low-frequency
      // anyway, and shows up as a visible hitch on load.
      const occlusion = new Float32Array(level.vertexCount)
      applySubdivision(level, bakeOcclusion(
        build.basePositions,
        computeNormals(build.basePositions, build.indices),
        3,
      ), occlusion, 1)

      // The grid stops at the hairline and hands over to the hair strands; the
      // surface only dims there, so the skull keeps its volume.
      const mask = scalpMask(baseSmooth)
      const gridShade = occlusion.map((value, vertex) => value * (0.06 + 0.94 * mask[vertex]))
      const surfaceShade = occlusion.map((value, vertex) => value * (0.4 + 0.6 * mask[vertex]))

      const faceDeformed = new Float32Array(rest)
      const deformed = new Float32Array(build.basePositions)
      const smooth = new Float32Array(baseSmooth)

      const model = new THREE.Group()
      model.scale.setScalar(build.scale)
      model.position.y = .64
      bust.add(model)

      const geometry = new THREE.BufferGeometry()
      const surfacePositions = new THREE.BufferAttribute(smooth, 3)
      surfacePositions.setUsage(THREE.DynamicDrawUsage)
      geometry.setAttribute('position', surfacePositions)
      geometry.setAttribute('occlusion', new THREE.BufferAttribute(surfaceShade, 1))
      geometry.setIndex(new THREE.BufferAttribute(level.indices, 1))
      // Subdivision quadruples every triangle, so the cavity range scales with it.
      geometry.addGroup(0, build.cavityIndexStart * 4, 0)
      geometry.addGroup(build.cavityIndexStart * 4, build.cavityIndexCount * 4, 1)
      geometry.computeVertexNormals()

      // Depth-only pass, nudged away from the camera so the additive skin and
      // the grid it carries still pass the depth test. Without it the far side
      // of the head shows through the near side and the volume disappears.
      const occluder = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
        colorWrite: false, depthWrite: true, side: THREE.FrontSide,
        polygonOffset: true, polygonOffsetFactor: 1.4, polygonOffsetUnits: 1.4,
      }))
      occluder.renderOrder = -1
      model.add(occluder)
      model.add(new THREE.Mesh(geometry, [skinMaterial, cavityMaterial]))

      // --- The grid ----------------------------------------------------------
      let crown = -Infinity
      for (let vertex = 0; vertex < level.vertexCount; vertex += 1) {
        crown = Math.max(crown, baseSmooth[vertex * 3 + 1])
      }
      const grids: Grid[] = []
      const addGrid = (plan: ReturnType<typeof planIsoLines>, material: THREE.ShaderMaterial) => {
        const lineGeometry = new THREE.BufferGeometry()
        const attribute = new THREE.BufferAttribute(new Float32Array(plan.segmentCount * 6), 3)
        attribute.setUsage(THREE.DynamicDrawUsage)
        lineGeometry.setAttribute('position', attribute)
        lineGeometry.setAttribute('strength', new THREE.BufferAttribute(bakeIsoScalar(plan, gridShade), 1))
        lineGeometry.setAttribute('lineNormal', new THREE.BufferAttribute(bakeIsoVector(plan, restNormals), 3))
        model.add(new THREE.LineSegments(lineGeometry, material))
        grids.push({ plan, attribute })
      }
      addGrid(
        planIsoLines(level.indices, heightField(baseSmooth), evenLevels(-13, crown, compact ? 26 : 40)),
        latitudeMaterial,
      )
      addGrid(
        planIsoLines(
          level.indices,
          azimuthField(baseSmooth, SKULL_CENTRE[2]),
          evenLevels(-Math.PI, Math.PI, compact ? 30 : 46),
          true,
        ),
        meridianMaterial,
      )

      // Lash line and vermilion border index the shared vertex buffer, so they
      // blink and speak with the skin at no extra cost.
      const contourLines = (indices: Uint32Array, material: THREE.ShaderMaterial) => {
        const lineGeometry = new THREE.BufferGeometry()
        lineGeometry.setAttribute('position', surfacePositions)
        lineGeometry.setAttribute('lineNormal', new THREE.BufferAttribute(restNormals, 3))
        lineGeometry.setAttribute('strength', new THREE.BufferAttribute(occlusion, 1))
        lineGeometry.setIndex(new THREE.BufferAttribute(indices, 1))
        model.add(new THREE.LineSegments(lineGeometry, material))
      }
      contourLines(loopEdges(FEATURE_LOOPS), featureMaterial)
      contourLines(chainEdges(FEATURE_CHAINS), featureMaterial)
      contourLines(chainEdges(ACCENT_CHAINS), accentMaterial)

      // Landmark points, drawn only on the 468 canonical vertices: the mesh's
      // actual anatomical anchors rather than every subdivided corner.
      const landmarkGeometry = new THREE.BufferGeometry()
      landmarkGeometry.setAttribute('position', surfacePositions)
      landmarkGeometry.setIndex(new THREE.BufferAttribute(
        Uint32Array.from({ length: 468 }, (_, index) => index), 1,
      ))
      model.add(new THREE.Points(landmarkGeometry, landmarkMaterial))

      // --- Brow tufts and lid creases ----------------------------------------
      const detailGeometry = new THREE.BufferGeometry()
      const detailPositions = new THREE.BufferAttribute(new Float32Array(detail.endpointCount * 3), 3)
      detailPositions.setUsage(THREE.DynamicDrawUsage)
      detailGeometry.setAttribute('position', detailPositions)
      detailGeometry.setAttribute('strength', new THREE.BufferAttribute(detail.fade, 1))
      detailGeometry.setAttribute('lineNormal', flatNormals(detail.endpointCount))
      model.add(new THREE.LineSegments(detailGeometry, detailMaterial))

      // --- Eyes --------------------------------------------------------------
      const eyeGroups = build.eyes.map((eye) => {
        const group = new THREE.Group()
        group.position.set(eye.centre[0], eye.centre[1], eye.centre[2])

        // Orbit shell: an inverted sphere that contains the globe. The sockets
        // were carved out of the mesh so an eyeball could sit behind them,
        // which left the canthi looking straight through the skull. It is
        // flattened along the view axis so it stays *behind* the skin around
        // the orbit — a round shell of this width breaks the surface and draws
        // a bright intersection ellipse right across the eye.
        const orbitGeometry = withUnitOcclusion(new THREE.SphereGeometry(eye.radius * 1.24, 18, 12))
        for (const material of [orbitMaterial, new THREE.MeshBasicMaterial({
          colorWrite: false, depthWrite: true, side: THREE.BackSide,
        })]) {
          const shell = new THREE.Mesh(orbitGeometry, material)
          shell.scale.set(1, 1, .58)
          group.add(shell)
        }

        const globeGeometry = withUnitOcclusion(new THREE.SphereGeometry(eye.radius, 22, 16))
        group.add(new THREE.Mesh(globeGeometry, globeMaterial))
        group.add(new THREE.Mesh(globeGeometry, new THREE.MeshBasicMaterial({
          colorWrite: false, depthWrite: true,
          polygonOffset: true, polygonOffsetFactor: 1.4, polygonOffsetUnits: 1.4,
        })))

        // Iris as an annulus: the empty middle is the pupil, which is the only
        // way to get a dark centre out of an additively blended hologram.
        const iris = new THREE.Mesh(new THREE.RingGeometry(eye.radius * .24, eye.radius * .58, 32), irisMaterial)
        iris.position.z = eye.radius * .94
        group.add(iris)
        // A single specular highlight, offset towards the key light. Nothing
        // else so cheaply makes an eye look wet and alive.
        const catchlight = new THREE.Mesh(new THREE.CircleGeometry(eye.radius * .075, 10), catchlightMaterial)
        catchlight.position.set(-eye.radius * .2, eye.radius * .24, eye.radius * .96)
        group.add(catchlight)

        // Resting orientation is stored as Euler angles rather than applied via
        // lookAt: assigning `rotation.y` for the gaze each frame regenerates the
        // quaternion and would silently discard a lookAt.
        group.userData.restYaw = Math.atan2(eye.forward[0], eye.forward[2])
        group.userData.restPitch = -Math.asin(eye.forward[1])
        model.add(group)
        return group
      })

      const hair = buildHairStrands(compact ? 190 : 340)
      const hairGeometry = new THREE.BufferGeometry()
      hairGeometry.setAttribute('position', new THREE.BufferAttribute(hair.positions, 3))
      // Roots read as solid mass, tips dissolve into the projection.
      hairGeometry.setAttribute('strength', new THREE.BufferAttribute(
        hair.fade.map((value) => 1 - value * 0.85), 1,
      ))
      hairGeometry.setAttribute('lineNormal', flatNormals(hair.fade.length))
      model.add(new THREE.LineSegments(hairGeometry, hairMaterial))

      return {
        geometry, surfacePositions, level, rig,
        skin: build.skin, base: build.basePositions,
        faceDeformed, deformed, smooth,
        grids, detail, detailPositions,
        eyes: eyeGroups,
        restAperture: mouthAperture(rest),
        cavity: cavityMaterial,
      }
    }

    /** Forward-facing normals for lines that are not cut from the skin. */
    function flatNormals(count: number) {
      const normals = new Float32Array(count * 3)
      for (let vertex = 0; vertex < count; vertex += 1) normals[vertex * 3 + 2] = 1
      return new THREE.BufferAttribute(normals, 3)
    }

    /** The surface shader reads an occlusion attribute; eyeballs have none. */
    function withUnitOcclusion(geometry: THREE.BufferGeometry) {
      const count = geometry.getAttribute('position').count
      geometry.setAttribute('occlusion', new THREE.BufferAttribute(new Float32Array(count).fill(1), 1))
      return geometry
    }

    // --- Sizing ---------------------------------------------------------------
    const resize = () => {
      const width = canvas.clientWidth || 300
      const height = canvas.clientHeight || 330
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8))
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    resize()

    const pointerTarget = new THREE.Vector2()
    const handlePointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointerTarget.set((event.clientX - rect.left) / rect.width - .5, (event.clientY - rect.top) / rect.height - .5)
    }
    const handlePointerLeave = () => pointerTarget.set(0, 0)
    canvas.addEventListener('pointermove', handlePointerMove, { passive: true })
    canvas.addEventListener('pointerleave', handlePointerLeave)

    // A lost context leaves a frozen canvas; stop the loop and restore on demand.
    let contextLost = false
    const handleContextLost = (event: Event) => { event.preventDefault(); contextLost = true }
    const handleContextRestored = () => { contextLost = false; resize() }
    canvas.addEventListener('webglcontextlost', handleContextLost)
    canvas.addEventListener('webglcontextrestored', handleContextRestored)

    // --- Animation ------------------------------------------------------------
    const clock = new THREE.Clock()
    const color = new THREE.Color()
    const gaze = new THREE.Vector2()
    const viseme = createVisemeState()
    const expression: Expression = {
      jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0,
      smile: 0, browRaise: 0, blinkLeft: 0, blinkRight: 0, squint: 0,
    }
    let blinkAt = 2.4
    let blinkStart = -10
    let doubleBlink = false
    let smoothSmile = 0
    let smoothBrow = 0
    let frame = 0

    const readVolume = () => {
      try { return Math.min(1, Math.max(0, outputRef.current())) } catch { return 0 }
    }
    const readSpectrum = () => {
      try { return frequencyRef.current() } catch { return EMPTY_SPECTRUM }
    }

    const animate = () => {
      frame = requestAnimationFrame(animate)
      const delta = Math.min(clock.getDelta(), .1)
      const elapsed = clock.getElapsedTime()
      if (contextLost || document.hidden) return

      const currentState = stateRef.current
      const speaking = currentState === 'speaking'
      const level = speaking ? readVolume() : 0
      advanceVisemes(viseme, speaking ? visemeTargets(readSpectrum(), level) : ZERO_TARGETS, level, delta)
      buttonRef.current?.style.setProperty('--voice-level', viseme.level.toFixed(3))
      uniforms.uTime.value = elapsed
      uniforms.uVoice.value = viseme.level

      // --- Head attitude ------------------------------------------------------
      const motion = reducedMotion ? .25 : 1
      const targetYaw = (Math.sin(elapsed * .38) * .13 + Math.sin(elapsed * .17) * .05) * motion + pointerTarget.x * .5
      const targetPitch = (Math.sin(elapsed * .27) * .035) * motion - pointerTarget.y * .22
      bust.rotation.y += (targetYaw - bust.rotation.y) * Math.min(1, delta * 2.4)
      bust.rotation.x += (targetPitch - bust.rotation.x) * Math.min(1, delta * 2.4)
      // Breathing, slightly deeper while listening.
      bust.position.y = Math.sin(elapsed * (currentState === 'listening' ? 1.05 : .8)) * .018 * motion
      bust.rotation.z = Math.sin(elapsed * .23) * .018 * motion

      // --- Blinking -----------------------------------------------------------
      // Humans blink every 3–6 s, close in ~80 ms and open in ~160 ms, and
      // double-blink often enough that a perfectly regular loop looks wrong.
      if (elapsed > blinkAt) {
        blinkStart = elapsed
        doubleBlink = hash01(Math.floor(elapsed * 13)) < .22
        blinkAt = elapsed + (doubleBlink ? .34 : 0) + 2.6 + hash01(Math.floor(elapsed * 7) + 1) * 3.6
      }
      const blinkAmount = (delay: number) => {
        const since = elapsed - blinkStart - delay
        if (since < 0 || since > .24) return 0
        return since < .08 ? since / .08 : 1 - (since - .08) / .16
      }
      // A lid that lags its partner by a frame or two is what stops a blink
      // reading as a shutter closing.
      const blinkOf = (delay: number) => {
        const single = blinkAmount(delay)
        return Math.max(0, Math.min(1, doubleBlink ? Math.max(single, blinkAmount(delay + .24)) : single))
      }
      expression.blinkLeft = blinkOf(0)
      expression.blinkRight = blinkOf(.014)

      // --- Expression ---------------------------------------------------------
      const targetSmile = currentState === 'success' ? .62 : currentState === 'listening' ? .17 : currentState === 'error' ? -.12 : .08
      const targetBrow = currentState === 'thinking' ? .55 : currentState === 'listening' ? .26 : currentState === 'awaiting' ? .42 : viseme.jawOpen * .12
      smoothSmile += (targetSmile - smoothSmile) * Math.min(1, delta * 3)
      smoothBrow += (targetBrow - smoothBrow) * Math.min(1, delta * 3.4)
      expression.smile = smoothSmile
      expression.browRaise = smoothBrow
      expression.squint = Math.max(0, smoothSmile) * .5
      expression.jawOpen = viseme.jawOpen
      expression.lipRound = viseme.lipRound
      expression.lipWide = viseme.lipWide
      expression.lipPress = viseme.lipPress

      if (head) {
        applyExpression(head.rig, expression, head.faceDeformed)
        applySkin(head.base, head.faceDeformed, head.skin, head.deformed)
        applySubdivision(head.level, head.deformed, head.smooth)
        head.surfacePositions.needsUpdate = true
        head.geometry.computeVertexNormals()

        for (const grid of head.grids) {
          evaluateIsoLines(grid.plan, head.smooth, grid.attribute.array as Float32Array)
          grid.attribute.needsUpdate = true
        }
        // Brow tufts and lid creases read the *smoothed* landmarks, so they sit
        // on the surface the grid describes rather than on the raw model.
        evaluateFaceDetail(head.detail, head.smooth, head.detailPositions.array as Float32Array)
        head.detailPositions.needsUpdate = true

        // The oral cavity only exists visually while the mouth is actually open.
        const aperture = mouthAperture(head.faceDeformed) - head.restAperture
        head.cavity.uniforms.uOpacity.value = .04 + smoothstep(0, 2.6, aperture) * .2

        // --- Gaze -------------------------------------------------------------
        // Small, held saccades plus a slow drift; a perfectly steady eye is the
        // fastest way back into the uncanny valley.
        const saccade = Math.floor(elapsed * .9)
        const targetGazeX = (hash01(saccade) - .5) * .5 + pointerTarget.x * 1.4
        const targetGazeY = (hash01(saccade + 91) - .5) * .28 - pointerTarget.y * .7
          + (currentState === 'thinking' ? .35 : 0)
        gaze.x += (targetGazeX - gaze.x) * Math.min(1, delta * 9)
        gaze.y += (targetGazeY - gaze.y) * Math.min(1, delta * 9)
        for (const eye of head.eyes) {
          eye.rotation.set(
            (eye.userData.restPitch as number) - gaze.y * .18,
            (eye.userData.restYaw as number) + gaze.x * .22,
            0,
          )
        }
      }

      // --- Palette ------------------------------------------------------------
      color.setHex(STATE_COLORS[currentState])
      uniforms.uGlow.value.lerp(color, Math.min(1, delta * 2.2))
      landmarkMaterial.color.lerp(color, Math.min(1, delta * 1.6))
      irisMaterial.color.lerp(color, Math.min(1, delta * 1.6))
      latitudeMaterial.uniforms.uOpacity.value = .48 + viseme.level * .2
      meridianMaterial.uniforms.uOpacity.value = .33 + viseme.level * .14
      landmarkMaterial.opacity = .34 + viseme.level * .18
      rings.rotation.z = elapsed * .11 * motion
      rings.scale.setScalar(1 + viseme.level * .055)
      ringMaterials.forEach((material, index) => { material.opacity = (.52 - index * .1) * (.8 + viseme.level * .3) })

      // Occasional projection dropout, timed rather than frame-counted so it
      // does not speed up on a 120 Hz display.
      uniforms.uOpacity.value = Math.sin(elapsed * 31) > .9993 ? .25 : 1

      renderer.render(scene, camera)
    }
    animate()

    return () => {
      disposed = true
      controller.abort()
      cancelAnimationFrame(frame)
      observer.disconnect()
      canvas.removeEventListener('pointermove', handlePointerMove)
      canvas.removeEventListener('pointerleave', handlePointerLeave)
      canvas.removeEventListener('webglcontextlost', handleContextLost)
      canvas.removeEventListener('webglcontextrestored', handleContextRestored)
      const releasedGeometries = new Set<THREE.BufferGeometry>()
      const releasedMaterials = new Set<THREE.Material>()
      scene.traverse((object) => {
        if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points)) return
        if (!releasedGeometries.has(object.geometry)) {
          releasedGeometries.add(object.geometry)
          object.geometry.dispose()
        }
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          if (releasedMaterials.has(material)) continue
          releasedMaterials.add(material)
          material.dispose()
        }
      })
      renderer.dispose()
    }
  }, [])

  const active = state !== 'idle' && state !== 'error'
  return (
    <button
      ref={buttonRef}
      className={`emefa-face state-${state}`}
      onClick={onClick}
      aria-label={state === 'idle' ? 'Démarrer une conversation vocale avec EMEFA' : 'Arrêter la conversation vocale avec EMEFA'}
    >
      <span className="emefa-projection-cone" aria-hidden="true" />
      <span className="emefa-holo-ring ring-outer" aria-hidden="true" />
      <span className="emefa-holo-ring ring-inner" aria-hidden="true" />
      <canvas ref={canvasRef} className="emefa-wireframe-canvas" role="img" aria-label={`Visage holographique 3D d’EMEFA — ${state}`} />
      <span className="emefa-scan-beam" aria-hidden="true" />
      <span className="emefa-holo-glitch" aria-hidden="true" />
      <span className="emefa-hud-data data-left" aria-hidden="true"><b>FACIAL MESH</b><i /><i /><i /><small>3D · LIVE</small></span>
      <span className="emefa-hud-data data-right" aria-hidden="true"><b>VOICE SYNC</b><span className="emefa-voice-bars"><i /><i /><i /><i /><i /></span><small>{active ? 'ONLINE' : 'STANDBY'}</small></span>
      <span className="emefa-face-name">EMEFA // HOLOGRAPHIC ENTITY</span>
      <span className="emefa-face-signal">{active ? '● LIAISON ACTIVE' : 'TOUCHER POUR PARLER'}</span>
    </button>
  )
}

const EMPTY_SPECTRUM = new Uint8Array()
const ZERO_TARGETS = { jawOpen: 0, lipRound: 0, lipWide: 0, lipPress: 0 }
