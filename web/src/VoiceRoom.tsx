import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useConversation } from '@elevenlabs/react'
import { api, BrandMark, graphNodes, palette, statusCopy, VoiceOrb } from './App'
import { isBusinessEmpty, ProfilePanel } from './ProfilePanel'
import { TasksPanel } from './TasksPanel'
import { MemoryPanel } from './MemoryPanel'
import { PipelinePanel } from './PipelinePanel'

// three.js is heavy; load the hologram as its own chunk so the shell stays light.
const HolographicUniverse = lazy(() =>
  import('./HolographicUniverse').then((module) => ({ default: module.HolographicUniverse })),
)
import type { BusinessProfile } from './ProfilePanel'
import type { Session, VoiceState } from './App'

type ConversationTurn = { id: string; role: 'user' | 'assistant'; text: string }
type SignedSession = { signed_url: string }
type VoiceMessage = { message?: string; source?: string; role?: string }
type AgentRun = {
  status: 'completed' | 'confirmation_required' | 'blocked' | 'failed' | 'rejected'
  answer?: string | null
  error?: string | null
  pending_action?: { name: string; arguments: Record<string, unknown> } | null
  action_id?: string | null
}
type PendingApproval = { action_id: string; name: string; arguments: Record<string, unknown> }
type DemoScenario = { id: string; title: string; prompt: string; status: 'live' | 'assisted' | 'preview'; note: string }

const scenarioStatusLabel: Record<DemoScenario['status'], string> = {
  live: 'RÉEL',
  assisted: 'ASSISTÉ',
  preview: 'APERÇU',
}
type SystemStatus = {
  brain_configured: boolean
  voice_configured: boolean
  skills: Array<{ name: string; risk: string }>
  open_task_count: number
  schema_version: number
}

