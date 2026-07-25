import { useEffect, useState } from 'react'
import { api } from './App'

export type DeliverableRecord = {
  document_id: string
  title: string
  filename: string
  content_type: string
  size_bytes: number
  updated_at: string
  download_url: string
}

export type SourceFileRecord = {
  file_id: string
  filename: string
  content_type: string
  size_bytes: number
  extraction_status: string
  text_preview: string
  download_url: string
}

type DeliverablesPayload = {
  deliverables: DeliverableRecord[]
  sources: SourceFileRecord[]
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('fr-FR', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date)
}

const sourceStatus: Record<string, string> = {
  extracted: 'Texte prêt pour EMEFA',
  stored: 'Fichier disponible',
  image_stored_no_ocr: 'Image enregistrée',
  unsupported: 'Format conservé sans lecture automatique',
  extraction_failed: 'Fichier conservé — lecture automatique indisponible',
}

async function loadDeliverables(): Promise<DeliverablesPayload> {
  const [deliverables, sources] = await Promise.all([
    api<DeliverableRecord[]>('/v1/documents'),
    api<SourceFileRecord[]>('/v1/files'),
  ])
  return { deliverables, sources }
}

export function DeliverablesPanel({
  open,
  refreshToken,
  onClose,
  onCounts,
}: {
  open: boolean
  refreshToken: number
  onClose: () => void
  onCounts?: (deliverables: number, sources: number) => void
}) {
  const [data, setData] = useState<DeliverablesPayload | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setError('')
    loadDeliverables()
      .then((payload) => {
        if (cancelled) return
        setData(payload)
        onCounts?.(payload.deliverables.length, payload.sources.length)
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Impossible de charger les livrables.')
      })
    return () => { cancelled = true }
  }, [open, refreshToken, onCounts])

  if (!open) return null

  return (
    <div className="profile-overlay deliverables-overlay" role="dialog" aria-modal="true" aria-labelledby="deliverables-title">
      <section className="profile-panel deliverables-panel">
        <header className="profile-head deliverables-head">
          <div>
            <span className="deliverables-eyebrow">ESPACE DE RETRAIT</span>
            <h2 id="deliverables-title">Vos résultats et fichiers</h2>
            <p>Retrouvez ici ce qu’EMEFA a terminé et les fichiers que vous lui avez confiés.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer les livrables">✕</button>
        </header>

        {error && <div className="form-error" role="alert">{error}</div>}
        {!data && !error && <p className="profile-status">Chargement de vos fichiers…</p>}

        {data && (
          <div className="deliverables-content">
            <section className="deliverable-section" aria-labelledby="results-heading">
              <div className="deliverable-section-head">
                <div>
                  <span className="deliverable-section-icon" aria-hidden="true">✓</span>
                  <div><h3 id="results-heading">Résultats d’EMEFA</h3><p>Travaux terminés, prêts à être récupérés.</p></div>
                </div>
                <strong>{data.deliverables.length}</strong>
              </div>
              {data.deliverables.length === 0 ? (
                <div className="deliverables-empty">
                  <span aria-hidden="true">◇</span>
                  <div><strong>Aucun livrable pour le moment</strong><p>Demandez à EMEFA de créer ou traiter un document. Le résultat apparaîtra automatiquement ici.</p></div>
                </div>
              ) : (
                <div className="deliverable-list">
                  {data.deliverables.map((item) => (
                    <article className="deliverable-row" key={item.document_id}>
                      <div className="file-type-badge" aria-hidden="true">DOCX</div>
                      <div className="deliverable-meta">
                        <strong>{item.title || item.filename}</strong>
                        <span>{formatDate(item.updated_at)} · {formatBytes(item.size_bytes)}</span>
                      </div>
                      <a className="download-result" href={item.download_url} download>
                        <span aria-hidden="true">↓</span> Télécharger
                      </a>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="deliverable-section sources-section" aria-labelledby="sources-heading">
              <div className="deliverable-section-head">
                <div>
                  <span className="deliverable-section-icon source" aria-hidden="true">↑</span>
                  <div><h3 id="sources-heading">Fichiers envoyés</h3><p>Documents sources disponibles pour les prochains travaux.</p></div>
                </div>
                <strong>{data.sources.length}</strong>
              </div>
              {data.sources.length === 0 ? (
                <p className="source-empty">Aucun fichier source envoyé.</p>
              ) : (
                <div className="source-file-list">
                  {data.sources.map((file) => (
                    <a className="source-file-row" key={file.file_id} href={file.download_url} download>
                      <span className="source-file-icon" aria-hidden="true">▤</span>
                      <span><strong>{file.filename}</strong><small>{sourceStatus[file.extraction_status] || 'Fichier disponible'} · {formatBytes(file.size_bytes)}</small></span>
                      <b aria-hidden="true">↓</b>
                    </a>
                  ))}
                </div>
              )}
            </section>
          </div>
        )}

        <footer className="profile-actions deliverables-actions">
          <span>Les résultats restent disponibles après la conversation.</span>
          <button type="button" className="primary-button" onClick={onClose}>Retour à EMEFA</button>
        </footer>
      </section>
    </div>
  )
}
