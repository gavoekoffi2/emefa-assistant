/* oxlint-disable react/only-export-components */
import { useEffect, useRef, useState } from 'react'
import { ConversationProvider } from '@elevenlabs/react'
import { VoiceRoom } from './VoiceRoom'
import './App.css'
import './Holographic.css'

export type Session = { device_id: string; name: string }
export type VoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'awaiting' | 'success' | 'error'
type GraphNode = { id: number; label: string; group: string; x: number; y: number; z: number; size: number }
type GraphLink = { source: number; target: number }

export const api = async <T,>(path: string, options: RequestInit = {}): Promise<T> => {
  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `La requête a échoué (${response.status}).`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const statusCopy: Record<VoiceState, string> = {
  idle: 'PRÊTE',
  listening: 'JE VOUS ÉCOUTE',
  thinking: 'JE RÉFLÉCHIS',
  speaking: 'JE VOUS RÉPONDS',
  awaiting: 'EN ATTENTE DE VOTRE APPROBATION',
  success: 'TERMINÉ',
  error: 'CONNEXION INTERROMPUE',
}

export const palette: Record<string, string> = {
  EMEFA: '#70ecff', Projets: '#9a7dff', Mémoire: '#f3c96b', Outils: '#67e4b2', Documents: '#ff8da1', Idées: '#6f9dff',
}

export const graphNodes: GraphNode[] = [
  { id: 0, label: 'EMEFA', group: 'EMEFA', x: 0, y: 0, z: 70, size: 7 },
  { id: 1, label: 'Mémoire personnelle', group: 'Mémoire', x: -150, y: -45, z: 10, size: 5 },
  { id: 2, label: 'Projets actifs', group: 'Projets', x: 145, y: -75, z: -35, size: 5 },
  { id: 3, label: 'Documents', group: 'Documents', x: -65, y: 125, z: -80, size: 4 },
  { id: 4, label: 'Agenda', group: 'Outils', x: 110, y: 105, z: 20, size: 4 },
  { id: 5, label: 'Messagerie', group: 'Outils', x: 210, y: 10, z: -90, size: 4 },
  { id: 6, label: 'Notes vocales', group: 'Mémoire', x: -220, y: 80, z: 55, size: 4 },
  { id: 7, label: 'Décisions', group: 'Mémoire', x: -120, y: -145, z: -70, size: 4 },
  { id: 8, label: 'Recherche', group: 'Outils', x: 35, y: -155, z: 35, size: 4 },
  { id: 9, label: 'Idées', group: 'Idées', x: 20, y: 165, z: 75, size: 4 },
  { id: 10, label: 'Tâches', group: 'Projets', x: 175, y: 150, z: -45, size: 4 },
  { id: 11, label: 'Ressources', group: 'Documents', x: -190, y: 155, z: -45, size: 4 },
  { id: 12, label: 'Conversations', group: 'Mémoire', x: -25, y: -115, z: -110, size: 4 },
  { id: 13, label: 'Contacts', group: 'Outils', x: 230, y: -120, z: 40, size: 4 },
  { id: 14, label: 'Archives', group: 'Documents', x: -245, y: -100, z: -35, size: 3 },
  { id: 15, label: 'Objectifs', group: 'Projets', x: 90, y: 35, z: -130, size: 4 },
]
const graphLinks: GraphLink[] = [
  { source: 0, target: 1 }, { source: 0, target: 2 }, { source: 0, target: 3 }, { source: 0, target: 4 },
  { source: 0, target: 8 }, { source: 0, target: 9 }, { source: 1, target: 6 }, { source: 1, target: 7 },
  { source: 1, target: 12 }, { source: 1, target: 14 }, { source: 2, target: 10 }, { source: 2, target: 15 },
  { source: 3, target: 11 }, { source: 3, target: 14 }, { source: 4, target: 10 }, { source: 5, target: 13 },
  { source: 8, target: 3 }, { source: 9, target: 11 }, { source: 10, target: 15 }, { source: 12, target: 7 },
]

export function BrandMark() { return <span className="brand-mark" aria-hidden="true">E</span> }

export type AuthStatus = { registered: boolean; authenticated: boolean; account: { account_id: string; email: string; display_name: string; role: string } | null }

const MIN_PASSWORD = 10

/**
 * Sign-in gate.
 *
 * Two screens, chosen by whether this instance already has an owner. Before
 * it does, the activation code creates that owner; afterwards the code is
 * refused by the backend and only credentials get in (ADR-002).
 */
function Activation({ registered, onSignedIn }: { registered: boolean; onSignedIn: (session: Session) => void }) {
  const [name, setName] = useState('Ce navigateur')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const path = registered ? '/v1/auth/login' : '/v1/auth/register'
      const body = registered
        ? { email: email.trim(), password, device_name: name.trim() }
        : { email: email.trim(), password, display_name: displayName.trim(), device_name: name.trim(), enrollment_code: code }
      await api<unknown>(path, { method: 'POST', body: JSON.stringify(body) })
      // The session cookie is set by the call above; this reads back the
      // device the rest of the app is addressed by.
      onSignedIn(await api<Session>('/v1/web/session'))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Connexion impossible.') }
    finally { setBusy(false) }
  }

  const incomplete = !email.trim() || password.length < (registered ? 1 : MIN_PASSWORD) || (!registered && !code)

  return (
    <main className="activation-page">
      <section className="activation-intro">
        <div className="brand-row"><BrandMark /><strong>EMEFA</strong></div>
        <div className="intro-copy"><span className="eyebrow">Assistante personnelle vocale</span><h1>Une conversation.<br />Pas un chatbot.</h1><p>Parlez naturellement à EMEFA. Elle vous écoute, répond à voix haute et garde le fil de la conversation.</p></div>
        <div className="privacy-note"><span className="privacy-dot" /><div><strong>Accès privé</strong><small>{registered ? 'Votre mémoire et vos documents restent liés à votre compte.' : 'Le code d’activation ne sert qu’une fois, pour créer votre compte.'}</small></div></div>
      </section>
      <section className="activation-panel" aria-labelledby="activation-title">
        <div className="activation-card">
          <BrandMark />
          <h2 id="activation-title">{registered ? 'Se connecter' : 'Créer votre compte'}</h2>
          <p>{registered ? 'Entrez vos identifiants pour retrouver EMEFA.' : 'Ce compte sera propriétaire de cette instance EMEFA.'}</p>
          <form onSubmit={submit}>
            {!registered && (<>
              <label htmlFor="display-name">Votre nom</label>
              <input id="display-name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" />
            </>)}
            <label htmlFor="account-email">Adresse e-mail</label>
            <input id="account-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
            <label htmlFor="account-password">Mot de passe</label>
            <input id="account-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={registered ? undefined : MIN_PASSWORD} autoComplete={registered ? 'current-password' : 'new-password'} />
            {!registered && <small className="field-hint">{MIN_PASSWORD} caractères minimum.</small>}
            {!registered && (<>
              <label htmlFor="activation-code">Code d’activation</label>
              <input id="activation-code" type="password" value={code} onChange={(event) => setCode(event.target.value)} required placeholder="Votre code privé" />
            </>)}
            <label htmlFor="browser-name">Nom de ce navigateur</label>
            <input id="browser-name" value={name} onChange={(event) => setName(event.target.value)} required />
            {error && <div className="form-error" role="alert">{error}</div>}
            <button className="primary-button" disabled={busy || !name.trim() || incomplete}>{busy ? 'Connexion…' : registered ? 'Entrer dans EMEFA' : 'Créer le compte'}</button>
          </form>
        </div>
      </section>
    </main>
  )
}

