import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { VoiceState } from './App'
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

type ProfilePoint = readonly [number, number]

function interpolateProfile(y: number, profile: readonly ProfilePoint[]) {
  if (y <= profile[0][0]) return profile[0][1]
  for (let index = 1; index < profile.length; index += 1) {
    const [nextY, nextValue] = profile[index]
    const [previousY, previousValue] = profile[index - 1]
    if (y <= nextY) {
      const progress = (y - previousY) / (nextY - previousY)
      const eased = progress * progress * (3 - 2 * progress)
      return THREE.MathUtils.lerp(previousValue, nextValue, eased)
    }
  }
  return profile[profile.length - 1][1]
}

// Human female proportions: a visibly elongated skull, broad forehead and
// cheekbones, a soft jaw, and a rounded crown. The final cap closes above the
// visible contour lines so the forehead never converges into a pineapple point.
const HEAD_BOTTOM = -1.6
const HEAD_CROWN = 1.95
const VISIBLE_CROWN = 1.82
// Claude requested a clearly broader face while preserving the approved height.
// Separate multipliers keep cranial width and facial features proportional.
const HEAD_WIDTH_SCALE = 1.55
const FEATURE_WIDTH_SCALE = 1.45
const HEAD_WIDTH_PROFILE: readonly ProfilePoint[] = [
  [-1.6, .3], [-1.46, .44], [-1.2, .62], [-.82, .74],
  [-.38, .84], [.02, .9], [.38, .88], [.72, .88],
  [1.1, .84], [1.45, .76], [1.72, .6], [1.9, .27], [1.95, .08],
]

const FACE_DEPTH_PROFILE: readonly ProfilePoint[] = [
  [-1.6, .4], [-1.3, .57], [-.78, .71], [-.25, .8],
  [.18, .75], [.68, .71], [1.15, .66], [1.55, .54], [1.82, .34], [1.95, .1],
]

const REAR_DEPTH_PROFILE: readonly ProfilePoint[] = [
  [-1.6, .35], [-1.22, .53], [-.55, .67], [.18, .76],
  [.8, .82], [1.28, .76], [1.62, .59], [1.84, .34], [1.95, .1],
]

function headPoint(y: number, angle: number) {
  const width = interpolateProfile(y, HEAD_WIDTH_PROFILE)
  const facing = Math.cos(angle)
  const depth = interpolateProfile(y, facing >= 0 ? FACE_DEPTH_PROFILE : REAR_DEPTH_PROFILE)
  return new THREE.Vector3(
    Math.sin(angle) * width * HEAD_WIDTH_SCALE,
    y,
    facing * depth - .06,
  )
}

function curve(points: THREE.Vector3[], material: THREE.Material, closed = false) {
  const geometry = new THREE.BufferGeometry().setFromPoints(points)
  return closed ? new THREE.LineLoop(geometry, material) : new THREE.Line(geometry, material)
}

