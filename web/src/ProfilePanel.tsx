/* oxlint-disable react/only-export-components */
import { useEffect, useState } from 'react'
import { api } from './App'

export type AssistantProfile = { assistant_id: string; name: string; primary_language: string; interaction_style: string }
export type BusinessProfile = {
  assistant_id: string; owner_name: string; owner_role: string; company_name: string; industry: string
  offer: string; target_customers: string; goals: string; constraints_notes: string
  website_url: string; website_summary: string
}

type ImportResult = { profile: BusinessProfile; pages_imported: number }

export const isBusinessEmpty = (profile: BusinessProfile): boolean =>
  !(profile.owner_name || profile.owner_role || profile.company_name || profile.industry
    || profile.offer || profile.target_customers || profile.goals || profile.constraints_notes
    || profile.website_url || profile.website_summary)

const BUSINESS_FIELDS: Array<{ key: keyof Omit<BusinessProfile, 'assistant_id' | 'website_summary'>; label: string; long?: boolean; hint?: string }> = [
  { key: 'owner_name', label: 'Votre nom' },
  { key: 'owner_role', label: 'Votre rôle' },
  { key: 'company_name', label: 'Entreprise' },
  { key: 'industry', label: 'Secteur' },
  { key: 'offer', label: 'Votre offre', long: true, hint: 'Produits ou services que vous proposez' },
  { key: 'target_customers', label: 'Clients cibles', long: true },
  { key: 'goals', label: 'Objectifs', long: true },
  { key: 'constraints_notes', label: 'Contraintes et notes', long: true },
  { key: 'website_url', label: 'Site web', hint: 'https://votre-site.com' },
]

export function ProfilePanel({
  open,
  firstRun,
  onClose,
  onStartInterview,
}: {
  open: boolean
  firstRun: boolean
  onClose: () => void
  onStartInterview: () => void
}) {
  const [assistant, setAssistant] = useState<AssistantProfile | null>(null)
  const [business, setBusiness] = useState<BusinessProfile | null>(null)
  const [website, setWebsite] = useState('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'saving' | 'importing' | 'saved' | 'error'>('loading')
  const [error, setError] = useState('')
  const [importedPages, setImportedPages] = useState(0)

  useEffect(() => {
    if (!open) return
    setStatus('loading'); setError(''); setImportedPages(0)
    Promise.all([
      api<AssistantProfile>('/v1/assistant/profile'),
      api<BusinessProfile>('/v1/assistant/business'),
    ]).then(([profileData, businessData]) => {
      setAssistant(profileData)
      setBusiness(businessData)
      setWebsite(businessData.website_url || '')
      setStatus('ready')
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
      const { assistant_id: _ignored, website_summary: _summary, ...businessFields } = business
      const savedBusiness = await api<BusinessProfile>('/v1/assistant/business', {
        method: 'PATCH',
        body: JSON.stringify(businessFields),
      })
      setAssistant(savedAssistant); setBusiness(savedBusiness); setStatus('saved')
    } catch (cause) {
      setStatus('error'); setError(cause instanceof Error ? cause.message : 'Enregistrement impossible.')
    }
  }

  const importWebsite = async () => {
    const url = website.trim()
    if (!url) { setError('Indiquez l’adresse de votre site.'); return }
    setStatus('importing'); setError(''); setImportedPages(0)
    try {
      const result = await api<ImportResult>('/v1/assistant/business/import', {
        method: 'POST', body: JSON.stringify({ url }),
      })
      setBusiness(result.profile)
      setWebsite(result.profile.website_url)
      setImportedPages(result.pages_imported)
      setStatus('saved')
    } catch (cause) {
      setStatus('error')
      setError(cause instanceof Error ? cause.message : 'EMEFA n’a pas pu analyser ce site.')
    }
  }

  const startInterview = () => {
    onClose()
    onStartInterview()
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="profile-title">{firstRun ? 'EMEFA apprend à vous connaître' : 'Personnalisation'}</h2>
            <p>{firstRun
              ? 'Pas de long formulaire. Choisissez la méthode la plus simple pour vous.'
              : 'EMEFA enrichit ce profil pendant vos échanges. Vous gardez le contrôle.'}</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer le profil">✕</button>
        </header>

        {status === 'loading' && <p className="profile-status">Chargement…</p>}
        {assistant && business && status !== 'loading' && (
          <div className="profile-form">
            <section className="onboarding-choice featured">
              <span className="choice-icon" aria-hidden="true">⌁</span>
              <div><strong>Parler avec EMEFA</strong><p>Elle vous pose quelques questions, une à la fois, puis adapte sa façon de travailler avec vous.</p></div>
              <button type="button" className="primary-button" onClick={startInterview}>Commencer l’échange vocal</button>
            </section>

            <section className="onboarding-choice">
              <span className="choice-icon" aria-hidden="true">↗</span>
              <div><strong>Importer votre site</strong><p>EMEFA lit les pages publiques utiles et préremplit automatiquement votre contexte professionnel.</p></div>
              <label className="sr-only" htmlFor="business-website-import">Adresse de votre site</label>
              <div className="website-import-row">
                <input id="business-website-import" type="url" value={website} placeholder="https://votre-site.com"
                  onChange={(event) => setWebsite(event.target.value)} />
                <button type="button" onClick={() => void importWebsite()} disabled={status === 'importing'}>
                  {status === 'importing' ? 'Analyse…' : 'Analyser'}
                </button>
              </div>
              {importedPages > 0 && <p className="profile-saved" role="status">{importedPages} page{importedPages > 1 ? 's' : ''} analysée{importedPages > 1 ? 's' : ''}. EMEFA utilisera désormais ces informations.</p>}
            </section>

            {!firstRun && (
              <details className="profile-advanced">
                <summary>Voir ou corriger les informations</summary>
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
                      <input id={`business-${key}`} value={business[key]} maxLength={key === 'website_url' ? 2000 : 200} placeholder={hint}
                        onChange={(event) => setBusiness({ ...business, [key]: event.target.value })} />
                    )}
                  </div>
                ))}
                {business.website_summary && <p className="website-source-note">Les informations publiques importées restent liées à votre site. Relancez l’analyse pour les actualiser.</p>}
                <button type="button" className="primary-button" onClick={() => void save()} disabled={status === 'saving'}>
                  {status === 'saving' ? 'Enregistrement…' : 'Enregistrer les corrections'}
                </button>
              </details>
            )}

            {error && <div className="form-error" role="alert">{error}</div>}
            <footer className="profile-actions">
              {status === 'saved' && importedPages === 0 && <span className="profile-saved" role="status">Profil enregistré</span>}
              <button type="button" className="profile-later" onClick={onClose}>{firstRun ? 'Continuer sans personnaliser' : 'Fermer'}</button>
            </footer>
          </div>
        )}
        {status === 'error' && !assistant && <div className="form-error" role="alert">{error}</div>}
      </section>
    </div>
  )
}
