import { useEffect, useRef } from 'react'
import * as THREE from 'three'
import type { VoiceState } from './App'

const NODE_POSITIONS = [
  [0, 0, 0], [-4.5, -1.2, -1], [4.4, -1.8, -2], [-2, 3.5, -3], [3.2, 2.8, -1],
  [5.2, .3, -4], [-5.5, 2.1, 1], [-3.3, -3.7, -3], [1.1, -4, 0], [.7, 4.3, 1],
  [4.7, 3.7, -2], [-4.7, 4, -2], [-.8, -3, -4], [5.8, -3.2, .5], [-6, -2.8, -2], [2.7, 1, -5],
] as const

const LINKS = [
  [0,1],[0,2],[0,3],[0,4],[0,8],[0,9],[1,6],[1,7],[1,12],[1,14],
  [2,10],[2,15],[3,11],[3,14],[4,10],[5,13],[8,3],[9,11],[10,15],[12,7],
] as const

const COLORS = [0x70ecff, 0xf3c96b, 0x9a7dff, 0xff8da1, 0x67e4b2, 0x67e4b2, 0xf3c96b, 0xf3c96b, 0x67e4b2, 0x6f9dff, 0x9a7dff, 0xff8da1, 0xf3c96b, 0x67e4b2, 0xff8da1, 0x9a7dff]

const STATE_COLORS: Record<VoiceState, number> = {
  idle: 0x57d7ff,
  listening: 0x55f6d0,
  thinking: 0xb18cff,
  speaking: 0x7af4ff,
  error: 0xff607c,
}

function seeded(index: number) {
  const value = Math.sin(index * 913.731 + 41.53) * 43758.5453
  return value - Math.floor(value)
}

