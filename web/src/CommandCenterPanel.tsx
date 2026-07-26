import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

type Initiative = {
  initiative_id: string
  title: string
  objective: string
  status: 'proposed' | 'active' | 'paused' | 'completed' | 'cancelled'
  priority: 'low' | 'normal' | 'high' | 'critical'
  risk: 'low' | 'medium' | 'high'
  autonomy_level: number
  next_action: string
  due_date: string | null
}

type Routine = {
  routine_id: string
  name: string
  prompt: string
  schedule_kind: 'manual' | 'daily' | 'weekly'
  schedule_hour: number | null
  schedule_weekday: number | null
  enabled: boolean
  requires_confirmation: boolean
  last_run_at: string | null
}

type RoutineRun = {
  run_id: string
  status: string
  result: string
  action_id: string | null
  started_at: string
}

type Snapshot = {
  initiative_counts: Record<string, number>
  open_task_count: number
  prospect_count: number
  due_follow_up_count: number
  active_routine_count: number
  pending_approval_count: number
  skill_count: number
  recent_runs: RoutineRun[]
}

const statusLabels: Record<string, string> = {
  proposed: 'Proposée', active: 'Active', paused: 'En pause', completed: 'Terminée', cancelled: 'Annulée',
}
const priorityLabels: Record<string, string> = {
  low: 'Basse', normal: 'Normale', high: 'Haute', critical: 'Critique',
}
const weekdays = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

