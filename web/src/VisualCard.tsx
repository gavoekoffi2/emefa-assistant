/**
 * Visual cards.
 *
 * The backend sends typed data, never markup: a model that can write HTML into
 * a page can write a script into it. Everything below turns validated payloads
 * into elements, so nothing EMEFA says can become something the browser runs.
 */
export type VisualCardData = {
  kind: 'image' | 'document' | 'file' | 'chart' | 'table' | 'map' | 'metrics' | 'video'
  title: string
  caption?: string
  payload: Record<string, unknown>
}

const asPoints = (payload: Record<string, unknown>) =>
  Array.isArray(payload.points)
    ? (payload.points as { label: string; value: number }[])
    : []

function Chart({ payload }: { payload: Record<string, unknown> }) {
  const points = asPoints(payload)
  const unit = typeof payload.unit === 'string' ? payload.unit : ''
  const line = payload.shape === 'line'
  if (points.length === 0) return null

  // The scale always includes zero, so a bar's length stays proportional to
  // its value. Starting an axis at the smallest value makes small differences
  // look enormous, which is the most common way a chart misleads.
  const values = points.map((point) => point.value)
  const top = Math.max(0, ...values)
  const bottom = Math.min(0, ...values)
  const span = top - bottom || 1
  const height = 128
  const width = Math.max(220, points.length * 44)
  const y = (value: number) => height - ((value - bottom) / span) * height

  return (
    <figure className="card-chart">
      <svg viewBox={`0 0 ${width} ${height + 26}`} role="img" aria-label={`Graphique, ${points.length} valeurs`}>
        <line x1="0" y1={y(0)} x2={width} y2={y(0)} className="chart-axis" />
        {line ? (
          <polyline
            className="chart-line"
            points={points
              .map((point, index) => `${(index + 0.5) * (width / points.length)},${y(point.value)}`)
              .join(' ')}
          />
        ) : (
          points.map((point, index) => {
            const slot = width / points.length
            const barWidth = slot * 0.56
            const topY = Math.min(y(point.value), y(0))
            return (
              <rect
                key={`${point.label}-${index}`}
                className="chart-bar"
                x={index * slot + (slot - barWidth) / 2}
                y={topY}
                width={barWidth}
                height={Math.max(1, Math.abs(y(point.value) - y(0)))}
              />
            )
          })
        )}
        {points.map((point, index) => (
          <text
            key={`label-${point.label}-${index}`}
            className="chart-label"
            x={(index + 0.5) * (width / points.length)}
            y={height + 18}
            textAnchor="middle"
          >
            {point.label.length > 8 ? `${point.label.slice(0, 7)}…` : point.label}
          </text>
        ))}
      </svg>
      <figcaption>
        {points.map((point) => `${point.label} : ${point.value.toLocaleString('fr-FR')}${unit ? ` ${unit}` : ''}`).join(' · ')}
      </figcaption>
    </figure>
  )
}

function Table({ payload }: { payload: Record<string, unknown> }) {
  const columns = Array.isArray(payload.columns) ? (payload.columns as string[]) : []
  const rows = Array.isArray(payload.rows) ? (payload.rows as string[][]) : []
  if (columns.length === 0) return null
  return (
    <div className="card-table-scroll">
      <table className="card-table">
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Metrics({ payload }: { payload: Record<string, unknown> }) {
  const metrics = Array.isArray(payload.metrics)
    ? (payload.metrics as { label: string; value: string; hint?: string }[])
    : []
  return (
    <div className="card-metrics">
      {metrics.map((metric) => (
        <div key={metric.label}>
          <strong>{metric.value}</strong>
          <span>{metric.label}</span>
          {metric.hint && <small>{metric.hint}</small>}
        </div>
      ))}
    </div>
  )
}

/**
 * A location, drawn as a graticule with a marker.
 *
 * Not a street map: no tile provider is connected, and the page's
 * content-security policy would refuse remote tiles anyway. Showing where a
 * place is, and saying that is all this is, beats a broken map frame.
 */
function LocationMap({ payload }: { payload: Record<string, unknown> }) {
  const latitude = Number(payload.latitude)
  const longitude = Number(payload.longitude)
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null
  const label = typeof payload.label === 'string' ? payload.label : ''
  const x = ((longitude + 180) / 360) * 100
  const y = ((90 - latitude) / 180) * 100
  return (
    <figure className="card-map">
      <svg viewBox="0 0 100 50" role="img" aria-label={`Position de ${label}`}>
        {[0, 25, 50].map((value) => <line key={`h${value}`} x1="0" y1={value} x2="100" y2={value} className="map-grid" />)}
        {[0, 25, 50, 75, 100].map((value) => <line key={`v${value}`} x1={value} y1="0" x2={value} y2="50" className="map-grid" />)}
        <line x1="0" y1="25" x2="100" y2="25" className="map-equator" />
        <circle cx={x} cy={y / 2} r="1.6" className="map-marker" />
      </svg>
      <figcaption>
        {label} — {latitude.toFixed(4)}°, {longitude.toFixed(4)}°
        <br />
        <small>Repère de position, pas une carte routière.</small>
      </figcaption>
    </figure>
  )
}

export function VisualCard({ card }: { card: VisualCardData }) {
  const url = typeof card.payload.url === 'string' ? card.payload.url : ''
  return (
    <article className={`visual-card visual-${card.kind}`}>
      <header>
        <h3>{card.title}</h3>
        {card.caption && <p>{card.caption}</p>}
      </header>
      {card.kind === 'image' && url && <img src={url} alt={card.title} loading="lazy" />}
      {card.kind === 'video' && url && <video src={url} controls preload="metadata" />}
      {(card.kind === 'document' || card.kind === 'file') && url && (
        <a className="card-download" href={url} target="_blank" rel="noreferrer">
          Ouvrir {card.kind === 'document' ? 'le document' : 'le fichier'}
        </a>
      )}
      {card.kind === 'chart' && <Chart payload={card.payload} />}
      {card.kind === 'table' && <Table payload={card.payload} />}
      {card.kind === 'metrics' && <Metrics payload={card.payload} />}
      {card.kind === 'map' && <LocationMap payload={card.payload} />}
    </article>
  )
}

export function VisualCards({ cards }: { cards: VisualCardData[] }) {
  if (cards.length === 0) return null
  return (
    <section className="visual-cards" aria-label="Éléments affichés par EMEFA">
      {cards.map((card, index) => <VisualCard key={`${card.kind}-${index}`} card={card} />)}
    </section>
  )
}