export function KnowledgeGalaxy({ activeNodes, voiceState }: { activeNodes: number[]; voiceState: VoiceState }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const pointerRef = useRef({ x: 0, y: 0 })
  const activeRef = useRef(activeNodes)
  useEffect(() => { activeRef.current = activeNodes }, [activeNodes])
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    let frame = 0
    let animation = 0
    const stars = Array.from({ length: 150 }, (_, id) => ({ id, x: Math.random(), y: Math.random(), r: Math.random() * 1.25 + .2, a: Math.random() * .55 + .15 }))
    const resize = () => { const ratio = Math.min(devicePixelRatio || 1, 2); canvas.width = canvas.clientWidth * ratio; canvas.height = canvas.clientHeight * ratio; context.setTransform(ratio, 0, 0, ratio, 0, 0) }
    const draw = () => {
      const w = canvas.clientWidth, h = canvas.clientHeight
      context.clearRect(0, 0, w, h)
      for (const star of stars) { context.fillStyle = `rgba(179,221,255,${star.a})`; context.beginPath(); context.arc(star.x * w, star.y * h, star.r, 0, Math.PI * 2); context.fill() }
      const angle = frame * .00055 + pointerRef.current.x * .00025
      const tilt = -.16 + pointerRef.current.y * .00012
      const projected = graphNodes.map((node) => {
        const rx = node.x * Math.cos(angle) - node.z * Math.sin(angle)
        const rz = node.x * Math.sin(angle) + node.z * Math.cos(angle)
        const ry = node.y * Math.cos(tilt) - rz * Math.sin(tilt)
        const depth = node.y * Math.sin(tilt) + rz * Math.cos(tilt)
        const scale = 540 / (650 + depth)
        return { ...node, sx: w / 2 + rx * scale, sy: h / 2 + ry * scale, scale, depth }
      })
      for (const link of graphLinks) {
        const a = projected[link.source], b = projected[link.target]
        const lit = activeRef.current.includes(a.id) || activeRef.current.includes(b.id)
        const gradient = context.createLinearGradient(a.sx, a.sy, b.sx, b.sy)
        gradient.addColorStop(0, lit ? 'rgba(116,224,255,.72)' : 'rgba(100,160,210,.12)'); gradient.addColorStop(1, lit ? 'rgba(151,126,255,.55)' : 'rgba(100,160,210,.05)')
        context.strokeStyle = gradient; context.lineWidth = lit ? 1.4 : .65; context.beginPath(); context.moveTo(a.sx, a.sy); context.lineTo(b.sx, b.sy); context.stroke()
      }
      projected.sort((a, b) => b.depth - a.depth).forEach((node) => {
        const active = activeRef.current.includes(node.id) || (voiceState !== 'idle' && node.id === 0)
        const radius = node.size * node.scale * (active ? 1.65 : 1)
        const color = palette[node.group] || '#70ecff'
        context.shadowColor = color; context.shadowBlur = active ? 27 : 10; context.fillStyle = color; context.globalAlpha = active ? 1 : .75
        context.beginPath(); context.arc(node.sx, node.sy, Math.max(2.1, radius), 0, Math.PI * 2); context.fill(); context.shadowBlur = 0; context.globalAlpha = 1
        if (active || node.size >= 5) { context.fillStyle = active ? '#f7fdff' : 'rgba(215,235,248,.72)'; context.font = `${active ? 600 : 500} ${active ? 12 : 10}px Manrope`; context.textAlign = 'center'; context.fillText(node.label, node.sx, node.sy + radius + 15) }
      })
      frame += 1; animation = requestAnimationFrame(draw)
    }
    resize(); draw(); window.addEventListener('resize', resize)
    return () => { cancelAnimationFrame(animation); window.removeEventListener('resize', resize) }
  }, [voiceState])
  return <canvas ref={canvasRef} className="galaxy-canvas" onPointerMove={(event) => { pointerRef.current = { x: event.clientX - innerWidth / 2, y: event.clientY - innerHeight / 2 } }} aria-label="Univers de connaissances EMEFA" />
}

