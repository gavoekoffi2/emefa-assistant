import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { VoiceState } from './App'
import { FEATURE_LOOPS, loopEdges, parseCanonicalFaceObj } from './face/canonicalFace.ts'
import { applySkin, buildFemaleHead, feminizeFace, hash01, smoothstep, uniqueEdges } from './face/femaleHead.ts'
import { applyExpression, buildFaceRig, mouthAperture } from './face/faceRig.ts'
import type { Expression } from './face/faceRig.ts'
import { buildHairStrands } from './face/hair.ts'
import { evaluateContours, planContours } from './face/contours.ts'
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

const HOLOGRAM_VERTEX = /* glsl */`
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vLocal;
  void main() {
    vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
    vNormal = normalize(normalMatrix * normal);
    vView = normalize(-viewPosition.xyz);
    vLocal = position;
    gl_Position = projectionMatrix * viewPosition;
  }
`

// Rim light plus a soft key is what actually renders the face readable: on an
// additively blended surface a flat fill would collapse the nose, the brow and
// the lips into a single glowing blob.
const HOLOGRAM_FRAGMENT = /* glsl */`
  uniform vec3 uBase;
  uniform vec3 uGlow;
  uniform float uTime;
  uniform float uVoice;
  uniform float uOpacity;
  uniform float uRim;
  varying vec3 vNormal;
  varying vec3 vView;
  varying vec3 vLocal;

  void main() {
    vec3 normal = normalize(vNormal);
    vec3 view = normalize(vView);
    float facing = max(dot(normal, view), 0.0);
    float fresnel = pow(1.0 - facing, 2.3);

    vec3 key = normalize(vec3(-0.42, 0.62, 0.78));
    vec3 fill = normalize(vec3(0.76, -0.12, 0.52));
    float shade = max(dot(normal, key), 0.0) * 0.95 + max(dot(normal, fill), 0.0) * 0.34;

    // Fine projection scanlines, plus one slow bright sweep travelling upward.
    float lines = 0.66 + 0.34 * sin(vLocal.y * 46.0 - uTime * 2.6);
    float sweep = smoothstep(0.72, 1.0, sin(vLocal.y * 0.22 - uTime * 0.5));

    // The bust dissolves into the projection instead of ending in a lit slab.
    // A fully lit torso is the fastest way to turn a person back into a mannequin.
    float body = smoothstep(-20.0, -8.0, vLocal.y);

    // Weighted towards the shading term: the fresnel silhouette alone gives a
    // glowing outline with a featureless middle, which is what flattened the
    // previous face into a mask.
    float alpha = ((fresnel * uRim + shade * 0.55 + 0.03) * mix(0.72, 1.0, lines) + sweep * 0.08) * mix(0.16, 1.0, body);
    vec3 color = mix(uBase, uGlow, clamp(fresnel * 0.85 + shade * 0.55, 0.0, 1.0));
    gl_FragColor = vec4(color * (1.0 + uVoice * 0.4), alpha * uOpacity);
  }
`

