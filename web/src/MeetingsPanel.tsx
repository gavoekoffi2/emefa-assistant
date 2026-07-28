import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

type MeetingSummary = {
  meeting_id: string; title: string; occurred_at: string; participants: string
  document_id: string | null; summary: string; decision_count: number; action_count: number
}
type OpenAction = {
  meeting_action_id: string; description: string; owner: string
  due_date: string | null; meeting_title: string
}
type Payload = { meetings: MeetingSummary[]; open_actions: OpenAction[] }

export function MeetingsPanel({ open, onClose, onAsk }: {
  open: boolean
  onClose: () => void
  onAsk: (prompt: string) => void
}) {
  const [payload, setPayload] = useState<Payload | null>(null)
  const [notes, setNotes] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    api<Payload>('/v1/meetings')
      .then((data) => { setPayload(data); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) { setNotes(''); reload() } }, [open, reload])

  if (!open) return null

  const remove = async (meetingId: string) => {
    setBusy(meetingId)
    try {
      await api<void>(`/v1/meetings/${meetingId}`, { method: 'DELETE' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Suppression impossible.')
    } finally { setBusy('') }
  }

  // Dictated or pasted notes go through the assistant, not through a form:
  // she is the one who identifies decisions, owners and deadlines.
  const submitNotes = () => {
    const text = notes.trim()
    if (!text) return
    onClose()
    onAsk(
      'Voici mes notes de réunion. Rédige le compte rendu professionnel, identifie les décisions, '
      + 'les actions avec leur responsable et leur échéance, mets à jour le projet concerné et '
      + `crée les tâches nécessaires.\n\n${text}`,
    )
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="meetings-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="meetings-title">Réunions</h2>
            <p>Dictez ou collez vos notes : EMEFA en tire le compte rendu, les décisions, les actions et les tâches.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer les réunions">✕</button>
        </header>

        {error && <div className="form-error" role="alert">{error}</div>}

        <div className="profile-field">
          <label htmlFor="meeting-notes">Notes de la réunion</label>
          <textarea
            id="meeting-notes"
            rows={5}
            maxLength={20000}
            value={notes}
            placeholder="Qui était présent, ce qui a été décidé, qui fait quoi et pour quand…"
            onChange={(event) => setNotes(event.target.value)}
          />
          <button type="button" className="primary-button" onClick={submitNotes} disabled={!notes.trim()}>
            Transformer en compte rendu
          </button>
        </div>

        {payload && payload.open_actions.length > 0 && (
          <div className="task-group">
            <span className="profile-section">Actions attendues d’autres personnes</span>
            {payload.open_actions.map((action) => (
              <div key={action.meeting_action_id} className="task-row">
                <div>
                  <strong>{action.owner}</strong>
                  <small>{action.description}</small>
                  <small>{action.meeting_title}{action.due_date ? ` · pour le ${action.due_date}` : ''}</small>
                </div>
                <button onClick={() => { onClose(); onAsk(`Prépare une relance pour ${action.owner} au sujet de : ${action.description}.`) }}>
                  Relancer
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="task-group">
          <span className="profile-section">Réunions enregistrées</span>
          {payload === null && !error && <p className="profile-status">Chargement…</p>}
          {payload && payload.meetings.length === 0 && (
            <p className="profile-status">Aucune réunion enregistrée pour l’instant.</p>
          )}
          {payload?.meetings.map((meeting) => (
            <div key={meeting.meeting_id} className="task-row">
              <div>
                <strong>{meeting.title}</strong>
                <small>{meeting.occurred_at}{meeting.participants ? ` · ${meeting.participants}` : ''}</small>
                <small>{meeting.decision_count} décision(s) · {meeting.action_count} action(s)</small>
              </div>
              <div className="row-actions">
                {meeting.document_id && (
                  <a className="row-link" href={`/v1/documents/${meeting.document_id}/download`}>Compte rendu</a>
                )}
                <button
                  className="row-delete"
                  onClick={() => void remove(meeting.meeting_id)}
                  disabled={busy === meeting.meeting_id}
                  aria-label={`Supprimer ${meeting.title}`}
                >{busy === meeting.meeting_id ? '…' : 'Supprimer'}</button>
              </div>
            </div>
          ))}
        </div>

        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
        </footer>
      </section>
    </div>
  )
}
