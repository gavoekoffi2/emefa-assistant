import { useCallback, useEffect, useState } from 'react'
import { api } from './App'

export type MemoryItem = {
  memory_id: string; category: string; content: string; source: string; created_at: string
}

const categoryLabels: Record<string, string> = {
  fact: 'Fait',
  preference: 'Préférence',
  relationship: 'Relation',
  procedure: 'Procédure',
  other: 'Autre',
}

export function MemoryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [memories, setMemories] = useState<MemoryItem[] | null>(null)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const reload = useCallback(() => {
    api<MemoryItem[]>('/v1/memories')
      .then((items) => { setMemories(items); setError('') })
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Chargement impossible.'))
  }, [])

  useEffect(() => { if (open) { setMemories(null); reload() } }, [open, reload])

  if (!open) return null

  const forget = async (memoryId: string) => {
    setBusyId(memoryId)
    try {
      await api<void>(`/v1/memories/${memoryId}`, { method: 'DELETE' })
      reload()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Impossible d’oublier ce souvenir.')
    } finally { setBusyId('') }
  }

  return (
    <div className="profile-overlay" role="dialog" aria-modal="true" aria-labelledby="memory-title">
      <section className="profile-panel">
        <header className="profile-head">
          <div>
            <h2 id="memory-title">Mémoire durable</h2>
            <p>Ce qu’EMEFA retient pour vous. Dites-lui « retiens que… » pour ajouter, ou oubliez ici.</p>
          </div>
          <button className="profile-close" onClick={onClose} aria-label="Fermer la mémoire">✕</button>
        </header>
        {error && <div className="form-error" role="alert">{error}</div>}
        {memories === null && !error && <p className="profile-status">Chargement…</p>}
        {memories !== null && memories.length === 0 && (
          <p className="profile-status">Aucun souvenir enregistré. Cette mémoire vous appartient : EMEFA n’y écrit que ce que vous demandez.</p>
        )}
        {memories !== null && memories.map((memory) => (
          <div key={memory.memory_id} className="task-row memory-row">
            <div>
              <span className="memory-category">{categoryLabels[memory.category] || memory.category}</span>
              <strong>{memory.content}</strong>
              <small>Ajouté le {memory.created_at.slice(0, 10)}</small>
            </div>
            <button onClick={() => void forget(memory.memory_id)} disabled={busyId === memory.memory_id}>
              {busyId === memory.memory_id ? '…' : 'Oublier'}
            </button>
          </div>
        ))}
        <footer className="profile-actions">
          <button type="button" className="profile-later" onClick={onClose}>Fermer</button>
        </footer>
      </section>
    </div>
  )
}
