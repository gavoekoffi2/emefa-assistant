import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { VoiceState } from './App'
import './EMEFAFace.css'

type EMEFAFaceProps = {
  state: VoiceState
  onClick: () => void
  getOutputVolume: () => number
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

function headWidth(y: number) {
  const normalized = (y + 1.48) / 3.12
  const cranium = Math.sin(Math.max(0, Math.min(1, normalized)) * Math.PI)
  const jaw = y < -.55 ? (y + 1.48) * .22 : 0
  return .59 + cranium * .38 + jaw
}

function headPoint(y: number, angle: number) {
  const width = headWidth(y)
  const depth = .69 + Math.max(0, y) * .035
  return new THREE.Vector3(
    Math.sin(angle) * width,
    y,
    Math.cos(angle) * depth - .06,
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
export function EMEFAFace({ state, onClick, getOutputVolume }: EMEFAFaceProps) {
  const buttonRef = useRef<HTMLButtonElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef(state)
  const outputRef = useRef(getOutputVolume)

  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { outputRef.current = getOutputVolume }, [getOutputVolume])

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
    camera.position.set(0, .04, 7.2)

    const bust = new THREE.Group()
    bust.position.y = .12
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

    // Horizontal contour slices: the luminous strokes themselves form the skull.
    for (let row = 0; row < 29; row += 1) {
      const y = -1.47 + row / 28 * 3.08
      const points = Array.from({ length: 73 }, (_, index) => headPoint(y, -Math.PI + index / 72 * Math.PI * 2))
      const line = curve(points, row % 4 === 0 ? accentMaterial : dimMaterial, true)
      line.userData.baseOpacity = row % 4 === 0 ? .64 : .29
      bust.add(line)
    }

    // Vertical meridians reveal real volume while the head turns.
    for (let column = 0; column < 22; column += 1) {
      const angle = -Math.PI + column / 21 * Math.PI * 2
      const points = Array.from({ length: 48 }, (_, index) => headPoint(-1.47 + index / 47 * 3.08, angle))
      bust.add(curve(points, column % 5 === 0 ? accentMaterial : dimMaterial))
    }

    const features = new THREE.Group()
    features.position.z = .02
    bust.add(features)

    // Brows and eyes are independent luminous splines so blinking stays visible.
    const leftEye = curve(ellipsePoints(-.35, .29, .24, .085, .685), brightMaterial, true)
    const rightEye = curve(ellipsePoints(.35, .29, .24, .085, .685), brightMaterial, true)
    const leftIris = curve(ellipsePoints(-.35, .29, .055, .072, .705), accentMaterial, true)
    const rightIris = curve(ellipsePoints(.35, .29, .055, .072, .705), accentMaterial, true)
    const eyes = new THREE.Group()
    eyes.add(leftEye, rightEye, leftIris, rightIris)
    features.add(eyes)
    features.add(
      curve(ellipsePoints(-.35, .46, .27, .1, .67, .16, Math.PI - .16), accentMaterial),
      curve(ellipsePoints(.35, .46, .27, .1, .67, .16, Math.PI - .16), accentMaterial),
    )

    // A protruding nose bridge makes the profile unmistakably three-dimensional.
    features.add(curve([
      new THREE.Vector3(0, .38, .72), new THREE.Vector3(-.025, .12, .86),
      new THREE.Vector3(-.055, -.13, .98), new THREE.Vector3(-.15, -.23, .77),
      new THREE.Vector3(0, -.27, .83), new THREE.Vector3(.15, -.23, .77),
    ], brightMaterial))
    features.add(curve(ellipsePoints(0, -.27, .15, .045, .79, 0, Math.PI), accentMaterial))

    const upperLip = curve(ellipsePoints(0, -.57, .3, .085, .73, Math.PI, Math.PI * 2), brightMaterial)
    const lowerLipPoints = ellipsePoints(0, -.57, .3, .1, .73, 0, Math.PI)
    const lowerLip = curve(lowerLipPoints, brightMaterial)
    const mouthCore = curve([new THREE.Vector3(-.29, -.57, .725), new THREE.Vector3(0, -.535, .755), new THREE.Vector3(.29, -.57, .725)], accentMaterial)
    features.add(upperLip, lowerLip, mouthCore)

    // Jaw accent, ears, neck and shoulders complete the floating holographic bust.
    features.add(curve([
      new THREE.Vector3(-.72, -.72, .46), new THREE.Vector3(-.58, -1.18, .56),
      new THREE.Vector3(-.28, -1.43, .65), new THREE.Vector3(0, -1.5, .7),
      new THREE.Vector3(.28, -1.43, .65), new THREE.Vector3(.58, -1.18, .56),
      new THREE.Vector3(.72, -.72, .46),
    ], accentMaterial))
    features.add(
      curve(ellipsePoints(-.91, -.03, .115, .3, .05), dimMaterial, true),
      curve(ellipsePoints(.91, -.03, .115, .3, .05), dimMaterial, true),
      curve([new THREE.Vector3(-.33, -1.42, .25), new THREE.Vector3(-.4, -2.02, .05)], accentMaterial),
      curve([new THREE.Vector3(.33, -1.42, .25), new THREE.Vector3(.4, -2.02, .05)], accentMaterial),
      curve([new THREE.Vector3(-1.48, -2.17, -.18), new THREE.Vector3(-.72, -1.91, .03), new THREE.Vector3(0, -2.08, .18), new THREE.Vector3(.72, -1.91, .03), new THREE.Vector3(1.48, -2.17, -.18)], dimMaterial),
    )

    // Thousands of dim vertices reinforce that this is a generated data sculpture.
    const pointPositions: number[] = []
    for (let row = 0; row < 35; row += 1) {
      const y = -1.46 + row / 34 * 3.05
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
    let frame = 0
    const animate = () => {
      const elapsed = clock.getElapsedTime()
      const currentState = stateRef.current
      const rawVoice = currentState === 'speaking' ? Math.min(1, Math.max(0, outputRef.current())) : 0
      smoothVoice += (rawVoice - smoothVoice) * (rawVoice > smoothVoice ? .48 : .18)
      buttonRef.current?.style.setProperty('--voice-level', smoothVoice.toFixed(3))

      const automaticYaw = Math.sin(elapsed * .42) * .19
      bust.rotation.y += (automaticYaw + pointerTarget.x * .42 - bust.rotation.y) * .035
      bust.rotation.x += (Math.sin(elapsed * .3) * .025 - pointerTarget.y * .18 - bust.rotation.x) * .035
      bust.position.y = .12 + Math.sin(elapsed * .85) * .025

      const blinkPhase = elapsed % 5.2
      const blink = blinkPhase > 4.85 && blinkPhase < 5.05 ? .08 : 1
      eyes.scale.y += (blink - eyes.scale.y) * .55

      const lowerPosition = lowerLip.geometry.getAttribute('position') as THREE.BufferAttribute
      lowerLipPoints.forEach((point, index) => lowerPosition.setXYZ(index, point.x, point.y - smoothVoice * .22 * Math.sin(index / 33 * Math.PI), point.z))
      lowerPosition.needsUpdate = true
      mouthCore.scale.y = 1 + smoothVoice * 2.6
      mouthCore.position.y = -smoothVoice * .05

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
