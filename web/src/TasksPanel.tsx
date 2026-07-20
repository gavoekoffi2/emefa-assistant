import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

export type TaskItem = {
  task_id: string; title: string; details: string; due_date: string | null
  status: string; bucket: string; created_at: string
}

const BUCKETS: Array<{ key: string; label: string }> = [
  { key: 'en_retard', label: 'En retard' },
  { key: 'aujourdhui', label: 'Aujourd’hui' },
  { key: 'a_venir', label: 'À venir' },
  { key: 'sans_echeance', label: 'Sans échéance' },
]

export function TasksPanel({ open, onClose, onAskBrief }: {
  open: boolean; onClose: () => void; onAskBrief: () => void
}) {
  const [tasks, setTasks] = useState<TaskItem[] | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const reload = useCallback(() => {
    api<TaskItem[]>('/v1/tasks')
      .then((items) => { setTasks(items); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) { setTasks(null); reload() } }, [open, reload])

  if (!open) return null

  const complete = async (taskId: string) => {
    setBusyId(taskId)
    try {
      await api<TaskItem>(`/v1/tasks/${taskId}/complete`, { method: 'POST' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible de terminer la tâche.')
    } finally { setBusyId('') }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="tasks-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="tasks-title">Tâches et engagements</h2>
            <p>Ce qu’EMEFA suit pour vous. Dites-lui « rappelle-moi de… » pour en ajouter.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer les tâches">✕</button>
        </header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {tasks === null && !error && <p className="profile-status">Chargement…</p>}
        {tasks !== null && tasks.length === 0 && (
          <p className="profile-status">Aucune tâche ouverte. Demandez à EMEFA d’en retenir une.</p>
        )}
        {tasks !== null && tasks.length > 0 && BUCKETS.map(({ key, label }) => {
          const group = tasks.filter((task) => task.bucket === key)
          if (group.length === 0) return null
          return (
            <div key={key} className="task-group">
              <span className={`profile-section bucket-${key}`}>{label}</span>
              {group.map((task) => (
                <div key={task.task_id} className="task-row">
                  <div>
                    <strong>{task.title}</strong>
                    {task.due_date && <small>Échéance : {task.due_date}</small>}
                    {task.details && <small>{task.details}</small>}
                  </div>
                  <button onClick={() => void complete(task.task_id)} disabled={busyId === task.task_id}>
                    {busyId === task.task_id ? '…' : 'Terminer'}
                  </button>
                </div>
              ))}
            </div>
          )
        })}
        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
          <button type="button" className="primary-button" onClick={() => { onClose(); onAskBrief() }}>
            Brief du jour
          </button>
        </footer>
      </section>
    </div>
  )
}
