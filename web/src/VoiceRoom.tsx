import { useEffect, useMemo, useState } from 'react'
import { useConversation } from '@elevenlabs/react'
import { api, BrandMark, graphNodes, palette, statusCopy, VoiceOrb } from './App'
import { HolographicUniverse } from './HolographicUniverse'
import { isBusinessEmpty, ProfilePanel } from './ProfilePanel'
import type { BusinessProfile } from './ProfilePanel'
import type { Session, VoiceState } from './App'

type ConversationTurn = { id: string; role: 'user' | 'assistant'; text: string }
type SignedSession = { signed_url: string }
type VoiceMessage = { message?: string; source?: string; role?: string }
type AgentRun = {
  status: 'completed' | 'confirmation_required' | 'blocked' | 'failed'
  answer?: string | null
  error?: string | null
  pending_action?: { name: string } | null
}

const agentErrorCopy: Record<string, string> = {
  brain_unavailable: 'Le moteur de langage est momentanément indisponible. Réessayez dans un instant.',
  unknown_tool: 'EMEFA a tenté une action qu’elle ne connaît pas. Reformulez votre demande.',
  turn_budget_exhausted: 'Cette demande est trop complexe pour un seul échange. Découpez-la ou reformulez.',
  invalid_brain_step: 'Le moteur a renvoyé une réponse invalide. Réessayez.',
}