const skillLabels: Record<string, string> = {
  reset_business_profile: 'Effacer le profil professionnel',
  update_business_profile: 'Mettre à jour le profil professionnel',
  get_profiles: 'Consulter les profils',
  forget_memory: 'Oublier un souvenir',
  email_send: 'Envoyer un e-mail',
  email_create_draft: 'Créer un brouillon d’e-mail',
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
  const [tasksOpen, setTasksOpen] = useState(false)
  const [memoryOpen, setMemoryOpen] = useState(false)
  const [pipelineOpen, setPipelineOpen] = useState(false)
  const [firstRun, setFirstRun] = useState(false)
  const [approval, setApproval] = useState<PendingApproval | null>(null)
  const [deciding, setDeciding] = useState(false)
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [morningBrief, setMorningBrief] = useState<string | null>(null)
  const [scenarios, setScenarios] = useState<DemoScenario[]>([])
  const [scenariosOpen, setScenariosOpen] = useState(false)

  useEffect(() => {
    api<{ text: string }>('/v1/briefings/today')
      .then((briefing) => setMorningBrief(briefing.text))
      .catch(() => undefined)
    api<DemoScenario[]>('/v1/demo/scenarios')
      .then(setScenarios)
      .catch(() => undefined)
  }, [])

  const showMorningBrief = () => {
    if (!morningBrief) return
    setAnswer(morningBrief)
    setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'assistant', text: morningBrief }])
    setMorningBrief(null)
  }

  const refreshSystem = () => {
    api<SystemStatus>('/v1/system/status').then(setSystem).catch(() => undefined)
  }

  useEffect(() => {
    refreshSystem()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasksOpen])

  useEffect(() => {
    api<BusinessProfile>('/v1/assistant/business')
      .then((profile) => {
        if (isBusinessEmpty(profile)) { setFirstRun(true); setProfileOpen(true) }
      })
      .catch(() => undefined)
    api<PendingApproval[]>('/v1/agent/approvals')
      .then((pending) => { if (pending.length > 0) setApproval(pending[0]) })
      .catch(() => undefined)
  }, [])


  const settleState = (next: VoiceState) => {
    // Reflect the real backend outcome, then relax back to the resting
    // state (listening if a live voice session is up, idle otherwise).
    setState(next)
    if (next === 'success') {
      window.setTimeout(() => {
        setState((current) => current === 'success'
          ? (conversation.status === 'connected' ? 'listening' : 'idle')
          : current)
      }, 2200)
    }
  }

  const applyAgentRun = (run: AgentRun) => {
    let text: string
    let outcome: VoiceState = 'success'
    if (run.status === 'completed' && run.answer) text = run.answer
    else if (run.status === 'rejected') text = run.answer || 'Action annulée. Rien n’a été exécuté.'
    else if (run.status === 'confirmation_required') {
      const label = skillLabels[run.pending_action?.name ?? ''] || run.pending_action?.name || 'cette action'
      text = `Avant de continuer, EMEFA attend votre approbation pour : ${label}.`
      outcome = 'awaiting'
      if (run.action_id && run.pending_action) {
        setApproval({ action_id: run.action_id, name: run.pending_action.name, arguments: run.pending_action.arguments })
      }
    } else if (run.status === 'blocked') { text = 'Cette action est bloquée par la politique de sécurité d’EMEFA.'; outcome = 'error' }
    else { text = agentErrorCopy[run.error ?? ''] || 'La demande n’a pas abouti.'; outcome = 'error' }
    setAnswer(text)
    setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'assistant', text }])
    settleState(outcome)
    refreshSystem()
  }

  const decideApproval = async (approve: boolean) => {
    if (!approval || deciding) return
    setDeciding(true); setState('thinking')
    try {
      const run = await api<AgentRun>(`/v1/agent/approvals/${approval.action_id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ approve }),
      })
      setApproval(null)
      applyAgentRun(run)

      // If we have an active conversation and the action was approved, send the result as a contextual update
      if (approve && conversation.status === 'connected' && run.status === 'completed' && run.answer) {
        conversation.sendContextualUpdate(run.answer)
      }
    } catch (cause) {
      setState('error')
      setNotice(cause instanceof Error ? cause.message : 'La décision n’a pas pu être transmise.')
    } finally {
      setDeciding(false)
    }
  }

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

  // During a live voice session, actions prepared orally create pending
  // approvals server-side; poll so the card surfaces without a reload.
  useEffect(() => {
    if (!live) return
    const timer = setInterval(() => {
      api<PendingApproval[]>('/v1/agent/approvals')
        .then((pending) => { if (pending.length > 0) setApproval((current) => current ?? pending[0]) })
        .catch(() => undefined)
    }, 4000)
    return () => clearInterval(timer)
  }, [live])

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
        clientTools: {
          emefa_execute: async ({ request }: { request: string }) => {
            try {
              const run = await api<AgentRun>('/v1/agent/runs', {
                method: 'POST',
                body: JSON.stringify({ message: request }),
                credentials: 'include',
              })

              if (run.status === 'completed' && run.answer) {
                return run.answer
              } else if (run.status === 'confirmation_required' && run.action_id && run.pending_action) {
                setApproval({
                  action_id: run.action_id,
                  name: run.pending_action.name,
                  arguments: run.pending_action.arguments,
                })
                return 'Une approbation est requise pour cette action.'
              } else if (run.error) {
                return `Erreur: ${agentErrorCopy[run.error] || run.error}`
              }
              return 'Action terminée sans résultat.'
            } catch (error) {
              return `Erreur réseau: ${error instanceof Error ? error.message : 'Impossible de contacter le serveur EMEFA.'}`
            }
          },
        },
      })
      return true
    } catch (cause) {
      setState('error')
      const denied = cause instanceof DOMException && ['NotAllowedError', 'PermissionDeniedError'].includes(cause.name)
      setNotice(denied ? 'Autorisez le microphone pour parler directement à EMEFA.' : cause instanceof Error ? cause.message : 'EMEFA ne peut pas ouvrir la conversation vocale.')
      return false
    }
  }

  const toggleLive = async () => {
    if (live) { await conversation.endSession(); return }
    await startRealtime()
  }

  const startProfileInterview = async () => {
    setProfileOpen(false)
    setFirstRun(false)
    if (conversation.status !== 'connected') {
      const connected = await startRealtime()
      if (!connected) return
    }
    conversation.sendContextualUpdate(
      'L’utilisateur choisit un entretien de personnalisation. Pose une seule question courte à la fois. '
      + 'Commence par son nom et son rôle, puis son activité, ses clients, ses objectifs et ses préférences de travail. '
      + 'Après chaque réponse, appelle emefa_execute pour enregistrer uniquement les informations confirmées dans le profil professionnel. '
      + 'Ne dis jamais qu’une information est enregistrée si le résultat de l’outil ne le confirme pas.',
    )
    conversation.sendUserMessage('Je souhaite que tu apprennes à me connaître pour mieux travailler avec moi.')
  }

  const sendMessage = async (value: string) => {
    setNotice(''); setTranscript(value)
    setHistory((current) => [...current.slice(-7), { id: crypto.randomUUID(), role: 'user', text: value }])
    setState('thinking')
    if (conversation.status === 'connected') { conversation.sendUserMessage(value); return }
    try {
      const run = await api<AgentRun>('/v1/agent/runs', { method: 'POST', body: JSON.stringify({ message: value }) })
      applyAgentRun(run)
    } catch (cause) {
      setState('error')
      setNotice(cause instanceof Error ? cause.message : 'La demande n’a pas abouti.')
    }
  }

  const submitTyped = () => {
    const value = typed.trim()
    if (!value) return
    setTyped('')
    void sendMessage(value)
  }

  const askBrief = () => void sendMessage('Qu’est-ce qui mérite mon attention aujourd’hui ?')

  const runScenario = (scenario: DemoScenario) => {
    setScenariosOpen(false)
    void sendMessage(scenario.prompt)
  }
  const latestUser = useMemo(() => [...history].reverse().find((turn) => turn.role === 'user')?.text, [history])

  return (
    <div className={`jarvis-shell state-${state}`}>
      <Suspense fallback={null}>
        <HolographicUniverse activeNodes={activeNodes} voiceState={state} />
      </Suspense>
      <div className="hud-atmosphere" aria-hidden="true"><span className="scan-beam" /><span className="film-grain" /></div>
      <div className="hud-frame" aria-hidden="true"><i className="corner top-left" /><i className="corner top-right" /><i className="corner bottom-left" /><i className="corner bottom-right" /></div>
      <div className="space-vignette" />
      <header className="jarvis-header">
        <div className="brand-row"><BrandMark /><div><strong>EMEFA</strong><small>INTELLIGENCE COGNITIVE</small></div></div>
        <nav><button className={profileOpen || tasksOpen || memoryOpen || pipelineOpen ? '' : 'nav-active'} onClick={() => { setProfileOpen(false); setTasksOpen(false); setMemoryOpen(false); setPipelineOpen(false) }}>Univers</button><button className={tasksOpen ? 'nav-active' : ''} onClick={() => { setProfileOpen(false); setMemoryOpen(false); setPipelineOpen(false); setTasksOpen(true) }}>Tâches</button><button className={pipelineOpen ? 'nav-active' : ''} onClick={() => { setProfileOpen(false); setTasksOpen(false); setMemoryOpen(false); setPipelineOpen(true) }}>Pipeline</button><button className={memoryOpen ? 'nav-active' : ''} onClick={() => { setProfileOpen(false); setTasksOpen(false); setPipelineOpen(false); setMemoryOpen(true) }}>Mémoire</button><button className={profileOpen ? 'nav-active' : ''} onClick={() => { setTasksOpen(false); setMemoryOpen(false); setPipelineOpen(false); setProfileOpen(true) }}>Profil</button></nav>
        <div className="header-right"><span className="system-clock"><b>SYS</b> EN LIGNE</span><span className="privacy-status"><i /> {window.location.protocol === 'https:' ? 'CHIFFREMENT ACTIF' : 'CONNEXION LOCALE'}</span><button className="profile-button" onClick={onLogout} title={`Déconnecter ${session.name}`}>CG</button></div>
      </header>
      <aside className="space-sidebar">
        <span className="sidebar-label">MATRICE COGNITIVE</span>
        {['EMEFA', 'Projets', 'Mémoire', 'Outils', 'Documents', 'Idées'].map((group, index) => <button key={group} className={group === 'EMEFA' ? 'selected' : ''}><span className="module-index">0{index + 1}</span><i style={{ background: palette[group] }} />{group}</button>)}
        <div className="sidebar-signal"><span /><span /><span /><span /><span /><small>SIGNAL NEURAL</small></div>
        <div className="sidebar-bottom"><span>{system ? system.skills.length : '—'}</span><small>compétences actives</small></div>
      </aside>
      <aside className="telemetry-panel" aria-label="Télémétrie EMEFA">
        <div className="telemetry-heading"><span>DIAGNOSTIC</span><i /></div>
        <div className="telemetry-card"><small>NOYAU COGNITIF</small><strong className={system?.brain_configured ? 'online' : ''}>{system ? (system.brain_configured ? 'EN LIGNE' : 'NON CONFIGURÉ') : '…'}</strong><div className="meter"><i style={{ width: system?.brain_configured ? '100%' : '6%' }} /></div></div>
        <div className="telemetry-card"><small>LIAISON VOCALE</small><strong className={live ? 'online' : ''}>{live ? 'ACTIVE' : system && !system.voice_configured ? 'NON CONFIGURÉE' : 'VEILLE'}</strong><div className="wave-mini">{Array.from({ length: 18 }, (_, index) => <i key={index} />)}</div></div>
        <div className="radar-widget"><span className="radar-sweep" /><i className="radar-point p1" /><i className="radar-point p2" /><i className="radar-point p3" /><b>SUIVI</b><small>{system ? system.open_task_count : '—'} ENGAGEMENTS</small></div>
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
      {scenariosOpen && scenarios.length > 0 && (
        <div className="scenario-tray" role="menu" aria-label="Scénarios de démonstration">
          <div className="scenario-tray-head"><span>PARCOURS GUIDÉS</span><small>Chaque carte indique ce qui est réel, assisté ou en aperçu.</small></div>
          {scenarios.map((scenario) => (
            <button key={scenario.id} className={`scenario-item s-${scenario.status}`} onClick={() => runScenario(scenario)} role="menuitem">
              <span className="scenario-badge">{scenarioStatusLabel[scenario.status]}</span>
              <strong>{scenario.title}</strong>
              <em>« {scenario.prompt} »</em>
              <small>{scenario.note}</small>
            </button>
          ))}
        </div>
      )}
      <section className="command-dock"><button className={`dock-scenarios${scenariosOpen ? ' active' : ''}`} onClick={() => setScenariosOpen((open) => !open)} disabled={scenarios.length === 0} aria-label="Parcours guidés" title="Parcours guidés">✦</button><span className="dock-prompt">›</span><input value={typed} onChange={(event) => { setTyped(event.target.value); if (live) conversation.sendUserActivity() }} onKeyDown={(event) => { if (event.key === 'Enter') void submitTyped() }} placeholder="Écrire à EMEFA — avec ou sans la voix…" aria-label="Écrire une demande" /><button onClick={() => void submitTyped()} disabled={!typed.trim()}>TRANSMETTRE</button></section>
      <div className="model-pill"><span>PROTOCOLE</span><strong>VOICE·LIVE</strong><i>●</i></div>
      {notice && <div className="voice-notice" role="alert">{notice}</div>}
      {morningBrief && (
        <div className="brief-strip" role="status">
          <span>☀ Votre brief du jour est prêt.</span>
          <button onClick={showMorningBrief}>L’afficher</button>
          <button className="brief-dismiss" onClick={() => setMorningBrief(null)} aria-label="Ignorer le brief">✕</button>
        </div>
      )}
      {approval && (
        <div className="approval-card" role="alertdialog" aria-labelledby="approval-title">
          <span className="approval-badge">APPROBATION REQUISE</span>
          <strong id="approval-title">{skillLabels[approval.name] || approval.name}</strong>
          {Object.keys(approval.arguments).length > 0 && (
            <code className="approval-args">{JSON.stringify(approval.arguments)}</code>
          )}
          <p>EMEFA n’exécutera cette action qu’avec votre accord explicite.</p>
          <div className="approval-actions">
            <button className="approval-reject" onClick={() => void decideApproval(false)} disabled={deciding}>Refuser</button>
            <button className="approval-approve" onClick={() => void decideApproval(true)} disabled={deciding}>{deciding ? 'Traitement…' : 'Approuver'}</button>
          </div>
        </div>
      )}
      <ProfilePanel open={profileOpen} firstRun={firstRun} onClose={() => { setProfileOpen(false); setFirstRun(false) }} onStartInterview={() => void startProfileInterview()} />
      <TasksPanel open={tasksOpen} onClose={() => setTasksOpen(false)} onAskBrief={askBrief} />
      <MemoryPanel open={memoryOpen} onClose={() => setMemoryOpen(false)} />
      <PipelinePanel open={pipelineOpen} onClose={() => setPipelineOpen(false)} />
    </div>
  )
}