export function CommandCenterPanel({ open, onClose, onApprovalCreated }: {
  open: boolean
  onClose: () => void
  onApprovalCreated: () => void
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [initiatives, setInitiatives] = useState<Initiative[]>([])
  const [routines, setRoutines] = useState<Routine[]>([])
  const [tab, setTab] = useState<'overview' | 'initiatives' | 'routines'>('overview')
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState('')
  const [newInitiative, setNewInitiative] = useState({ title: '', objective: '', priority: 'normal', next_action: '' })
  const [newRoutine, setNewRoutine] = useState({ name: '', prompt: '', schedule_kind: 'manual', schedule_hour: '8', schedule_weekday: '0' })

  const reload = useCallback(async () => {
    try {
      const [nextSnapshot, nextInitiatives, nextRoutines] = await Promise.all([
        api<Snapshot>('/v1/command-center/snapshot'),
        api<Initiative[]>('/v1/command-center/initiatives'),
        api<Routine[]>('/v1/command-center/routines'),
      ])
      setSnapshot(nextSnapshot)
      setInitiatives(nextInitiatives)
      setRoutines(nextRoutines)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Centre de pilotage indisponible.')
    }
  }, [])

  useEffect(() => {
    if (open) void reload()
  }, [open, reload])

  if (!open) return null

  const createInitiative = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!newInitiative.title.trim()) return
    setBusy('initiative'); setError(''); setStatus('')
    try {
      await api<Initiative>('/v1/command-center/initiatives', {
        method: 'POST',
        body: JSON.stringify({ ...newInitiative, status: 'active', risk: 'low', autonomy_level: 0 }),
      })
      setNewInitiative({ title: '', objective: '', priority: 'normal', next_action: '' })
      setStatus('Initiative ajoutée au suivi d’EMEFA.')
      await reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Création impossible.')
    } finally { setBusy('') }
  }

  const updateInitiative = async (initiativeId: string, changes: Partial<Initiative>) => {
    setBusy(initiativeId); setError(''); setStatus('')
    try {
      await api<Initiative>(`/v1/command-center/initiatives/${initiativeId}`, {
        method: 'PATCH', body: JSON.stringify(changes),
      })
      await reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Mise à jour impossible.')
    } finally { setBusy('') }
  }

  const createRoutine = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!newRoutine.name.trim() || !newRoutine.prompt.trim()) return
    setBusy('routine'); setError(''); setStatus('')
    try {
      const payload: Record<string, unknown> = {
        name: newRoutine.name,
        prompt: newRoutine.prompt,
        schedule_kind: newRoutine.schedule_kind,
        enabled: true,
      }
      if (newRoutine.schedule_kind !== 'manual') payload.schedule_hour = Number(newRoutine.schedule_hour)
      if (newRoutine.schedule_kind === 'weekly') payload.schedule_weekday = Number(newRoutine.schedule_weekday)
      await api<Routine>('/v1/command-center/routines', { method: 'POST', body: JSON.stringify(payload) })
      setNewRoutine({ name: '', prompt: '', schedule_kind: 'manual', schedule_hour: '8', schedule_weekday: '0' })
      setStatus('Routine créée. Les actions sensibles resteront soumises à votre approbation.')
      await reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Création impossible.')
    } finally { setBusy('') }
  }

  const runRoutine = async (routineId: string) => {
    setBusy(routineId); setError(''); setStatus('')
    try {
      const run = await api<RoutineRun>(`/v1/command-center/routines/${routineId}/run`, { method: 'POST' })
      setStatus(run.status === 'awaiting_approval'
        ? 'Routine préparée. Une approbation vous attend avant toute action sensible.'
        : run.result || 'Routine terminée.')
      if (run.action_id) onApprovalCreated()
      await reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Exécution impossible.')
    } finally { setBusy('') }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="command-center-title">
      <section className="profile-panel command-center-panel">
        <header className="profile-head">
          <div>
            <span className="profile-section">CENTRE DE PILOTAGE</span>
            <h2 id="command-center-title">Priorités, initiatives et routines</h2>
            <p>Une vue réelle de ce qu’EMEFA suit, prépare et attend de vous.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer le centre de pilotage">✕</button>
        </header>

        <nav className="pilot-tabs" aria-label="Sections du centre de pilotage">
          <button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>Vue d’ensemble</button>
          <button className={tab === 'initiatives' ? 'active' : ''} onClick={() => setTab('initiatives')}>Initiatives</button>
          <button className={tab === 'routines' ? 'active' : ''} onClick={() => setTab('routines')}>Routines</button>
        </nav>

        {error && <div className="form-error" role="alert">{error}</div>}
        {status && <div className="pilot-success" role="status">{status}</div>}

        {tab === 'overview' && (
          <div className="pilot-overview">
            <div className="pilot-metrics">
              <article><strong>{snapshot?.initiative_counts.active ?? '—'}</strong><span>initiatives actives</span></article>
              <article><strong>{snapshot?.open_task_count ?? '—'}</strong><span>tâches ouvertes</span></article>
              <article><strong>{snapshot?.due_follow_up_count ?? '—'}</strong><span>relances dues</span></article>
              <article><strong>{snapshot?.active_routine_count ?? '—'}</strong><span>routines actives</span></article>
              <article className={(snapshot?.pending_approval_count ?? 0) > 0 ? 'metric-alert' : ''}><strong>{snapshot?.pending_approval_count ?? '—'}</strong><span>approbations en attente</span></article>
              <article><strong>{snapshot?.skill_count ?? '—'}</strong><span>compétences disponibles</span></article>
            </div>
            <div className="pilot-summary-grid">
              <div><span className="profile-section">FOCUS ACTUEL</span>{initiatives.filter((item) => !['completed', 'cancelled'].includes(item.status)).slice(0, 4).map((item) => <button key={item.initiative_id} className="pilot-focus" onClick={() => setTab('initiatives')}><span className={`priority-dot p-${item.priority}`} /><strong>{item.title}</strong><small>{item.next_action || item.objective || 'Prochaine action à définir'}</small></button>)}</div>
              <div><span className="profile-section">DERNIÈRES EXÉCUTIONS</span>{snapshot?.recent_runs.length ? snapshot.recent_runs.slice(0, 4).map((run) => <div key={run.run_id} className="pilot-run"><strong>{run.status === 'completed' ? 'Terminée' : run.status === 'awaiting_approval' ? 'Approbation requise' : run.status}</strong><small>{run.result || 'Aucun résultat enregistré'}</small></div>) : <p className="profile-status">Aucune routine exécutée.</p>}</div>
            </div>
          </div>
        )}

        {tab === 'initiatives' && (
          <div className="pilot-list-layout">
            <form className="pilot-create" onSubmit={createInitiative}>
              <span className="profile-section">NOUVELLE INITIATIVE</span>
              <label>Titre<input value={newInitiative.title} onChange={(event) => setNewInitiative({ ...newInitiative, title: event.target.value })} placeholder="Ex. Lancer une nouvelle offre" required /></label>
              <label>Objectif<textarea value={newInitiative.objective} onChange={(event) => setNewInitiative({ ...newInitiative, objective: event.target.value })} placeholder="Résultat attendu" /></label>
              <label>Prochaine action<input value={newInitiative.next_action} onChange={(event) => setNewInitiative({ ...newInitiative, next_action: event.target.value })} placeholder="Étape concrète suivante" /></label>
              <label>Priorité<select value={newInitiative.priority} onChange={(event) => setNewInitiative({ ...newInitiative, priority: event.target.value })}><option value="low">Basse</option><option value="normal">Normale</option><option value="high">Haute</option><option value="critical">Critique</option></select></label>
              <button className="primary-button" disabled={busy === 'initiative'}>{busy === 'initiative' ? 'Ajout…' : 'Ajouter au pilotage'}</button>
            </form>
            <div className="pilot-items">
              {initiatives.length === 0 && <p className="profile-status">Aucune initiative. Ajoutez le premier objectif structuré.</p>}
              {initiatives.map((item) => (
                <article key={item.initiative_id} className={`initiative-card priority-${item.priority}`}>
                  <header><div><span>{priorityLabels[item.priority]} · risque {item.risk}</span><strong>{item.title}</strong></div><select aria-label={`État de ${item.title}`} value={item.status} disabled={busy === item.initiative_id} onChange={(event) => void updateInitiative(item.initiative_id, { status: event.target.value as Initiative['status'] })}>{Object.entries(statusLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></header>
                  {item.objective && <p>{item.objective}</p>}
                  <footer><span>PROCHAINE ACTION</span><strong>{item.next_action || 'À définir avec EMEFA'}</strong></footer>
                </article>
              ))}
            </div>
          </div>
        )}

        {tab === 'routines' && (
          <div className="pilot-list-layout">
            <form className="pilot-create" onSubmit={createRoutine}>
              <span className="profile-section">NOUVELLE ROUTINE</span>
              <label>Nom<input value={newRoutine.name} onChange={(event) => setNewRoutine({ ...newRoutine, name: event.target.value })} placeholder="Ex. Revue du lundi" required /></label>
              <label>Instruction<textarea value={newRoutine.prompt} onChange={(event) => setNewRoutine({ ...newRoutine, prompt: event.target.value })} placeholder="Ce qu’EMEFA doit préparer" required /></label>
              <label>Fréquence<select value={newRoutine.schedule_kind} onChange={(event) => setNewRoutine({ ...newRoutine, schedule_kind: event.target.value })}><option value="manual">À la demande</option><option value="daily">Chaque jour</option><option value="weekly">Chaque semaine</option></select></label>
              {newRoutine.schedule_kind !== 'manual' && <label>Heure locale<input type="number" min="0" max="23" value={newRoutine.schedule_hour} onChange={(event) => setNewRoutine({ ...newRoutine, schedule_hour: event.target.value })} /></label>}
              {newRoutine.schedule_kind === 'weekly' && <label>Jour<select value={newRoutine.schedule_weekday} onChange={(event) => setNewRoutine({ ...newRoutine, schedule_weekday: event.target.value })}>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label>}
              <p className="routine-safety">Toute action externe ou sensible demandera votre approbation avant exécution.</p>
              <button className="primary-button" disabled={busy === 'routine'}>{busy === 'routine' ? 'Création…' : 'Créer la routine'}</button>
            </form>
            <div className="pilot-items">
              {routines.length === 0 && <p className="profile-status">Aucune routine configurée.</p>}
              {routines.map((routine) => (
                <article key={routine.routine_id} className="routine-card">
                  <header><div><span>{routine.enabled ? 'ACTIVE' : 'EN PAUSE'}</span><strong>{routine.name}</strong></div><button onClick={() => void runRoutine(routine.routine_id)} disabled={busy === routine.routine_id}>{busy === routine.routine_id ? '…' : 'Exécuter'}</button></header>
                  <p>{routine.prompt}</p>
                  <footer><small>{routine.schedule_kind === 'manual' ? 'À la demande' : routine.schedule_kind === 'daily' ? `Chaque jour à ${routine.schedule_hour} h` : `${weekdays[routine.schedule_weekday ?? 0]} à ${routine.schedule_hour} h`}</small><small>{routine.last_run_at ? `Dernière exécution : ${routine.last_run_at.slice(0, 16).replace('T', ' ')}` : 'Jamais exécutée'}</small></footer>
                </article>
              ))}
            </div>
          </div>
        )}

        <footer className="profile-actions"><button type="button" className="profile-later" onClick={onClose}>Fermer</button></footer>
      </section>
    </div>
  )
}