function ellipsePoints(cx: number, cy: number, rx: number, ry: number, z: number, start = 0, end = Math.PI * 2) {
  return Array.from({ length: 34 }, (_, index) => {
    const angle = start + (end - start) * index / 33
    return new THREE.Vector3(cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry, z)
  })
}

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

    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.8))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(28, 1, .1, 30)
    camera.position.set(0, .05, 6.75)

    const bust = new THREE.Group()
    bust.position.y = .02
    scene.add(bust)

    const dimMaterial = new THREE.LineBasicMaterial({
      color: 0x45cfff, transparent: true, opacity: .29,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const brightMaterial = new THREE.LineBasicMaterial({
      color: 0xa6f8ff, transparent: true, opacity: .82,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })
    const accentMaterial = new THREE.LineBasicMaterial({
      color: 0x52e5ff, transparent: true, opacity: .64,
      blending: THREE.AdditiveBlending, depthWrite: false,
    })

    // A colorless anatomical surface writes only to the depth buffer. It hides
    // the wireframe on the far side of the skull, so the face reads as a solid
    // human volume rather than a transparent spherical cage.
    const surfaceRows = 34
    const surfaceColumns = 48
    const surfacePositions: number[] = []
    const surfaceIndices: number[] = []
    for (let row = 0; row <= surfaceRows; row += 1) {
      const y = HEAD_BOTTOM + row / surfaceRows * (HEAD_CROWN - HEAD_BOTTOM)
      for (let column = 0; column <= surfaceColumns; column += 1) {
        const point = headPoint(y, -Math.PI + column / surfaceColumns * Math.PI * 2)
        surfacePositions.push(point.x, point.y, point.z)
      }
    }
    for (let row = 0; row < surfaceRows; row += 1) {
      for (let column = 0; column < surfaceColumns; column += 1) {
        const current = row * (surfaceColumns + 1) + column
        const next = current + surfaceColumns + 1
        surfaceIndices.push(current, next, current + 1, next, next + 1, current + 1)
      }
    }
    const surfaceGeometry = new THREE.BufferGeometry()
    surfaceGeometry.setAttribute('position', new THREE.Float32BufferAttribute(surfacePositions, 3))
    surfaceGeometry.setIndex(surfaceIndices)
    surfaceGeometry.computeVertexNormals()
    const depthOccluder = new THREE.Mesh(
      surfaceGeometry,
      new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: true, side: THREE.FrontSide }),
    )
    depthOccluder.renderOrder = -1
    bust.add(depthOccluder)

    // Fewer latitude bands prevent the cranium from reading as a striped fruit.
    // The brighter side contours make the tall human silhouette unmistakable.
    const contourRows = 23
    for (let row = 0; row < contourRows; row += 1) {
      const y = HEAD_BOTTOM + .02 + row / (contourRows - 1) * (VISIBLE_CROWN - HEAD_BOTTOM - .02)
      const points = Array.from({ length: 73 }, (_, index) => headPoint(y, -Math.PI + index / 72 * Math.PI * 2))
      const line = curve(points, row % 5 === 0 ? accentMaterial : dimMaterial, true)
      line.userData.baseOpacity = row % 5 === 0 ? .64 : .29
      bust.add(line)
    }
    const silhouetteY = Array.from({ length: 64 }, (_, index) => HEAD_BOTTOM + .02 + index / 63 * (VISIBLE_CROWN - HEAD_BOTTOM - .02))
    bust.add(
      curve(silhouetteY.map((y) => headPoint(y, -Math.PI / 2)), brightMaterial),
      curve(silhouetteY.map((y) => headPoint(y, Math.PI / 2)), brightMaterial),
    )

    // Vertical meridians reveal the taller cranial volume while the head turns.
    for (let column = 0; column < 18; column += 1) {
      const angle = -Math.PI + column / 17 * Math.PI * 2
      const points = Array.from({ length: 56 }, (_, index) => headPoint(HEAD_BOTTOM + .02 + index / 55 * (HEAD_CROWN - HEAD_BOTTOM - .04), angle))
      bust.add(curve(points, column % 4 === 0 ? accentMaterial : dimMaterial))
    }

    const features = new THREE.Group()
    features.position.z = .02
    features.scale.x = FEATURE_WIDTH_SCALE
    bust.add(features)

    // Brows and eyes are independent luminous splines so blinking stays visible.
    const leftEye = curve(ellipsePoints(-.39, .29, .26, .088, .705), brightMaterial, true)
    const rightEye = curve(ellipsePoints(.39, .29, .26, .088, .705), brightMaterial, true)
    const leftIris = curve(ellipsePoints(-.39, .29, .057, .074, .725), accentMaterial, true)
    const rightIris = curve(ellipsePoints(.39, .29, .057, .074, .725), accentMaterial, true)
    const irises = new THREE.Group()
    irises.add(leftIris, rightIris)
    const eyes = new THREE.Group()
    eyes.add(leftEye, rightEye, irises)
    features.add(eyes)
    const brows = new THREE.Group()
    brows.add(
      curve(ellipsePoints(-.39, .47, .3, .105, .69, .16, Math.PI - .16), accentMaterial),
      curve(ellipsePoints(.39, .47, .3, .105, .69, .16, Math.PI - .16), accentMaterial),
    )
    features.add(brows)

    // A protruding nose bridge makes the profile unmistakably three-dimensional.
    features.add(curve([
      new THREE.Vector3(0, .38, .72), new THREE.Vector3(-.025, .12, .86),
      new THREE.Vector3(-.055, -.13, .98), new THREE.Vector3(-.15, -.23, .77),
      new THREE.Vector3(0, -.27, .83), new THREE.Vector3(.15, -.23, .77),
    ], brightMaterial))
    features.add(curve(ellipsePoints(0, -.27, .15, .045, .79, 0, Math.PI), accentMaterial))

    const upperLipPoints = ellipsePoints(0, -.57, .33, .085, .75, Math.PI, Math.PI * 2)
    const upperLip = curve(upperLipPoints, brightMaterial)
    const lowerLipPoints = ellipsePoints(0, -.57, .33, .1, .75, 0, Math.PI)
    const lowerLip = curve(lowerLipPoints, brightMaterial)
    const mouthCore = curve([new THREE.Vector3(-.32, -.57, .745), new THREE.Vector3(0, -.535, .775), new THREE.Vector3(.32, -.57, .745)], accentMaterial)
    features.add(upperLip, lowerLip, mouthCore)

    // Cheekbones and a tapered jaw reinforce feminine facial anatomy.
    features.add(
      curve([new THREE.Vector3(-.75, .03, .55), new THREE.Vector3(-.65, -.18, .7), new THREE.Vector3(-.52, -.4, .72)], dimMaterial),
      curve([new THREE.Vector3(.75, .03, .55), new THREE.Vector3(.65, -.18, .7), new THREE.Vector3(.52, -.4, .72)], dimMaterial),
    )

    // Jaw accent, ears, neck and shoulders complete the floating holographic bust.
    features.add(curve([
      new THREE.Vector3(-.75, -.72, .5), new THREE.Vector3(-.61, -1.16, .57),
      new THREE.Vector3(-.29, -1.48, .49), new THREE.Vector3(0, -1.61, .41),
      new THREE.Vector3(.29, -1.48, .49), new THREE.Vector3(.61, -1.16, .57),
      new THREE.Vector3(.75, -.72, .5),
    ], accentMaterial))
    features.add(
      curve(ellipsePoints(-1.01, -.03, .125, .33, .04), dimMaterial, true),
      curve(ellipsePoints(1.01, -.03, .125, .33, .04), dimMaterial, true),
      curve([new THREE.Vector3(-.36, -1.54, .25), new THREE.Vector3(-.43, -2.08, .05)], accentMaterial),
      curve([new THREE.Vector3(.36, -1.54, .25), new THREE.Vector3(.43, -2.08, .05)], accentMaterial),
      curve([new THREE.Vector3(-1.48, -2.17, -.18), new THREE.Vector3(-.72, -1.91, .03), new THREE.Vector3(0, -2.08, .18), new THREE.Vector3(.72, -1.91, .03), new THREE.Vector3(1.48, -2.17, -.18)], dimMaterial),
    )

    // Thousands of dim vertices reinforce that this is a generated data sculpture.
    const pointPositions: number[] = []
    const pointRows = 39
    for (let row = 0; row < pointRows; row += 1) {
      const y = HEAD_BOTTOM + .02 + row / (pointRows - 1) * (VISIBLE_CROWN - HEAD_BOTTOM - .02)
      for (let column = 0; column < 44; column += 1) {
        const point = headPoint(y, column / 44 * Math.PI * 2)
        pointPositions.push(point.x, point.y, point.z)
      }
    }
    const pointGeometry = new THREE.BufferGeometry()
    pointGeometry.setAttribute('position', new THREE.Float32BufferAttribute(pointPositions, 3))
    const pointMaterial = new THREE.PointsMaterial({
      color: 0x7deaff, size: .018, transparent: true, opacity: .5,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    })
    bust.add(new THREE.Points(pointGeometry, pointMaterial))

    const rings = new THREE.Group()
    rings.rotation.x = 1.22
    rings.position.y = -2.13
    scene.add(rings)
    ;[1.05, 1.38, 1.72].forEach((radius, index) => {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(radius, index === 1 ? .012 : .006, 5, 100),
        new THREE.MeshBasicMaterial({ color: index === 1 ? 0x9ff8ff : 0x3acfff, transparent: true, opacity: .52 - index * .1, blending: THREE.AdditiveBlending }),
      )
      rings.add(ring)
    })

    const resize = () => {
      const width = canvas.clientWidth || 300
      const height = canvas.clientHeight || 330
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    resize()

    const pointerTarget = new THREE.Vector2()
    const handlePointer = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect()
      pointerTarget.set((event.clientX - rect.left) / rect.width - .5, (event.clientY - rect.top) / rect.height - .5)
    }
    canvas.addEventListener('pointermove', handlePointer, { passive: true })
    canvas.addEventListener('pointerleave', () => pointerTarget.set(0, 0))

    const clock = new THREE.Clock()
    const color = new THREE.Color()
    let smoothVoice = 0
    let smoothOpen = 0
    let smoothRound = 0
    let smoothWide = 0
    let frame = 0
    const animate = () => {
      const elapsed = clock.getElapsedTime()
      const currentState = stateRef.current
      const rawVoice = currentState === 'speaking' ? Math.min(1, Math.max(0, outputRef.current())) : 0
      smoothVoice += (rawVoice - smoothVoice) * (rawVoice > smoothVoice ? .48 : .18)

      // The SDK's output analyser drives a compact facial rig. Spectral centroid
      // separates rounded vowels from spread vowels and high-frequency
      // consonants, producing real articulation rather than volume-only flapping.
      const spectrum = currentState === 'speaking' ? frequencyRef.current() : new Uint8Array()
      let energy = 0
      let weighted = 0
      let highEnergy = 0
      for (let index = 1; index < spectrum.length; index += 1) {
        const value = spectrum[index] / 255
        energy += value
        weighted += value * index
        if (index > spectrum.length * .46) highEnergy += value
      }
      const centroid = energy > .01 ? weighted / energy / Math.max(1, spectrum.length - 1) : .2
      const highRatio = energy > .01 ? highEnergy / energy : 0
      const targetOpen = Math.min(1, rawVoice * 1.15 + Math.max(0, .28 - centroid) * 1.1)
      const targetRound = Math.min(1, Math.max(0, (.24 - centroid) * 5.5) * rawVoice)
      const targetWide = Math.min(1, Math.max(0, (centroid - .2) * 4.2 + highRatio * .8) * rawVoice)
      smoothOpen += (targetOpen - smoothOpen) * .42
      smoothRound += (targetRound - smoothRound) * .3
      smoothWide += (targetWide - smoothWide) * .3
      buttonRef.current?.style.setProperty('--voice-level', smoothVoice.toFixed(3))

      const automaticYaw = Math.sin(elapsed * .42) * .19
      bust.rotation.y += (automaticYaw + pointerTarget.x * .42 - bust.rotation.y) * .035
      bust.rotation.x += (Math.sin(elapsed * .3) * .025 - pointerTarget.y * .18 - bust.rotation.x) * .035
      bust.position.y = .02 + Math.sin(elapsed * .85) * .025

      const blinkCycle = 4.65 + Math.sin(elapsed * .17) * .7
      const blinkPhase = elapsed % blinkCycle
      const blink = blinkPhase > blinkCycle - .18 ? .07 : 1
      eyes.scale.y += (blink - eyes.scale.y) * .55

      // Tiny deterministic saccades and state-aware brows avoid a dead stare.
      const gazeStep = Math.floor(elapsed * .72)
      const gazeX = Math.sin(gazeStep * 12.9898) * .025
      const gazeY = Math.sin(gazeStep * 7.233) * .012 + (currentState === 'thinking' ? .018 : 0)
      irises.position.x += (gazeX - irises.position.x) * .12
      irises.position.y += (gazeY - irises.position.y) * .12
      const browLift = currentState === 'listening' ? .035 : currentState === 'thinking' ? .055 : smoothOpen * .018
      brows.position.y += (browLift - brows.position.y) * .08

      const mouthWidth = 1 + smoothWide * .22 - smoothRound * .38
      const upperPosition = upperLip.geometry.getAttribute('position') as THREE.BufferAttribute
      const lowerPosition = lowerLip.geometry.getAttribute('position') as THREE.BufferAttribute
      upperLipPoints.forEach((point, index) => upperPosition.setXYZ(index, point.x * mouthWidth, point.y + smoothOpen * .055 * Math.sin(index / 33 * Math.PI), point.z))
      lowerLipPoints.forEach((point, index) => lowerPosition.setXYZ(index, point.x * mouthWidth, point.y - smoothOpen * .26 * Math.sin(index / 33 * Math.PI), point.z))
      upperPosition.needsUpdate = true
      lowerPosition.needsUpdate = true
      mouthCore.scale.x = mouthWidth
      mouthCore.scale.y = .12 + smoothOpen * 3.4
      mouthCore.position.y = -smoothOpen * .075

      color.setHex(STATE_COLORS[currentState])
      dimMaterial.color.lerp(color, .05)
      accentMaterial.color.lerp(color, .04)
      pointMaterial.color.lerp(color, .04)
      brightMaterial.opacity = .72 + smoothVoice * .25 + Math.sin(elapsed * 2.4) * .035
      pointMaterial.opacity = .38 + smoothVoice * .22
      rings.rotation.z = elapsed * .11
      rings.scale.setScalar(1 + smoothVoice * .055)

      // Brief data dropouts create a film-style projection rather than a solid model.
      bust.visible = !(Math.floor(elapsed * 100) % 347 === 0)
      renderer.render(scene, camera)
      frame = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      canvas.removeEventListener('pointermove', handlePointer)
      scene.traverse((object) => {
        if (!(object instanceof THREE.Line || object instanceof THREE.Points || object instanceof THREE.Mesh)) return
        object.geometry.dispose()
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => material.dispose())
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
