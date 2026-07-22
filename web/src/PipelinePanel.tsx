import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

export type ProspectItem = {
  prospect_id: string; name: string; company: string; email: string; phone: string
  stage: string; notes: string; next_action: string; next_action_date: string | null
  follow_up_due: boolean; created_at: string
}

const STAGES: Array<{ key: string; label: string }> = [
  { key: 'proposition', label: 'Proposition' },
  { key: 'qualifié', label: 'Qualifié' },
  { key: 'contacté', label: 'Contacté' },
  { key: 'nouveau', label: 'Nouveau' },
]

export function PipelinePanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [prospects, setProspects] = useState<ProspectItem[] | null>(null)
  const [error, setError] = useState('')

  const reload = useCallback(() => {
    api<ProspectItem[]>('/v1/prospects')
      .then((items) => { setProspects(items); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) { setProspects(null); reload() } }, [open, reload])

  if (!open) return null

  const dueCount = prospects?.filter((p) => p.follow_up_due).length ?? 0

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="pipeline-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="pipeline-title">Pipeline commercial</h2>
            <p>
              {dueCount > 0
                ? `${dueCount} relance${dueCount > 1 ? 's' : ''} due${dueCount > 1 ? 's' : ''} — demandez à EMEFA de préparer les e-mails.`
                : 'Dites « ajoute [nom] au pipeline » ou « passe [nom] en qualifié » pour le faire évoluer.'}
            </p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer le pipeline">✕</button>
        </header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {prospects === null && !error && <p className="profile-status">Chargement…</p>}
        {prospects !== null && prospects.length === 0 && (
          <p className="profile-status">Pipeline vide. Mentionnez un client potentiel à EMEFA pour commencer le suivi.</p>
        )}
        {prospects !== null && STAGES.map(({ key, label }) => {
          const group = prospects.filter((p) => p.stage === key)
          if (group.length === 0) return null
          return (
            <div key={key} className="task-group">
              <span className="profile-section">{label} · {group.length}</span>
              {group.map((prospect) => (
                <div key={prospect.prospect_id} className={`task-row prospect-row${prospect.follow_up_due ? ' due' : ''}`}>
                  <div>
                    <strong>{prospect.name}{prospect.company && <em> — {prospect.company}</em>}</strong>
                    {prospect.next_action && (
                      <small>
                        {prospect.follow_up_due ? '⚠ Relance due' : 'À faire'} : {prospect.next_action}
                        {prospect.next_action_date && ` (${prospect.next_action_date})`}
                      </small>
                    )}
                    {prospect.notes && <small>{prospect.notes}</small>}
                  </div>
                  {prospect.follow_up_due && <span className="due-badge">RELANCE</span>}
                </div>
              ))}
            </div>
          )
        })}
        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
          <button type="button" className="primary-button" onClick={reload}>Actualiser</button>
        </footer>
      </section>
    </div>
  )
}