const HAIR_VERTEX = /* glsl */`
  attribute float fade;
  varying float vFade;
  void main() {
    vFade = fade;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const HAIR_FRAGMENT = /* glsl */`
  uniform vec3 uBase;
  uniform vec3 uGlow;
  uniform float uOpacity;
  varying float vFade;
  void main() {
    // Roots read as solid mass, tips dissolve into the projection.
    float strength = (1.0 - vFade * 0.82) * uOpacity;
    gl_FragColor = vec4(mix(uGlow, uBase, vFade), strength);
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
      uRim: { value: .4 },
    }
    const hairUniforms = {
      uBase: { value: uniforms.uBase.value },
      uGlow: { value: uniforms.uGlow.value },
      uOpacity: { value: .34 },
    }

    const skinMaterial = new THREE.ShaderMaterial({
      uniforms, vertexShader: HOLOGRAM_VERTEX, fragmentShader: HOLOGRAM_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.FrontSide,
    })
    // The oral cavity uses the same shading at a fraction of the intensity, so
    // an open mouth reads as a recess instead of glowing like the lips.
    const cavityMaterial = skinMaterial.clone()
    cavityMaterial.uniforms = { ...uniforms, uOpacity: { value: .1 }, uRim: { value: .12 } }

    const globeMaterial = new THREE.ShaderMaterial({
      uniforms: { ...uniforms, uOpacity: { value: .62 }, uRim: { value: .05 } },
      vertexShader: HOLOGRAM_VERTEX, fragmentShader: HOLOGRAM_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.FrontSide,
    })
    const orbitMaterial = new THREE.ShaderMaterial({
      uniforms: { ...uniforms, uOpacity: { value: .11 }, uRim: { value: 0 } },
      vertexShader: HOLOGRAM_VERTEX, fragmentShader: HOLOGRAM_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.BackSide,
    })
    const wireMaterial = new THREE.LineBasicMaterial({
      color: 0x8ceaff, transparent: true, opacity: .055,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    // Lash line, brows and vermilion border. Bright, because these are the
    // contours a viewer reads a face from.
    const featureMaterial = new THREE.LineBasicMaterial({
      color: 0xcaf8ff, transparent: true, opacity: .4,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const contourMaterial = new THREE.LineBasicMaterial({
      color: 0x7fe8ff, transparent: true, opacity: .22,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const pointMaterial = new THREE.PointsMaterial({
      color: 0xa9f4ff, size: .011, transparent: true, opacity: .3,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    })
    const irisMaterial = new THREE.MeshBasicMaterial({
      color: 0x9ff4ff, transparent: true, opacity: .4,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    })
    const catchlightMaterial = new THREE.MeshBasicMaterial({
      color: 0xffffff, transparent: true, opacity: .8,
      blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
    })
    const hairMaterial = new THREE.ShaderMaterial({
      uniforms: hairUniforms, vertexShader: HAIR_VERTEX, fragmentShader: HAIR_FRAGMENT,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
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

    // --- Head assembly, once the landmark model has loaded --------------------
    type Head = {
      positions: THREE.BufferAttribute
      geometry: THREE.BufferGeometry
      deformed: Float32Array
      faceDeformed: Float32Array
      rig: ReturnType<typeof buildFaceRig>
      skin: ReturnType<typeof buildFemaleHead>['skin']
      base: Float32Array
      contourPlan: ReturnType<typeof planContours>
      contourPositions: THREE.BufferAttribute
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

      const deformed = new Float32Array(build.basePositions)
      const faceDeformed = new Float32Array(rest)

      const geometry = new THREE.BufferGeometry()
      const positions = new THREE.BufferAttribute(deformed, 3)
      positions.setUsage(THREE.DynamicDrawUsage)
      geometry.setAttribute('position', positions)
      geometry.setIndex(new THREE.BufferAttribute(build.indices, 1))
      geometry.addGroup(0, build.cavityIndexStart, 0)
      geometry.addGroup(build.cavityIndexStart, build.cavityIndexCount, 1)
      geometry.computeVertexNormals()

      const model = new THREE.Group()
      model.scale.setScalar(build.scale)
      model.position.y = .64
      bust.add(model)

      // Depth-only pass, nudged away from the camera so the additive skin it is
      // protecting still passes the depth test. Without it the far side of the
      // head shows through the near side and the volume disappears.
      const occluder = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({
        colorWrite: false, depthWrite: true, side: THREE.FrontSide,
        polygonOffset: true, polygonOffsetFactor: 1.4, polygonOffsetUnits: 1.4,
      }))
      occluder.renderOrder = -1
      model.add(occluder)

      model.add(new THREE.Mesh(geometry, [skinMaterial, cavityMaterial]))
      // Wireframe over the face only. Running it across the cranium, neck and
      // bust too turned the whole bust into a uniform net that read as fabric
      // rather than as skin, and buried the shading that describes the features.
      model.add(new THREE.LineSegments(
        new THREE.BufferGeometry()
          .setAttribute('position', positions)
          .setIndex(new THREE.BufferAttribute(uniqueEdges(build.indices.subarray(0, build.faceIndexCount)), 1)),
        wireMaterial,
      ))
      if (!compact) {
        // Points get their own unindexed view of the same buffer so each vertex
        // is drawn once rather than once per adjacent triangle.
        const pointGeometry = new THREE.BufferGeometry()
        pointGeometry.setAttribute('position', positions)
        model.add(new THREE.Points(pointGeometry, pointMaterial))
      }

      // Lash line, brows and vermilion border, indexed into the shared vertex
      // buffer so they blink and speak with the skin at no extra cost.
      model.add(new THREE.LineSegments(
        new THREE.BufferGeometry()
          .setAttribute('position', positions)
          .setIndex(new THREE.BufferAttribute(loopEdges(FEATURE_LOOPS), 1)),
        featureMaterial,
      ))

      // Contours are planned against the rest pose and re-evaluated per frame,
      // so they follow the jaw instead of sliding over it.
      const contourPlan = planContours(build.basePositions, build.indices, compact ? 16 : 22, -11, 10.4)
      const contourGeometry = new THREE.BufferGeometry()
      const contourPositions = new THREE.BufferAttribute(new Float32Array(contourPlan.segmentCount * 6), 3)
      contourPositions.setUsage(THREE.DynamicDrawUsage)
      contourGeometry.setAttribute('position', contourPositions)
      model.add(new THREE.LineSegments(contourGeometry, contourMaterial))

      // --- Eyes --------------------------------------------------------------
      const eyeGroups = build.eyes.map((eye) => {
        const group = new THREE.Group()
        group.position.set(eye.centre[0], eye.centre[1], eye.centre[2])
        // Orbit shell: an inverted sphere that fully contains the globe. The
        // sockets were carved out of the mesh so an eyeball could sit behind
        // them, which left the canthi looking straight through the skull. A
        // cone into the orbit does not work — the globe pokes out through its
        // walls and rings the eye. Real eye corners are dark; what breaks the
        // illusion is seeing the *background* through them, not the shadow.
        const orbitGeometry = new THREE.SphereGeometry(eye.radius * 1.24, 18, 12)
        // Flattened along the view axis so the shell stays *behind* the skin
        // around the orbit. A round shell of this width breaks the surface and
        // draws a bright intersection ellipse right across the eye.
        const orbitScale = new THREE.Vector3(1, 1, .58)
        for (const material of [orbitMaterial, new THREE.MeshBasicMaterial({
          colorWrite: false, depthWrite: true, side: THREE.BackSide,
        })]) {
          const shell = new THREE.Mesh(orbitGeometry, material)
          shell.scale.copy(orbitScale)
          group.add(shell)
        }

        const globeGeometry = new THREE.SphereGeometry(eye.radius, 22, 16)
        const globe = new THREE.Mesh(globeGeometry, globeMaterial)
        group.add(globe)
        // Depth for the globe too, so wireframe behind the socket stays hidden.
        const globeDepth = new THREE.Mesh(globeGeometry, new THREE.MeshBasicMaterial({
          colorWrite: false, depthWrite: true,
          polygonOffset: true, polygonOffsetFactor: 1.4, polygonOffsetUnits: 1.4,
        }))
        group.add(globeDepth)

        // Iris as an annulus: the empty middle is the pupil, which is the only
        // way to get a dark centre out of an additively blended hologram.
        const iris = new THREE.Mesh(new THREE.RingGeometry(eye.radius * .26, eye.radius * .54, 30), irisMaterial)
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

      const hair = buildHairStrands(compact ? 108 : 168)
      const hairGeometry = new THREE.BufferGeometry()
      hairGeometry.setAttribute('position', new THREE.BufferAttribute(hair.positions, 3))
      hairGeometry.setAttribute('fade', new THREE.BufferAttribute(hair.fade, 1))
      model.add(new THREE.LineSegments(hairGeometry, hairMaterial))

      return {
        positions, geometry, deformed, faceDeformed, rig,
        skin: build.skin, base: build.basePositions,
        contourPlan, contourPositions, eyes: eyeGroups,
        restAperture: mouthAperture(rest),
        cavity: cavityMaterial,
      }
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
      const breath = Math.sin(elapsed * (currentState === 'listening' ? 1.05 : .8)) * .018 * motion
      bust.position.y = breath
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
        head.positions.needsUpdate = true
        head.geometry.computeVertexNormals()
        evaluateContours(head.contourPlan, head.deformed, head.contourPositions.array as Float32Array)
        head.contourPositions.needsUpdate = true

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
      wireMaterial.color.lerp(color, Math.min(1, delta * 1.8))
      contourMaterial.color.lerp(color, Math.min(1, delta * 1.8))
      pointMaterial.color.lerp(color, Math.min(1, delta * 1.6))
      irisMaterial.color.lerp(color, Math.min(1, delta * 1.6))
      featureMaterial.color.lerp(color, Math.min(1, delta * .9))
      contourMaterial.opacity = .2 + viseme.level * .14
      pointMaterial.opacity = .26 + viseme.level * .18
      hairUniforms.uOpacity.value = .3 + viseme.level * .1
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
