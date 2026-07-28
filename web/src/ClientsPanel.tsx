import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

type Contact = {
  contact_id: string; name: string; kind: string; company: string; role: string
  email: string; phone: string; notes: string; status: string
  last_interaction_at: string | null; silent_days: number | null; follow_up_due: boolean
}
type Project = {
  project_id: string; name: string; contact_id: string | null; objective: string
  status: string; health: string; next_step: string; blocker: string
  due_date: string | null; blocked: boolean; late: boolean
}
type Deal = {
  deal_id: string; title: string; contact_id: string | null; amount: number; currency: string
  stage: string; sent_at: string | null; response_due_date: string | null; awaiting_response: boolean
}
type Contract = {
  contract_id: string; title: string; contact_id: string | null; end_date: string | null
  value: number; currency: string; status: string; days_to_expiry: number | null; expiring: boolean
}
type Overview = {
  follow_ups: Array<Contact & { silent_days: number }>
  awaiting_deals: Array<Deal & { contact_name: string; waiting_days: number | null }>
  expiring_contracts: Array<Contract & { contact_name: string }>
  blocked_projects: Array<Project & { contact_name: string }>
  counts: Record<string, number>
}

type Tab = 'overview' | 'contacts' | 'projects' | 'deals' | 'contracts'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'overview', label: 'À traiter' },
  { key: 'contacts', label: 'Contacts' },
  { key: 'projects', label: 'Projets' },
  { key: 'deals', label: 'Devis' },
  { key: 'contracts', label: 'Contrats' },
]

const money = (amount: number, currency: string) =>
  `${Math.round(amount).toLocaleString('fr-FR')} ${currency}`

export function ClientsPanel({ open, onClose, onAsk }: {
  open: boolean
  onClose: () => void
  onAsk: (prompt: string) => void
}) {
  const [tab, setTab] = useState<Tab>('overview')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [contacts, setContacts] = useState<Contact[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [deals, setDeals] = useState<Deal[]>([])
  const [contracts, setContracts] = useState<Contract[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  const reload = useCallback(() => {
    setError('')
    Promise.all([
      api<Overview>('/v1/crm/overview'),
      api<Contact[]>('/v1/crm/contacts'),
      api<Project[]>('/v1/crm/projects'),
      api<Deal[]>('/v1/crm/deals'),
      api<Contract[]>('/v1/crm/contracts'),
    ])
      .then(([o, c, p, d, k]) => { setOverview(o); setContacts(c); setProjects(p); setDeals(d); setContracts(k) })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) reload() }, [open, reload])

  if (!open) return null

  const remove = async (path: string, id: string) => {
    setBusy(id)
    try {
      await api<void>(path, { method: 'DELETE' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Suppression impossible.')
    } finally { setBusy('') }
  }

  const nameOf = (contactId: string | null) =>
    contacts.find((contact) => contact.contact_id === contactId)?.name ?? ''

  const ask = (prompt: string) => { onClose(); onAsk(prompt) }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="clients-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="clients-title">Clients et affaires</h2>
            <p>La mémoire relationnelle d’EMEFA. Demandez-lui « où en est le projet X ? » — elle lit ceci.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer les clients">✕</button>
        </header>

        <div className="segment-row" role="tablist" aria-label="Sections du portefeuille">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              role="tab"
              aria-selected={tab === key}
              className={tab === key ? 'segment-active' : ''}
              onClick={() => setTab(key)}
            >
              {label}
              {key === 'overview' && overview
                ? ` (${overview.counts.follow_ups + overview.counts.awaiting_deals
                  + overview.counts.expiring_contracts + overview.counts.blocked_projects})`
                : ''}
            </button>
          ))}
        </div>

        {error && <div className="form-error" role="alert">{error}</div>}

        {tab === 'overview' && overview && (
          <>
            <Bucket
              title="Clients à relancer"
              empty="Aucun client laissé sans nouvelles."
              items={overview.follow_ups.map((contact) => ({
                id: contact.contact_id,
                title: contact.name + (contact.company ? ` — ${contact.company}` : ''),
                detail: `${contact.silent_days} jours sans échange`,
                prompt: `Prépare une relance pour ${contact.name}.`,
              }))}
              onAsk={ask}
            />
            <Bucket
              title="Devis en attente de réponse"
              empty="Aucun devis en attente."
              items={overview.awaiting_deals.map((deal) => ({
                id: deal.deal_id,
                title: deal.title + (deal.contact_name ? ` — ${deal.contact_name}` : ''),
                detail: `${money(deal.amount, deal.currency)}${deal.waiting_days ? ` · ${deal.waiting_days} jours` : ''}`,
                prompt: `Relance le devis « ${deal.title} ».`,
              }))}
              onAsk={ask}
            />
            <Bucket
              title="Contrats à échéance"
              empty="Aucun contrat proche de son terme."
              items={overview.expiring_contracts.map((contract) => ({
                id: contract.contract_id,
                title: contract.title + (contract.contact_name ? ` — ${contract.contact_name}` : ''),
                detail: `expire dans ${contract.days_to_expiry} jour(s)`,
                prompt: `Que dois-je décider pour le contrat « ${contract.title} » ?`,
              }))}
              onAsk={ask}
            />
            <Bucket
              title="Projets bloqués ou en retard"
              empty="Aucun projet bloqué."
              items={overview.blocked_projects.map((project) => ({
                id: project.project_id,
                title: project.name,
                detail: project.blocker || (project.late ? 'échéance dépassée' : `santé ${project.health}`),
                prompt: `Où en est le projet ${project.name} et comment le débloquer ?`,
              }))}
              onAsk={ask}
            />
          </>
        )}

        {tab === 'contacts' && (
          <Rows
            empty="Aucun contact. Dites à EMEFA « note ce client » pendant une conversation."
            rows={contacts.map((contact) => ({
              id: contact.contact_id,
              title: contact.name,
              badge: contact.kind,
              detail: [contact.company, contact.role, contact.email, contact.phone].filter(Boolean).join(' · '),
              note: contact.follow_up_due ? `À relancer — ${contact.silent_days} jours de silence` : '',
              prompt: `Fais le point sur ${contact.name}.`,
              path: `/v1/crm/contacts/${contact.contact_id}`,
            }))}
            busy={busy} onDelete={remove} onAsk={ask}
          />
        )}

        {tab === 'projects' && (
          <Rows
            empty="Aucun projet suivi."
            rows={projects.map((project) => ({
              id: project.project_id,
              title: project.name,
              badge: `${project.status} · ${project.health}`,
              detail: [nameOf(project.contact_id), project.objective].filter(Boolean).join(' · '),
              note: [project.next_step && `Prochaine étape : ${project.next_step}`,
                project.blocker && `Blocage : ${project.blocker}`,
                project.due_date && `Échéance : ${project.due_date}`].filter(Boolean).join(' — '),
              prompt: `Où en est le projet ${project.name} ?`,
              path: `/v1/crm/projects/${project.project_id}`,
            }))}
            busy={busy} onDelete={remove} onAsk={ask}
          />
        )}

        {tab === 'deals' && (
          <Rows
            empty="Aucun devis enregistré."
            rows={deals.map((deal) => ({
              id: deal.deal_id,
              title: deal.title,
              badge: deal.stage,
              detail: [nameOf(deal.contact_id), money(deal.amount, deal.currency)].filter(Boolean).join(' · '),
              note: [deal.sent_at && `Envoyé le ${deal.sent_at}`,
                deal.response_due_date && `Réponse attendue le ${deal.response_due_date}`,
                deal.awaiting_response && 'En attente de réponse'].filter(Boolean).join(' — '),
              prompt: `Quel est le statut du devis « ${deal.title} » ?`,
              path: `/v1/crm/deals/${deal.deal_id}`,
            }))}
            busy={busy} onDelete={remove} onAsk={ask}
          />
        )}

        {tab === 'contracts' && (
          <Rows
            empty="Aucun contrat enregistré."
            rows={contracts.map((contract) => ({
              id: contract.contract_id,
              title: contract.title,
              badge: contract.status,
              detail: [nameOf(contract.contact_id), money(contract.value, contract.currency)].filter(Boolean).join(' · '),
              note: contract.end_date
                ? `Fin le ${contract.end_date}${contract.days_to_expiry !== null ? ` (${contract.days_to_expiry} j)` : ''}`
                : '',
              prompt: `Résume le contrat « ${contract.title} ».`,
              path: `/v1/crm/contracts/${contract.contract_id}`,
            }))}
            busy={busy} onDelete={remove} onAsk={ask}
          />
        )}

        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
          <button
            type="button"
            className="primary-button"
            onClick={() => ask('Quels clients dois-je relancer, et quels devis attendent une réponse ?')}
          >Demander le point commercial</button>
        </footer>
      </section>
    </div>
  )
}

