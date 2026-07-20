/* oxlint-disable react/only-export-components */
import { useEffect, useState } from 'react'
import { api } from './App'

export type AssistantProfile = { assistant_id: string; name: string; primary_language: string; interaction_style: string }
export type BusinessProfile = {
  assistant_id: string; owner_name: string; owner_role: string; company_name: string; industry: string
  offer: string; target_customers: string; goals: string; constraints_notes: string
}

export const isBusinessEmpty = (profile: BusinessProfile): boolean =>
  !(profile.owner_name || profile.owner_role || profile.company_name || profile.industry
    || profile.offer || profile.target_customers || profile.goals || profile.constraints_notes)

const BUSINESS_FIELDS: Array<{ key: keyof Omit<BusinessProfile, 'assistant_id'>; label: string; long?: boolean; hint?: string }> = [
  { key: 'owner_name', label: 'Votre nom' },
  { key: 'owner_role', label: 'Votre rôle' },
  { key: 'company_name', label: 'Entreprise' },
  { key: 'industry', label: 'Secteur' },
  { key: 'offer', label: 'Votre offre', long: true, hint: 'Produits ou services que vous proposez' },
  { key: 'target_customers', label: 'Clients cibles', long: true },
  { key: 'goals', label: 'Objectifs', long: true },
  { key: 'constraints_notes', label: 'Contraintes et notes', long: true },
]

export function ProfilePanel({ open, firstRun, onClose }: { open: boolean; firstRun: boolean; onClose: () => void }) {
  const [assistant, setAssistant] = useState<AssistantProfile | null>(null)
  const [business, setBusiness] = useState<BusinessProfile | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'saved' | 'error'>('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setStatus('loading'); setError('')
    Promise.all([
      api<AssistantProfile>('/v1/assistant/profile'),
      api<BusinessProfile>('/v1/assistant/business'),
    ]).then(([profileData, businessData]) => {
      setAssistant(profileData); setBusiness(businessData); setStatus('ready')
    }).catch((cause) => {
      setStatus('error'); setError(cause instanceof Error ? cause.message : 'Chargement impossible.')
    })
  }, [open])

  if (!open) return null

  const save = async () => {
    if (!assistant || !business) return
    setStatus('saving'); setError('')
    try {
      const savedAssistant = await api<AssistantProfile>('/v1/assistant/profile', {
        method: 'PATCH',
        body: JSON.stringify({ name: assistant.name.trim() || 'EMEFA', interaction_style: assistant.interaction_style }),
      })
      const { assistant_id: _ignored, ...businessFields } = business
      const savedBusiness = await api<BusinessProfile>('/v1/assistant/business', {
        method: 'PATCH',
        body: JSON.stringify(businessFields),
      })
      setAssistant(savedAssistant); setBusiness(savedBusiness); setStatus('saved')
    } catch (cause) {
      setStatus('error'); setError(cause instanceof Error ? cause.message : 'Enregistrement impossible.')
    }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="profile-title">{firstRun ? 'Faisons connaissance' : 'Profil'}</h2>
            <p>{firstRun
              ? 'Présentez votre activité : EMEFA s’en servira pour personnaliser chaque réponse.'
              : 'Ces informations personnalisent les réponses d’EMEFA. Modifiez-les à tout moment.'}</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer le profil">✕</button>
        </header>
        {status === 'loading' && <p className="profile-status">Chargement…</p>}
        {assistant && business && status !== 'loading' && (
          <form className="profile-form" onSubmit={(event) => { event.preventDefault(); void save() }}>
            <span className="profile-section">Votre assistante</span>
            <label htmlFor="assistant-name">Nom de l’assistante</label>
            <input id="assistant-name" value={assistant.name} maxLength={80}
              onChange={(event) => setAssistant({ ...assistant, name: event.target.value })} />
            <label htmlFor="assistant-style">Style d’interaction</label>
            <input id="assistant-style" value={assistant.interaction_style} maxLength={2000}
              placeholder="Ex. : directe, chaleureuse, réponses courtes"
              onChange={(event) => setAssistant({ ...assistant, interaction_style: event.target.value })} />
            <span className="profile-section">Votre activité</span>
            {BUSINESS_FIELDS.map(({ key, label, long, hint }) => (
              <div key={key} className="profile-field">
                <label htmlFor={`business-${key}`}>{label}</label>
                {long ? (
                  <textarea id={`business-${key}`} value={business[key]} rows={2} maxLength={2000} placeholder={hint}
                    onChange={(event) => setBusiness({ ...business, [key]: event.target.value })} />
                ) : (
                  <input id={`business-${key}`} value={business[key]} maxLength={200} placeholder={hint}
                    onChange={(event) => setBusiness({ ...business, [key]: event.target.value })} />
                )}
              </div>
            ))}
            {error && <div className="form-error" role="alert">{error}</div>}
            <footer className="profile-actions">
              {status === 'saved' && <span className="profile-saved" role="status">Profil enregistré</span>}
              <button type="button" className="profile-later" onClick={onClose}>{firstRun ? 'Plus tard' : 'Fermer'}</button>
              <button type="submit" className="primary-button" disabled={status === 'saving'}>
                {status === 'saving' ? 'Enregistrement…' : 'Enregistrer'}
              </button>
            </footer>
          </form>
        )}
        {status === 'error' && !assistant && <div className="form-error" role="alert">{error}</div>}
      </section>
    </div>
  )
}