export function VoiceOrb({ state, onClick }: { state: VoiceState; onClick: () => void }) {
  return <button className={`voice-orb ${state}`} onClick={onClick} aria-label={state === 'idle' ? 'Démarrer une conversation vocale' : 'Arrêter la conversation vocale'}><span className="orb-halo h1" /><span className="orb-halo h2" /><span className="orb-core"><BrandMark /></span><span className="equalizer">{Array.from({ length: 9 }, (_, index) => <i key={index} />)}</span></button>
}

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [registered, setRegistered] = useState(false)
  const [checking, setChecking] = useState(true)
  useEffect(() => {
    // Two questions, one round trip each: does this instance have an owner,
    // and is this browser already signed in? The session lookup also covers
    // browsers enrolled before accounts existed, which stay valid.
    void (async () => {
      try {
        const status = await api<AuthStatus>('/v1/auth/status')
        setRegistered(status.registered)
        if (status.registered && !status.authenticated) {
          setSession(null)
          setChecking(false)
          return
        }
      } catch { setRegistered(false) }
      try { setSession(await api<Session>('/v1/web/session')) } catch { setSession(null) }
      setChecking(false)
    })()
  }, [])
  const logout = async () => { try { await api<void>('/v1/auth/logout', { method: 'POST' }) } finally { setSession(null); setRegistered(true) } }
  if (checking) return <div className="splash"><BrandMark /><span>EMEFA</span><i className="spinner" /></div>
  return session ? <ConversationProvider><VoiceRoom session={session} onLogout={() => void logout()} /></ConversationProvider> : <Activation registered={registered} onSignedIn={setSession} />
}

export default App