type BucketItem = { id: string; title: string; detail: string; prompt: string }

function Bucket({ title, empty, items, onAsk }: {
  title: string; empty: string; items: BucketItem[]; onAsk: (prompt: string) => void
}) {
  return (
    <div className="task-group">
      <span className="profile-section">{title}</span>
      {items.length === 0 && <p className="profile-status">{empty}</p>}
      {items.map((item) => (
        <div key={item.id} className="task-row">
          <div><strong>{item.title}</strong><small>{item.detail}</small></div>
          <button onClick={() => onAsk(item.prompt)}>Traiter</button>
        </div>
      ))}
    </div>
  )
}

type Row = {
  id: string; title: string; badge: string; detail: string; note: string; prompt: string; path: string
}

function Rows({ rows, empty, busy, onDelete, onAsk }: {
  rows: Row[]
  empty: string
  busy: string
  onDelete: (path: string, id: string) => void
  onAsk: (prompt: string) => void
}) {
  if (rows.length === 0) return <p className="profile-status">{empty}</p>
  return (
    <div className="task-group">
      {rows.map((row) => (
        <div key={row.id} className="task-row">
          <div>
            <strong>{row.title} <em className="row-badge">{row.badge}</em></strong>
            {row.detail && <small>{row.detail}</small>}
            {row.note && <small>{row.note}</small>}
          </div>
          <div className="row-actions">
            <button onClick={() => onAsk(row.prompt)}>Demander</button>
            <button
              className="row-delete"
              onClick={() => onDelete(row.path, row.id)}
              disabled={busy === row.id}
              aria-label={`Supprimer ${row.title}`}
            >{busy === row.id ? '…' : 'Supprimer'}</button>
          </div>
        </div>
      ))}
    </div>
  )
}
