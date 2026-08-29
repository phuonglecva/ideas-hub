const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function load(path) {
  try {
    const r = await fetch(`${API}${path}`, { cache: 'no-store' })
    return r.ok ? await r.json() : []
  } catch { return [] }
}

function Score({ value }) {
  return <span className="score">{Number(value || 0).toFixed(0)}</span>
}

export default async function Home() {
  const [opportunities, signals, events] = await Promise.all([
    load('/v1/opportunities?limit=12'), load('/v1/signals?limit=8'), load('/v1/events?limit=8')
  ])
  return <main>
    <header><p className="eyebrow">VIETNAM OPPORTUNITY INTELLIGENCE</p><h1>Ideas Hub</h1><p>News is raw material. Evidence-backed opportunities are the product.</p></header>
    <section><div className="sectionTitle"><h2>Opportunity Radar</h2><span>{opportunities.length} candidates</span></div>
      <div className="grid">{opportunities.length ? opportunities.map(o => <article className="card" key={o.id}>
        <div className="row"><Score value={o.score}/><span className="confidence">{Math.round(o.confidence*100)}% confidence</span></div>
        <h3>{o.title}</h3><p className="muted">{o.customer}</p><p>{o.problem}</p><div className="solution">{o.solution}</div>
      </article>) : <div className="empty">No opportunities yet. Add a source and run the pipeline from the API docs.</div>}</div>
    </section>
    <div className="two"><section><div className="sectionTitle"><h2>Signals</h2></div>{signals.map(s => <div className="list" key={s.id}><Score value={s.score}/><div><b>Event {s.event_id.slice(0,8)}</b><small>{s.features?.article_count || 0} articles · {s.features?.source_count || 0} sources</small></div></div>)}</section>
    <section><div className="sectionTitle"><h2>Recent events</h2></div>{events.map(e => <div className="event" key={e.id}><b>{e.title}</b><small>{e.article_count} articles · {e.source_count} sources</small></div>)}</section></div>
  </main>
}
