const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8888";
const BROWSER_API =
  process.env.NEXT_PUBLIC_BROWSER_API_URL || "http://localhost:8888";

async function load(path) {
  try {
    const response = await fetch(`${API}${path}`, { cache: "no-store" });
    return response.ok ? await response.json() : [];
  } catch {
    return [];
  }
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true">
      <path d="M5 15 15 5M7 5h8v8" />
    </svg>
  );
}

function PulseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 12h4l2.2-6 4.1 12 2.2-6H21" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 3h8l4 4v14H6zM14 3v5h5M9 12h6M9 16h6" />
    </svg>
  );
}

function formatDate(value) {
  if (!value) return "Chưa rõ thời gian";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function scoreTone(value) {
  if (value >= 70) return "high";
  if (value >= 45) return "medium";
  return "low";
}

function Score({ value, compact = false }) {
  const score = Math.round(Number(value || 0));
  return (
    <span
      className={`score score-${scoreTone(score)} ${compact ? "scoreCompact" : ""}`}
    >
      {score}
    </span>
  );
}

function Stat({ label, value, note, tone }) {
  return (
    <div className={`stat ${tone || ""}`}>
      <span className="statLabel">{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function Tags({ items = [], limit = 4 }) {
  const visible = items.filter(Boolean).slice(0, limit);
  if (!visible.length) return null;
  return (
    <div className="tags">
      {visible.map((item, index) => (
        <span className="tag" key={`${item}-${index}`}>
          {item}
        </span>
      ))}
      {items.length > limit && (
        <span className="tag more">+{items.length - limit}</span>
      )}
    </div>
  );
}

function ArticleCard({ article, source }) {
  const data = article.extracted || {};
  const metrics = data.metrics || [];
  const insight =
    (data.changes || [])[0] ||
    (data.problems || [])[0] ||
    (data.claims || [])[0];
  const topics = [...(data.industries || []), ...(data.entities || [])];

  return (
    <article className="articleCard">
      <div className="articleMeta">
        <span className="sourceMark">{(source?.name || "N").slice(0, 1)}</span>
        <span>{source?.name || "Nguồn chưa xác định"}</span>
        <i />
        <time>{formatDate(article.published_at)}</time>
      </div>
      <a
        className="articleTitle"
        href={article.canonical_url}
        target="_blank"
        rel="noreferrer"
      >
        <h3>{article.title}</h3>
        <ArrowIcon />
      </a>
      {insight && (
        <p className="insight">
          <span>Điểm đáng chú ý</span>
          {insight}
        </p>
      )}
      {metrics.length > 0 && (
        <div className="metricStrip">
          {metrics.slice(0, 2).map((metric, index) => (
            <span key={`${metric}-${index}`}>{metric}</span>
          ))}
        </div>
      )}
      <Tags items={topics} />
      <footer className="articleFooter">
        <span>
          {(data.claims || []).length} luận điểm ·{" "}
          {(data.problems || []).length} vấn đề
        </span>
        <a href={article.canonical_url} target="_blank" rel="noreferrer">
          Đọc bài gốc <ArrowIcon />
        </a>
      </footer>
    </article>
  );
}

function OpportunityCard({ opportunity, articleById }) {
  const evidence = (opportunity.thesis?.evidence_ids || [])
    .map((id) => articleById.get(id))
    .filter(Boolean)
    .slice(0, 3);
  return (
    <article className="opportunityCard">
      <div className="opportunityTop">
        <Score value={opportunity.score} />
        <span className="statusPill">{opportunity.status || "candidate"}</span>
        <span className="confidence">
          Tin cậy {Math.round((opportunity.confidence || 0) * 100)}%
        </span>
      </div>
      <h3>{opportunity.title}</h3>
      <p className="customer">Dành cho {opportunity.customer}</p>
      <p className="problem">{opportunity.problem}</p>
      <div className="solutionBlock">
        <span>Hướng giải pháp</span>
        {opportunity.solution}
      </div>
      {evidence.length > 0 && (
        <div className="evidence">
          <span>Nguồn chứng minh</span>
          {evidence.map((article) => (
            <a
              href={article.canonical_url}
              target="_blank"
              rel="noreferrer"
              key={article.id}
            >
              {article.title}
              <ArrowIcon />
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

function SignalRow({ signal, event }) {
  const score = Math.round(signal.score || 0);
  return (
    <div className="signalRow">
      <Score value={score} compact />
      <div className="signalBody">
        <strong>
          {event?.title || `Sự kiện ${signal.event_id.slice(0, 8)}`}
        </strong>
        <div className="signalMeta">
          <span>{signal.features?.article_count || 0} bài viết</span>
          <span>{signal.features?.source_count || 0} nguồn</span>
        </div>
        <div className="scoreTrack">
          <i style={{ width: `${Math.min(score, 100)}%` }} />
        </div>
      </div>
    </div>
  );
}

export default async function Home() {
  const [opportunities, signals, events, articles, sources] = await Promise.all(
    [
      load("/v1/opportunities?limit=12"),
      load("/v1/signals?limit=10"),
      load("/v1/events?limit=10"),
      load("/v1/articles?limit=100"),
      load("/v1/sources"),
    ],
  );
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const eventById = new Map(events.map((event) => [event.id, event]));
  const articleById = new Map(articles.map((article) => [article.id, article]));
  const enabledSources = sources.filter((source) => source.enabled);
  const extractedCount = articles.filter((article) =>
    Object.values(article.extracted || {}).some(
      (value) => Array.isArray(value) && value.length,
    ),
  ).length;
  const averageSignal = signals.length
    ? Math.round(
        signals.reduce(
          (total, signal) => total + Number(signal.score || 0),
          0,
        ) / signals.length,
      )
    : 0;
  const latestUpdate = events[0]?.last_seen_at || articles[0]?.published_at;

  return (
    <main>
      <nav className="topbar">
        <a className="brand" href="#top" aria-label="Ideas Hub">
          <span className="brandGlyph">
            <i />
            <i />
            <i />
          </span>
          <span>
            Ideas<span>Hub</span>
          </span>
        </a>
        <div className="navLinks">
          <a href="#radar">Radar</a>
          <a href="#news">Nguồn tin</a>
          <a href="#signals">Tín hiệu</a>
          <a href="/cms">CMS</a>
        </div>
        <a
          className="systemStatus"
          href={`${BROWSER_API}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          <i /> Pipeline đang chạy <ArrowIcon />
        </a>
      </nav>

      <header className="hero" id="top">
        <div className="heroCopy">
          <p className="eyebrow">
            <span>LIVE INTELLIGENCE</span> VIETNAM MARKET RADAR
          </p>
          <h1>
            Từ dòng tin đến
            <br />
            <em>cơ hội có chứng cứ.</em>
          </h1>
          <p>
            Hệ thống theo dõi thay đổi thị trường, gom nhóm sự kiện và biến dữ
            liệu nguồn thành những luận điểm có thể kiểm chứng.
          </p>
        </div>
        <div className="heroTelemetry">
          <div className="telemetryHead">
            <PulseIcon />
            <span>Pipeline telemetry</span>
            <b>LIVE</b>
          </div>
          <div className="telemetryFlow">
            <span className="done">Nguồn</span>
            <span className="done">Bài viết</span>
            <span className="active">Tín hiệu</span>
            <span>Cơ hội</span>
          </div>
          <div className="telemetryFoot">
            <span>Cập nhật gần nhất</span>
            <time>{formatDate(latestUpdate)}</time>
          </div>
        </div>
      </header>

      <section className="stats" aria-label="Tổng quan dữ liệu">
        <Stat
          label="Nguồn đang theo dõi"
          value={enabledSources.length}
          note={`${sources.length} nguồn đã đăng ký`}
          tone="lime"
        />
        <Stat
          label="Bài đã thu thập"
          value={articles.length}
          note={`${extractedCount} bài có insight`}
        />
        <Stat
          label="Cụm sự kiện"
          value={events.length}
          note="Đang được theo dõi"
        />
        <Stat
          label="Sức mạnh tín hiệu"
          value={averageSignal}
          note="Điểm trung bình / 100"
          tone="violet"
        />
      </section>

      <div className="dashboardGrid">
        <section className="panel radarPanel" id="radar">
          <div className="sectionHeading">
            <div>
              <p>DECISION LAYER</p>
              <h2>Opportunity radar</h2>
            </div>
            <span>{opportunities.length} ứng viên</span>
          </div>
          {opportunities.length > 0 ? (
            <div className="opportunityGrid">
              {opportunities.map((opportunity) => (
                <OpportunityCard
                  key={opportunity.id}
                  opportunity={opportunity}
                  articleById={articleById}
                />
              ))}
            </div>
          ) : (
            <div className="radarEmpty">
              <div className="radarVisual">
                <i />
                <i />
                <i />
                <span>
                  <PulseIcon />
                </span>
              </div>
              <div>
                <span className="processing">ĐANG TÍCH LŨY BẰNG CHỨNG</span>
                <h3>Chưa đủ tín hiệu để tạo cơ hội đáng tin cậy.</h3>
                <p>
                  Pipeline đã thu thập {articles.length} bài và hình thành{" "}
                  {events.length} cụm sự kiện. Cơ hội sẽ xuất hiện khi điểm tín
                  hiệu vượt ngưỡng chất lượng.
                </p>
              </div>
            </div>
          )}
        </section>

        <aside className="panel sourcePanel">
          <div className="sectionHeading compactHeading">
            <div>
              <p>SOURCE HEALTH</p>
              <h2>Độ phủ nguồn</h2>
            </div>
          </div>
          <div className="sourceList">
            {sources.map((source) => {
              const count = articles.filter(
                (article) => article.source_id === source.id,
              ).length;
              return (
                <div className="sourceRow" key={source.id}>
                  <span className="sourceLogo">{source.name.slice(0, 1)}</span>
                  <div>
                    <strong>{source.name}</strong>
                    <small>{source.domain}</small>
                  </div>
                  <div className="sourceCount">
                    <b>{count}</b>
                    <small>bài</small>
                  </div>
                  <span className={source.enabled ? "sourceLive" : "sourceOff"}>
                    {source.enabled ? "LIVE" : "OFF"}
                  </span>
                </div>
              );
            })}
          </div>
        <a className="panelLink" href="/cms">
          Quản lý nguồn trong CMS <ArrowIcon />
        </a>
        </aside>

        <section className="panel newsPanel" id="news">
          <div className="sectionHeading">
            <div>
              <p>EVIDENCE STREAM</p>
              <h2>Dòng tin đã trích xuất</h2>
            </div>
            <span>{articles.length} bài gần nhất</span>
          </div>
          {articles.length > 0 ? (
            <div className="articleGrid">
              {articles.slice(0, 8).map((article) => (
                <ArticleCard
                  article={article}
                  source={sourceById.get(article.source_id)}
                  key={article.id}
                />
              ))}
            </div>
          ) : (
            <div className="simpleEmpty">
              <DocumentIcon />
              <p>Đang chờ bài viết đầu tiên từ crawler.</p>
            </div>
          )}
        </section>

        <aside className="panel signalsPanel" id="signals">
          <div className="sectionHeading compactHeading">
            <div>
              <p>SIGNAL ENGINE</p>
              <h2>Tín hiệu nổi bật</h2>
            </div>
            <span>{signals.length}</span>
          </div>
          <div className="signalList">
            {signals.length > 0 ? (
              signals
                .slice(0, 7)
                .map((signal) => (
                  <SignalRow
                    signal={signal}
                    event={eventById.get(signal.event_id)}
                    key={signal.id}
                  />
                ))
            ) : (
              <p className="asideEmpty">Chưa có tín hiệu.</p>
            )}
          </div>
          <div className="legend">
            <span>
              <i className="legendHigh" />
              Mạnh
            </span>
            <span>
              <i className="legendMedium" />
              Theo dõi
            </span>
            <span>
              <i className="legendLow" />
              Yếu
            </span>
          </div>
        </aside>

        <section className="panel eventPanel">
          <div className="sectionHeading">
            <div>
              <p>EVENT CLUSTERS</p>
              <h2>Sự kiện đang hình thành</h2>
            </div>
            <span>{events.length} cụm</span>
          </div>
          <div className="eventTable">
            {events.slice(0, 8).map((event, index) => {
              const signal = signals.find((item) => item.event_id === event.id);
              return (
                <div className="eventRow" key={event.id}>
                  <span className="eventIndex">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="eventTitle">
                    <strong>{event.title}</strong>
                    <small>Cập nhật {formatDate(event.last_seen_at)}</small>
                  </div>
                  <span>{event.article_count} bài</span>
                  <span>{event.source_count} nguồn</span>
                  {signal ? (
                    <Score value={signal.score} compact />
                  ) : (
                    <span className="pendingScore">—</span>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </div>

      <footer className="pageFooter">
        <div className="brand footerBrand">
          <span className="brandGlyph">
            <i />
            <i />
            <i />
          </span>
          <span>
            Ideas<span>Hub</span>
          </span>
        </div>
        <p>Observed facts → derived signals → testable opportunities.</p>
        <a href={`${BROWSER_API}/docs`} target="_blank" rel="noreferrer">
          API documentation <ArrowIcon />
        </a>
      </footer>
    </main>
  );
}
