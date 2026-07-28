import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

export type Initiative = {
  initiative_id: string
  type: string
  title: string
  reason: string
  next_action: string
  autonomy_level: number
  risk: string
  status: string
  requires_validation: boolean
  deadline: string | null
  created_at: string
}

type Listing = { initiatives: Initiative[]; counts: Record<string, number> }
type Curator = { date: string; text: string; tokens_today: number; pricing_configured: boolean }

/** Plain-language autonomy levels. The number alone means nothing to the user. */
const autonomyCopy: Record<number, string> = {
  0: 'Observation',
  1: 'Suggestion',
  2: 'Préparation sans envoi',
  3: 'Exécution locale',
  4: 'Modification de vos données',
  5: 'Action externe — accord obligatoire',
}

export function CommandCenterPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [listing, setListing] = useState<Listing | null>(null)
  const [curator, setCurator] = useState<Curator | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    api<Listing>('/v1/initiatives')
      .then((data) => { setListing(data); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
    api<Curator>('/v1/initiatives/curator').then(setCurator).catch(() => setCurator(null))
  }, [])

  useEffect(() => { if (open) { setListing(null); reload() } }, [open, reload])

  if (!open) return null

  const act = async (initiative: Initiative, action: 'approve' | 'dismiss') => {
    setBusy(initiative.initiative_id)
    try {
      await api<unknown>(`/v1/initiatives/${initiative.initiative_id}/${action}`, { method: 'POST' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Action impossible.')
    } finally { setBusy('') }
  }

  const refresh = async () => {
    setBusy('refresh')
    try {
      await api<unknown>('/v1/initiatives/refresh', { method: 'POST' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Analyse impossible.')
    } finally { setBusy('') }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="command-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="command-title">Centre de commande</h2>
            <p>Ce qu’EMEFA a remarqué sans qu’on le lui demande. Elle propose ; vous décidez.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer le centre de commande">✕</button>
        </header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {listing === null && !error && <p className="profile-status">Chargement…</p>}
        {listing !== null && listing.initiatives.length === 0 && (
          <p className="profile-status">Rien à signaler. EMEFA analyse vos tâches, votre pipeline et sa mémoire à intervalle régulier.</p>
        )}
        {listing?.initiatives.map((initiative) => (
          <div key={initiative.initiative_id} className="task-row initiative-row">
            <div>
              <span className="memory-category">{autonomyCopy[initiative.autonomy_level] ?? initiative.type}</span>
              <strong>{initiative.title}</strong>
              <small>{initiative.reason}</small>
              <small className="initiative-next">Prochaine étape : {initiative.next_action}</small>
              {initiative.requires_validation && (
                <small className="initiative-gate">Votre accord est requis avant toute exécution.</small>
              )}
            </div>
            <div className="initiative-actions">
              <button onClick={() => void act(initiative, 'approve')} disabled={busy === initiative.initiative_id}>Traiter</button>
              <button className="profile-later" onClick={() => void act(initiative, 'dismiss')} disabled={busy === initiative.initiative_id}>Ignorer</button>
            </div>
          </div>
        ))}
        {curator && (
          <div className="task-group">
            <span className="profile-section">Entretien</span>
            <pre className="curator-report">{curator.text}</pre>
          </div>
        )}
        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={() => void refresh()} disabled={busy === 'refresh'}>
            {busy === 'refresh' ? 'Analyse…' : 'Analyser maintenant'}
          </button>
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
        </footer>
      </section>
    </div>
  )
}