async function getVoiceTicket(): Promise<SignedSession> {
  const response = await fetch('/v1/realtime/session', { credentials: 'include' })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Connexion vocale refusée (${response.status}).`)
  }
  return response.json() as Promise<SignedSession>
}

export function VoiceRoom({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [state, setState] = useState<VoiceState>('idle')
  const [transcript, setTranscript] = useState('')
  const [answer, setAnswer] = useState('Bonsoir Claude. Je suis prête lorsque vous l’êtes.')
  const [notice, setNotice] = useState('')
  const [history, setHistory] = useState<ConversationTurn[]>([])
  const [activeNodes, setActiveNodes] = useState<number[]>([0])
  const [typed, setTyped] = useState('')
  const [profileOpen, setProfileOpen] = useState(false)
  const [firstRun, setFirstRun] = useState(false)

  useEffect(() => {
    api<BusinessProfile>('/v1/assistant/business')
      .then((profile) => {
        if (isBusinessEmpty(profile)) { setFirstRun(true); setProfileOpen(true) }
      })
      .catch(() => undefined)
  }, [])

  const conversation = useConversation({
    onConnect: () => { setNotice(''); setState('listening') },
    onDisconnect: () => setState('idle'),
    onError: (error) => {
      setState('error')
      setNotice(typeof error === 'string' ? error : 'La conversation vocale a été interrompue.')
    },
    onModeChange: ({ mode }) => setState(mode === 'speaking' ? 'speaking' : 'listening'),
    onMessage: (event) => {
      const payload = event as VoiceMessage
      const text = (payload.message || '').trim()
      if (!text) return
      const isUser = payload.source === 'user' || payload.role === 'user'
      if (isUser) {
        setTranscript(text)
        setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'user', text }])
        setState('thinking')
      } else {
        setAnswer(text)
        setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'assistant', text }])
        setActiveNodes([0, 1 + Math.floor(Math.random() * (graphNodes.length - 1))])
      }
    },
  })

  const live = conversation.status !== 'disconnected'

  useEffect(() => {
    if (conversation.status === 'connecting') setState('thinking')
    else if (conversation.status === 'connected') setState(conversation.isSpeaking ? 'speaking' : 'listening')
    else setState((current) => current === 'error' ? current : 'idle')
  }, [conversation.status, conversation.isSpeaking])

  const startRealtime = async () => {
    setNotice(''); setState('thinking')
    try {
      const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      permissionStream.getTracks().forEach((track) => track.stop())
      const ticket = await getVoiceTicket()
      await conversation.startSession({
        signedUrl: ticket.signed_url,
        workletPaths: {
          rawAudioProcessor: '/worklets/raw-audio-processor.js',
          audioConcatProcessor: '/worklets/audio-concat-processor.js',
        },
      })
    } catch (cause) {
      setState('error')
      const denied = cause instanceof DOMException && ['NotAllowedError', 'PermissionDeniedError'].includes(cause.name)
      setNotice(denied ? 'Autorisez le microphone pour parler directement à EMEFA.' : cause instanceof Error ? cause.message : 'EMEFA ne peut pas ouvrir la conversation vocale.')
    }
  }

  const toggleLive = async () => {
    if (live) { await conversation.endSession(); return }
    await startRealtime()
  }

  const submitTyped = async () => {
    const value = typed.trim()
    if (!value) return
    setTyped(''); setNotice(''); setTranscript(value)
    setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'user', text: value }])
    setState('thinking')
    if (conversation.status === 'connected') { conversation.sendUserMessage(value); return }
    try {
      const run = await api<AgentRun>('/v1/agent/runs', { method: 'POST', body: JSON.stringify({ message: value }) })
      let text: string
      if (run.status === 'completed' && run.answer) text = run.answer
      else if (run.status === 'confirmation_required') text = `L’action « ${run.pending_action?.name ?? 'demandée'} » nécessite votre approbation. Ce parcours d’approbation arrive dans une prochaine version.`
      else if (run.status === 'blocked') text = 'Cette action est bloquée par la politique de sécurité d’EMEFA.'
      else text = agentErrorCopy[run.error ?? ''] || 'La demande n’a pas abouti.'
      setAnswer(text)
      setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'assistant', text }])
      setState('idle')
    } catch (cause) {
      setState('error')
      setNotice(cause instanceof Error ? cause.message : 'La demande n’a pas abouti.')
    }
  }
  const latestUser = useMemo(() => [...history].reverse().find((turn) => turn.role === 'user')?.text, [history])

  return (
    <div className={`jarvis-shell state-${state}`}>
      <HolographicUniverse activeNodes={activeNodes} voiceState={state} />
      <div className="hud-atmosphere" aria-hidden="true"><span className="scan-beam" /><span className="film-grain" /></div>
      <div className="hud-frame" aria-hidden="true"><i className="corner top-left" /><i className="corner top-right" /><i className="corner bottom-left" /><i className="corner bottom-right" /></div>
      <div className="space-vignette" />
      <header className="jarvis-header">
        <div className="brand-row"><BrandMark /><div><strong>EMEFA</strong><small>INTELLIGENCE COGNITIVE</small></div></div>
        <nav><button className={profileOpen ? '' : 'nav-active'} onClick={() => setProfileOpen(false)}>Univers</button><button className={profileOpen ? 'nav-active' : ''} onClick={() => setProfileOpen(true)}>Profil</button></nav>
        <div className="header-right"><span className="system-clock"><b>SYS</b> EN LIGNE</span><span className="privacy-status"><i /> CHIFFREMENT ACTIF</span><button className="profile-button" onClick={onLogout} title={`Déconnecter ${session.name}`}>CG</button></div>
      </header>
      <aside className="space-sidebar">
        <span className="sidebar-label">MATRICE COGNITIVE</span>
        {['EMEFA', 'Projets', 'Mémoire', 'Outils', 'Documents', 'Idées'].map((group, index) => <button key={group} className={group === 'EMEFA' ? 'selected' : ''}><span className="module-index">0{index + 1}</span><i style={{ background: palette[group] }} />{group}</button>)}
        <div className="sidebar-signal"><span /><span /><span /><span /><span /><small>SIGNAL NEURAL</small></div>
        <div className="sidebar-bottom"><span>16</span><small>sources synchronisées</small></div>
      </aside>
      <aside className="telemetry-panel" aria-label="Télémétrie EMEFA">
        <div className="telemetry-heading"><span>DIAGNOSTIC</span><i /></div>
        <div className="telemetry-card"><small>NOYAU COGNITIF</small><strong>98.7%</strong><div className="meter"><i style={{ width: '98.7%' }} /></div></div>
        <div className="telemetry-card"><small>LIAISON VOCALE</small><strong className={live ? 'online' : ''}>{live ? 'ACTIVE' : 'VEILLE'}</strong><div className="wave-mini">{Array.from({ length: 18 }, (_, index) => <i key={index} />)}</div></div>
        <div className="radar-widget"><span className="radar-sweep" /><i className="radar-point p1" /><i className="radar-point p2" /><i className="radar-point p3" /><b>RÉSEAU</b><small>16 NŒUDS</small></div>
        <div className="data-stream"><span>FLUX</span><code>7F A2 09 C4</code><code>1B E8 33 D0</code><code>AE 04 F9 71</code></div>
      </aside>
      <div className="cognitive-flux" aria-hidden="true"><span>FLUX COGNITIF</span><div>{Array.from({ length: 24 }, (_, index) => <i key={index} />)}</div><small>SYNCHRONISATION CONTINUE</small></div>
      <main className="voice-stage">
        <div className={`voice-status ${state}`}><span className="status-dot" />{statusCopy[state]}<i className="status-line" /></div>
        <div className="core-zone">
          <div className="core-readout left"><span>CORE</span><strong>EMF-01</strong></div>
          <div className="core-reticle" aria-hidden="true"><i /><i /><i /><i /></div>
          <VoiceOrb state={state} onClick={() => void toggleLive()} />
          <div className="core-readout right"><span>LATENCE</span><strong>TEMPS RÉEL</strong></div>
        </div>
        <div className="voice-copy"><p className="heard">{state === 'listening' && transcript ? `« ${transcript} »` : latestUser ? `« ${latestUser} »` : live ? 'Parlez, je vous écoute…' : 'Touchez le noyau pour commencer à parler'}</p><p className="answer">{answer}</p></div>
        <div className="voice-controls"><button className={live ? 'danger' : ''} onClick={() => void toggleLive()}><span className="mic-symbol">⌁</span>{live ? 'Terminer la conversation' : 'Initialiser la liaison vocale'}</button><small>{live ? 'Conversation continue · interrompez EMEFA à tout moment' : 'Activation unique · échange vocal naturel'}</small></div>
      </main>
      <section className="command-dock"><span className="dock-prompt">›</span><input value={typed} onChange={(event) => { setTyped(event.target.value); if (live) conversation.sendUserActivity() }} onKeyDown={(event) => { if (event.key === 'Enter') void submitTyped() }} placeholder="Écrire à EMEFA — avec ou sans la voix…" aria-label="Écrire une demande" /><button onClick={() => void submitTyped()} disabled={!typed.trim()}>TRANSMETTRE</button></section>
      <div className="model-pill"><span>PROTOCOLE</span><strong>VOICE·LIVE</strong><i>●</i></div>
      {notice && <div className="voice-notice" role="alert">{notice}</div>}
      <ProfilePanel open={profileOpen} firstRun={firstRun} onClose={() => { setProfileOpen(false); setFirstRun(false) }} />
    </div>
  )
}