export function HolographicUniverse({ activeNodes, voiceState }: { activeNodes: number[]; voiceState: VoiceState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const stateRef = useRef(voiceState)
  const activeRef = useRef(activeNodes)

  useEffect(() => { stateRef.current = voiceState }, [voiceState])
  useEffect(() => { activeRef.current = activeNodes }, [activeNodes])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.35

    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x010611, 0.04)
    const camera = new THREE.PerspectiveCamera(42, 1, .1, 100)
    camera.position.set(0, .25, 13.5)

    const root = new THREE.Group()
    root.position.y = 1.35
    scene.add(root)

    scene.add(new THREE.AmbientLight(0x174e72, 1.25))
    const keyLight = new THREE.PointLight(0x6beaff, 36, 22, 2)
    keyLight.position.set(1, 1, 4)
    scene.add(keyLight)
    const rimLight = new THREE.PointLight(0xff8a4a, 22, 18, 2)
    rimLight.position.set(-5, 2, 1)
    scene.add(rimLight)

    const core = new THREE.Group()
    root.add(core)
    const coreMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x57d7ff, emissive: 0x167aa6, emissiveIntensity: 2.6,
      metalness: .48, roughness: .08, transparent: true, opacity: .68,
      clearcoat: 1, clearcoatRoughness: .08,
    })
    const coreSphere = new THREE.Mesh(new THREE.IcosahedronGeometry(.86, 5), coreMaterial)
    core.add(coreSphere)
    const innerMaterial = new THREE.MeshBasicMaterial({ color: 0xbaf9ff, transparent: true, opacity: .8, blending: THREE.AdditiveBlending, depthWrite: false })
    const innerSphere = new THREE.Mesh(new THREE.SphereGeometry(.48, 32, 24), innerMaterial)
    core.add(innerSphere)
    const shellMaterial = new THREE.MeshBasicMaterial({ color: 0x76eaff, wireframe: true, transparent: true, opacity: .22, blending: THREE.AdditiveBlending })
    const shell = new THREE.Mesh(new THREE.IcosahedronGeometry(1.3, 2), shellMaterial)
    core.add(shell)

    const rings: THREE.Mesh[] = []
    ;[
      [1.55, .018, .15, .1, 0], [1.88, .012, 1.12, .38, .25], [2.18, .009, .45, 1.08, -.15], [2.48, .007, 1.38, -.15, .35],
    ].forEach(([radius, tube, x, y, z], index) => {
      const material = new THREE.MeshBasicMaterial({ color: index === 2 ? 0xff9b55 : 0x66dfff, transparent: true, opacity: index === 2 ? .42 : .3, blending: THREE.AdditiveBlending })
      const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 6, 160), material)
      ring.rotation.set(x, y, z)
      rings.push(ring)
      core.add(ring)
    })

    const tickMaterial = new THREE.LineBasicMaterial({ color: 0x7eeaff, transparent: true, opacity: .55, blending: THREE.AdditiveBlending })
    const tickGeometry = new THREE.BufferGeometry()
    const tickVertices: number[] = []
    for (let index = 0; index < 72; index += 1) {
      const angle = index / 72 * Math.PI * 2
      const inner = index % 6 === 0 ? 2.66 : 2.75
      const outer = index % 6 === 0 ? 2.94 : 2.86
      tickVertices.push(Math.cos(angle) * inner, Math.sin(angle) * inner, 0, Math.cos(angle) * outer, Math.sin(angle) * outer, 0)
    }
    tickGeometry.setAttribute('position', new THREE.Float32BufferAttribute(tickVertices, 3))
    const ticks = new THREE.LineSegments(tickGeometry, tickMaterial)
    ticks.rotation.x = .22
    core.add(ticks)

    const nodeGroup = new THREE.Group()
    nodeGroup.position.z = -2.2
    root.add(nodeGroup)
    const nodeMeshes: THREE.Mesh[] = []
    NODE_POSITIONS.forEach((position, index) => {
      if (index === 0) { nodeMeshes.push(coreSphere); return }
      const material = new THREE.MeshBasicMaterial({ color: COLORS[index], transparent: true, opacity: .54, blending: THREE.AdditiveBlending, depthWrite: false })
      const node = new THREE.Mesh(new THREE.SphereGeometry(index < 5 ? .085 : .055, 12, 8), material)
      node.position.set(position[0], position[1], position[2])
      nodeMeshes.push(node)
      nodeGroup.add(node)
      const halo = new THREE.Mesh(new THREE.RingGeometry(.12, .15, 24), new THREE.MeshBasicMaterial({ color: COLORS[index], transparent: true, opacity: .24, side: THREE.DoubleSide, blending: THREE.AdditiveBlending }))
      halo.position.copy(node.position)
      nodeGroup.add(halo)
    })
    const linkPositions: number[] = []
    LINKS.forEach(([from, to]) => {
      linkPositions.push(...NODE_POSITIONS[from], ...NODE_POSITIONS[to])
    })
    const linkGeometry = new THREE.BufferGeometry()
    linkGeometry.setAttribute('position', new THREE.Float32BufferAttribute(linkPositions, 3))
    const links = new THREE.LineSegments(linkGeometry, new THREE.LineBasicMaterial({ color: 0x4bb9e8, transparent: true, opacity: .13, blending: THREE.AdditiveBlending }))
    nodeGroup.add(links)

    const particleCount = window.innerWidth < 800 ? 320 : 720
    const particlePositions = new Float32Array(particleCount * 3)
    const particleSizes = new Float32Array(particleCount)
    for (let index = 0; index < particleCount; index += 1) {
      const radius = 3.5 + seeded(index) * 10
      const theta = seeded(index + 1000) * Math.PI * 2
      const vertical = (seeded(index + 2000) - .5) * 9
      particlePositions[index * 3] = Math.cos(theta) * radius
      particlePositions[index * 3 + 1] = vertical
      particlePositions[index * 3 + 2] = Math.sin(theta) * radius - 4
      particleSizes[index] = .6 + seeded(index + 3000) * 1.8
    }
    const particleGeometry = new THREE.BufferGeometry()
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3))
    particleGeometry.setAttribute('size', new THREE.BufferAttribute(particleSizes, 1))
    const particles = new THREE.Points(particleGeometry, new THREE.PointsMaterial({ color: 0x71cfff, size: .025, transparent: true, opacity: .64, blending: THREE.AdditiveBlending, depthWrite: false }))
    scene.add(particles)

    const debris = new THREE.Group()
    for (let index = 0; index < 26; index += 1) {
      const shard = new THREE.Mesh(
        new THREE.TetrahedronGeometry(.035 + seeded(index + 50) * .055, 0),
        new THREE.MeshBasicMaterial({ color: index % 4 === 0 ? 0xffa261 : 0x67dfff, transparent: true, opacity: .35, wireframe: true }),
      )
      const radius = 3 + seeded(index + 80) * 6
      const angle = seeded(index + 100) * Math.PI * 2
      shard.position.set(Math.cos(angle) * radius, (seeded(index + 120) - .5) * 7, Math.sin(angle) * radius - 3)
      debris.add(shard)
    }
    scene.add(debris)

    const grid = new THREE.GridHelper(32, 32, 0x144f71, 0x08243a)
    grid.position.set(0, -5.2, -3)
    ;(grid.material as THREE.Material).transparent = true
    ;(grid.material as THREE.Material).opacity = .22
    scene.add(grid)

    const pointer = new THREE.Vector2()
    const pointerTarget = new THREE.Vector2()
    const handlePointer = (event: PointerEvent) => {
      pointerTarget.set((event.clientX / window.innerWidth - .5) * 2, (event.clientY / window.innerHeight - .5) * 2)
    }
    window.addEventListener('pointermove', handlePointer, { passive: true })

    const resize = () => {
      const width = canvas.clientWidth || window.innerWidth
      const height = canvas.clientHeight || window.innerHeight
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    resize()

    const clock = new THREE.Clock()
    let animationFrame = 0
    const color = new THREE.Color()
    const animate = () => {
      const elapsed = clock.getElapsedTime()
      const state = stateRef.current
      const motion = reducedMotion ? .08 : state === 'thinking' ? 1.65 : state === 'speaking' ? 1.3 : state === 'listening' ? .82 : .42
      pointer.lerp(pointerTarget, .025)
      camera.position.x += (pointer.x * .48 - camera.position.x) * .025
      camera.position.y += (-pointer.y * .28 + .25 - camera.position.y) * .025
      camera.lookAt(0, .45, 0)

      color.setHex(STATE_COLORS[state])
      coreMaterial.color.lerp(color, .045)
      coreMaterial.emissive.lerp(color.clone().multiplyScalar(.42), .045)
      shellMaterial.color.lerp(color, .05)
      keyLight.color.lerp(color, .04)
      const pulse = 1 + Math.sin(elapsed * (state === 'speaking' ? 7.5 : state === 'listening' ? 3.4 : 1.8)) * (state === 'speaking' ? .065 : .025)
      core.scale.setScalar(pulse)
      innerMaterial.opacity = .65 + Math.sin(elapsed * 4.2) * .2
      core.rotation.y = elapsed * .12 * motion
      shell.rotation.set(elapsed * .09 * motion, -elapsed * .16 * motion, elapsed * .07)
      rings.forEach((ring, index) => {
        ring.rotation.z += (.0008 + index * .00045) * motion * (index % 2 ? -1 : 1)
        ring.rotation.y += .00025 * motion
      })
      ticks.rotation.z = -elapsed * .045 * motion
      nodeGroup.rotation.y = elapsed * .025 + pointer.x * .04
      nodeGroup.rotation.x = -.06 + pointer.y * .025
      particles.rotation.y = elapsed * .006
      debris.rotation.y = -elapsed * .012
      debris.rotation.z = Math.sin(elapsed * .08) * .08
      nodeMeshes.forEach((node, index) => {
        if (index === 0) return
        const active = activeRef.current.includes(index)
        const scale = active ? 1.8 + Math.sin(elapsed * 5 + index) * .3 : 1
        node.scale.setScalar(scale)
        const material = node.material as THREE.MeshBasicMaterial
        material.opacity += ((active ? .95 : .48) - material.opacity) * .08
      })
      renderer.render(scene, camera)
      animationFrame = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(animationFrame)
      resizeObserver.disconnect()
      window.removeEventListener('pointermove', handlePointer)
      scene.traverse((object) => {
        if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points)) return
        object.geometry?.dispose()
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => material.dispose())
      })
      renderer.dispose()
    }
  }, [])

  return <canvas ref={canvasRef} className="holographic-universe" aria-label="Univers holographique tridimensionnel EMEFA" />
}
