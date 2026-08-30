"use client";

import { useMemo, useState } from "react";

const insightFields = [
  ["changes", "Thay đổi"],
  ["problems", "Vấn đề"],
  ["claims", "Luận điểm"],
  ["metrics", "Số liệu"],
  ["entities", "Thực thể"],
  ["industries", "Ngành"],
  ["affected_groups", "Nhóm ảnh hưởng"],
  ["regulations", "Quy định"],
];
const statuses = [
  "candidate",
  "reviewing",
  "validated",
  "rejected",
  "archived",
];

function Icon({ name }) {
  const paths = {
    back: <path d="m15 18-6-6 6-6M9 12h10" />,
    plus: <path d="M12 5v14M5 12h14" />,
    play: <path d="m8 5 11 7-11 7z" />,
    edit: <path d="m14 5 5 5M4 20l3.5-.7L19 7.8 16.2 5 4.7 16.5z" />,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    external: <path d="M5 15 15 5M7 5h8v8" />,
    source: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
      </>
    ),
    article: (
      <>
        <path d="M6 3h9l4 4v14H6zM15 3v5h5" />
        <path d="M9 12h7M9 16h7" />
      </>
    ),
    cluster: (
      <>
        <circle cx="7" cy="7" r="3" />
        <circle cx="17" cy="7" r="3" />
        <circle cx="12" cy="17" r="3" />
        <path d="m9 9 2 5M15 9l-2 5" />
      </>
    ),
    radar: (
      <>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="4" />
        <path d="m12 12 6-6" />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function parseLines(value) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function date(value) {
  if (!value) return "Chưa rõ";
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(new Date(value));
}

function Stat({ icon, label, value, note }) {
  return (
    <div className="cmsStat">
      <span>
        <Icon name={icon} />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <p>{note}</p>
      </div>
    </div>
  );
}

function Empty({ title, copy }) {
  return (
    <div className="cmsEmpty">
      <span>∅</span>
      <strong>{title}</strong>
      <p>{copy}</p>
    </div>
  );
}

export default function CmsConsole({
  apiBase,
  initialSources,
  initialArticles,
  initialEvents,
  initialOpportunities,
  initialCandidates,
  initialCrawlRuns,
}) {
  const [tab, setTab] = useState("sources");
  const [sources, setSources] = useState(initialSources);
  const [articles, setArticles] = useState(initialArticles);
  const [events, setEvents] = useState(initialEvents);
  const [opportunities, setOpportunities] = useState(initialOpportunities);
  const [candidates, setCandidates] = useState(initialCandidates);
  const [crawlRuns, setCrawlRuns] = useState(initialCrawlRuns);
  const [query, setQuery] = useState("");
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState(null);

  const articleCounts = useMemo(
    () =>
      articles.reduce((result, article) => {
        result[article.source_id] = (result[article.source_id] || 0) + 1;
        return result;
      }, {}),
    [articles],
  );
  const sourceById = useMemo(
    () => new Map(sources.map((source) => [source.id, source])),
    [sources],
  );
  const latestRunBySource = useMemo(() => {
    const result = new Map();
    crawlRuns.forEach((run) => {
      if (run.source_id && !result.has(run.source_id)) {
        result.set(run.source_id, run);
      }
    });
    return result;
  }, [crawlRuns]);
  const filter = (value) =>
    !query || value.toLowerCase().includes(query.toLowerCase());

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).join(", ")
        : data.detail;
      throw new Error(detail || `Yêu cầu thất bại (${response.status})`);
    }
    return data;
  }

  function notify(message, tone = "success") {
    setToast({ message, tone });
    window.setTimeout(() => setToast(null), 3500);
  }

  async function reload(kind) {
    const routes = {
      sources: ["/v1/sources", setSources],
      articles: ["/v1/articles?limit=200", setArticles],
      events: ["/v1/events?limit=200", setEvents],
      opportunities: ["/v1/opportunities?limit=200", setOpportunities],
      discovery: ["/v1/source-candidates?limit=200", setCandidates],
      crawlRuns: ["/v1/crawl-runs?limit=200", setCrawlRuns],
    };
    const [path, setter] = routes[kind];
    setter(await request(path));
  }

  async function saveSource(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(form);
    const payload = {
      name: values.name,
      domain: values.domain,
      source_type: values.source_type,
      feed_url: values.feed_url || null,
      trust_score: Number(values.trust_score),
    };
    const current = editor?.item;
    if (current) payload.enabled = values.enabled === "on";
    setBusy("source-save");
    try {
      if (current) {
        await request(`/v1/sources/${current.id}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        await reload("sources");
      } else {
        const domain = values.domain.replace(/^https?:\/\//, "").split("/")[0];
        const candidate = await request("/v1/source-candidates", {
          method: "POST",
          body: JSON.stringify({
            name: values.name,
            homepage_url: `https://${domain}`,
            feed_url: values.feed_url || null,
          }),
        });
        await request(`/v1/source-candidates/${candidate.id}/validate`, {
          method: "POST",
        });
        await reload("discovery");
        setTab("discovery");
      }
      setEditor(null);
      notify(
        current
          ? "Đã cập nhật nguồn."
          : "Nguồn đã vào hàng chờ kiểm định trước khi kích hoạt.",
      );
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function toggleSource(source) {
    setBusy(source.id);
    try {
      const updated = await request(`/v1/sources/${source.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !source.enabled }),
      });
      setSources((items) =>
        items.map((item) => (item.id === source.id ? updated : item)),
      );
      notify(
        updated.enabled ? "Nguồn đã được kích hoạt." : "Nguồn đã tạm dừng.",
      );
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function crawl(source) {
    setBusy(`crawl-${source.id}`);
    try {
      await request(`/v1/pipeline/sources/${source.id}/enqueue?limit=20`, {
        method: "POST",
      });
      notify(`Đã đưa ${source.name} vào hàng đợi crawl.`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function crawlAll() {
    setBusy("crawl-all");
    try {
      await request("/v1/pipeline/enqueue-enabled?limit=20", {
        method: "POST",
      });
      notify("Đã đưa toàn bộ nguồn đang bật vào hàng đợi.");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function runDiscovery() {
    setBusy("discovery-run");
    try {
      await request("/v1/source-discovery/enqueue", { method: "POST" });
      notify("Đã đưa tác vụ khám phá nguồn vào hàng đợi.");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function candidateAction(candidate, action) {
    setBusy(`${action}-${candidate.id}`);
    try {
      await request(`/v1/source-candidates/${candidate.id}/${action}`, {
        method: "POST",
      });
      await Promise.all([
        reload("discovery"),
        reload("sources"),
        reload("crawlRuns"),
      ]);
      notify(
        action === "approve"
          ? "Đã duyệt nguồn và đưa 3 bài bootstrap vào hàng đợi."
          : action === "reject"
            ? "Đã từ chối nguồn."
            : "Đã đưa nguồn vào hàng chờ kiểm định lại.",
      );
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function saveArticle(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const extracted = {};
    insightFields.forEach(([field]) => {
      extracted[field] = parseLines(form.get(field) || "");
    });
    setBusy("article-save");
    try {
      const updated = await request(`/v1/articles/${editor.item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: form.get("title"),
          canonical_url: form.get("canonical_url"),
          author: form.get("author") || null,
          extracted,
        }),
      });
      setArticles((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      setEditor(null);
      notify("Đã cập nhật bài viết và insight.");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function saveEvent(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("event-save");
    try {
      const updated = await request(`/v1/events/${editor.item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: form.get("title"),
          summary: form.get("summary") || null,
        }),
      });
      setEvents((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      setEditor(null);
      notify("Đã cập nhật cụm sự kiện.");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function updateOpportunity(opportunity, payload) {
    setBusy(opportunity.id);
    try {
      const updated = await request(`/v1/opportunities/${opportunity.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      setOpportunities((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      notify("Đã cập nhật opportunity.");
      return updated;
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  }

  async function saveOpportunity(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const updated = await updateOpportunity(editor.item, {
      title: form.get("title"),
      customer: form.get("customer"),
      problem: form.get("problem"),
      solution: form.get("solution"),
      status: form.get("status"),
    });
    if (updated) setEditor(null);
  }

  const filteredSources = sources.filter((source) =>
    filter(`${source.name} ${source.domain}`),
  );
  const filteredArticles = articles.filter((article) =>
    filter(`${article.title} ${sourceById.get(article.source_id)?.name || ""}`),
  );
  const filteredCandidates = candidates.filter((candidate) =>
    filter(
      `${candidate.name || ""} ${candidate.domain} ${candidate.feed_url || ""} ${candidate.status}`,
    ),
  );
  const filteredEvents = events.filter((event) =>
    filter(`${event.title} ${event.summary || ""}`),
  );
  const filteredOpportunities = opportunities.filter((item) =>
    filter(`${item.title} ${item.customer} ${item.status}`),
  );

  return (
    <main className="cmsShell">
      <header className="cmsTopbar">
        <a href="/" className="cmsBrand">
          <span className="brandGlyph">
            <i />
            <i />
            <i />
          </span>
          <span>
            Ideas<span>Hub</span>
          </span>
        </a>
        <span className="cmsMode">CONTROL ROOM</span>
        <a href="/" className="ghostButton">
          <Icon name="back" /> Dashboard
        </a>
      </header>

      <section className="cmsHero">
        <div>
          <p>DATA OPERATIONS</p>
          <h1>
            Quản trị luồng
            <br />
            <em>market intelligence.</em>
          </h1>
        </div>
        <div className="cmsHeroCopy">
          <span className="liveDot">SYSTEM ONLINE</span>
          <p>
            Kiểm soát nguồn thu thập, duyệt dữ liệu máy trích xuất và đưa cơ hội
            qua từng vòng đánh giá.
          </p>
        </div>
      </section>

      <section className="cmsStats">
        <Stat
          icon="source"
          label="Nguồn hoạt động"
          value={sources.filter((item) => item.enabled).length}
          note={`${sources.length} nguồn tổng cộng`}
        />
        <Stat
          icon="article"
          label="Bài trong kho"
          value={articles.length}
          note="Tối đa 200 bài gần nhất"
        />
        <Stat
          icon="cluster"
          label="Cụm sự kiện"
          value={events.length}
          note="Có thể biên tập metadata"
        />
        <Stat
          icon="radar"
          label="Opportunity"
          value={opportunities.length}
          note={`${opportunities.filter((item) => item.status === "validated").length} đã xác thực`}
        />
      </section>

      <section className="cmsWorkspace">
        <aside className="cmsNav">
          <p>WORKSPACE</p>
          {[
            ["sources", "source", "Nguồn dữ liệu", sources.length],
            [
              "discovery",
              "radar",
              "Khám phá nguồn",
              candidates.filter((item) =>
                ["discovered", "pending", "failed"].includes(item.status),
              ).length,
            ],
            ["articles", "article", "Bài & insight", articles.length],
            ["events", "cluster", "Cụm sự kiện", events.length],
            ["opportunities", "radar", "Opportunity", opportunities.length],
          ].map(([id, icon, label, count]) => (
            <button
              className={tab === id ? "active" : ""}
              onClick={() => {
                setTab(id);
                setQuery("");
              }}
              key={id}
            >
              <Icon name={icon} />
              <span>{label}</span>
              <b>{count}</b>
            </button>
          ))}
          <div className="cmsNavNote">
            <span>OPERATOR NOTE</span>
            <p>Tắt nguồn thay vì xoá để giữ nguyên chuỗi bằng chứng.</p>
          </div>
        </aside>

        <div className="cmsContent">
          <div className="cmsToolbar">
            <div>
              <p>
                {tab === "sources"
                  ? "INGESTION"
                  : tab === "discovery"
                    ? "SOURCE INTELLIGENCE"
                  : tab === "articles"
                    ? "CONTENT QA"
                    : tab === "events"
                      ? "CLUSTER CURATION"
                      : "DECISION WORKFLOW"}
              </p>
              <h2>
                {tab === "sources"
                  ? "Nguồn dữ liệu"
                  : tab === "discovery"
                    ? "Khám phá & kiểm định nguồn"
                  : tab === "articles"
                    ? "Bài viết & insight"
                    : tab === "events"
                      ? "Cụm sự kiện"
                      : "Opportunity pipeline"}
              </h2>
            </div>
            <label className="cmsSearch">
              <span>⌕</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm kiếm..."
              />
            </label>
            {tab === "sources" && (
              <>
                <button
                  className="ghostButton"
                  onClick={crawlAll}
                  disabled={busy === "crawl-all"}
                >
                  <Icon name="play" />{" "}
                  {busy === "crawl-all" ? "Đang gửi..." : "Crawl tất cả"}
                </button>
                <button
                  className="primaryButton"
                  onClick={() => setEditor({ type: "source" })}
                >
                  <Icon name="plus" /> Thêm nguồn
                </button>
              </>
            )}
            {tab === "discovery" && (
              <button
                className="primaryButton"
                onClick={runDiscovery}
                disabled={busy === "discovery-run"}
              >
                <Icon name="radar" />
                {busy === "discovery-run" ? "Đang gửi..." : "Quét nguồn mới"}
              </button>
            )}
          </div>

          {tab === "sources" && (
            <div className="sourceAdminList">
              <div className="adminTableHead">
                <span>Nguồn</span>
                <span>Loại</span>
                <span>Độ tin cậy</span>
                <span>Dữ liệu</span>
                <span>Trạng thái</span>
                <span />
              </div>
              {filteredSources.map((source) => {
                const run = latestRunBySource.get(source.id);
                return (
                <div className="sourceAdminRow" key={source.id}>
                  <div className="adminIdentity">
                    <span>{source.name.slice(0, 2).toUpperCase()}</span>
                    <div>
                      <strong>{source.name}</strong>
                      <a
                        href={source.feed_url || `https://${source.domain}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {source.domain} <Icon name="external" />
                      </a>
                    </div>
                  </div>
                  <span className="typePill">{source.source_type}</span>
                  <div className="trustMeter">
                    <span>
                      <i style={{ width: `${source.trust_score * 100}%` }} />
                    </span>
                    <b>{Math.round(source.trust_score * 100)}%</b>
                  </div>
                  <div className="sourceVolume">
                    <strong>{articleCounts[source.id] || 0}</strong>
                    <small>bài gần nhất</small>
                    {run && (
                      <small className={`runState ${run.status}`}>
                        {run.status} · {run.created || 0} mới
                        {run.duration_ms ? ` · ${(run.duration_ms / 1000).toFixed(1)}s` : ""}
                      </small>
                    )}
                  </div>
                  <button
                    className={`toggle ${source.enabled ? "on" : ""}`}
                    aria-label="Bật hoặc tắt nguồn"
                    onClick={() => toggleSource(source)}
                    disabled={busy === source.id}
                  >
                    <i />
                  </button>
                  <div className="rowActions">
                    <button
                      title="Crawl nguồn"
                      onClick={() => crawl(source)}
                      disabled={
                        !source.enabled || busy === `crawl-${source.id}`
                      }
                    >
                      <Icon name="play" />
                    </button>
                    <button
                      title="Chỉnh sửa"
                      onClick={() =>
                        setEditor({ type: "source", item: source })
                      }
                    >
                      <Icon name="edit" />
                    </button>
                  </div>
                </div>
              );})}
              {!filteredSources.length && (
                <Empty
                  title="Không tìm thấy nguồn"
                  copy="Thử từ khoá khác hoặc thêm một nguồn RSS mới."
                />
              )}
            </div>
          )}

          {tab === "discovery" && (
            <div className="candidateList">
              {filteredCandidates.map((candidate) => (
                <article className="candidateCard" key={candidate.id}>
                  <header>
                    <div className="candidateIdentity">
                      <span className={`candidateScore ${candidate.score >= 85 ? "high" : ""}`}>
                        {candidate.score}
                      </span>
                      <div>
                        <h3>{candidate.name || candidate.domain}</h3>
                        <a href={candidate.feed_url || candidate.homepage_url} target="_blank" rel="noreferrer">
                          {candidate.feed_url || candidate.homepage_url} <Icon name="external" />
                        </a>
                      </div>
                    </div>
                    <span className={`candidateStatus ${candidate.status}`}>
                      {candidate.status.replaceAll("_", " ")}
                    </span>
                  </header>

                  <div className="candidateMetrics">
                    <span><b>{candidate.entry_count}</b> entries</span>
                    <span><b>{Math.round(candidate.extraction_rate * 100)}%</b> extract</span>
                    <span><b>{candidate.source_count}</b> nguồn dẫn</span>
                    <span><b>{candidate.latest_entry_at ? date(candidate.latest_entry_at) : "—"}</b> bài mới nhất</span>
                  </div>

                  <div className="scoreBreakdown">
                    {Object.entries(candidate.score_breakdown || {}).map(([key, value]) => (
                      <div key={key}>
                        <span>{key.replaceAll("_", " ")}</span>
                        <i><b style={{ width: `${Math.min(100, value * 4)}%` }} /></i>
                        <strong>{value}</strong>
                      </div>
                    ))}
                  </div>

                  <div className="candidateEvidence">
                    <div>
                      <small>BÀI MẪU</small>
                      {(candidate.sample_headlines || []).slice(0, 3).map((headline) => (
                        <a key={headline.url || headline.title} href={headline.url} target="_blank" rel="noreferrer">
                          {headline.title} <Icon name="external" />
                        </a>
                      ))}
                      {!candidate.sample_headlines?.length && <p>Chưa có bài mẫu hợp lệ.</p>}
                    </div>
                    <div>
                      <small>BẰNG CHỨNG DẪN NGUỒN</small>
                      {(candidate.evidence || []).slice(0, 3).map((evidence) => (
                        <a key={evidence.article_id} href={evidence.article_url} target="_blank" rel="noreferrer">
                          {evidence.source_name}: {evidence.article_title} <Icon name="external" />
                        </a>
                      ))}
                      {!candidate.evidence?.length && <p>Chưa đủ bằng chứng độc lập.</p>}
                    </div>
                  </div>

                  {candidate.failure_reason && <p className="candidateError">{candidate.failure_reason}</p>}
                  <footer>
                    <small>Kiểm tra {date(candidate.last_checked_at || candidate.created_at)}</small>
                    {candidate.status !== "rejected" && (
                      <button className="ghostButton" onClick={() => candidateAction(candidate, "reject")} disabled={Boolean(busy)}>
                        Từ chối
                      </button>
                    )}
                    <button className="ghostButton" onClick={() => candidateAction(candidate, "validate")} disabled={Boolean(busy)}>
                      Rescan
                    </button>
                    {!candidate.source_id && (
                      <button className="primaryButton" onClick={() => candidateAction(candidate, "approve")} disabled={Boolean(busy)}>
                        Duyệt nguồn
                      </button>
                    )}
                  </footer>
                </article>
              ))}
              {!filteredCandidates.length && (
                <Empty title="Chưa có nguồn ứng viên" copy="Chạy quét để phân tích liên kết ngoài trong 200 bài gần nhất." />
              )}
            </div>
          )}

          {tab === "articles" && (
            <div className="contentReviewList">
              {filteredArticles.map((article) => {
                const insightCount = Object.values(
                  article.extracted || {},
                ).reduce(
                  (sum, items) =>
                    sum + (Array.isArray(items) ? items.length : 0),
                  0,
                );
                return (
                  <article className="reviewRow" key={article.id}>
                    <div className="reviewSource">
                      <span>
                        {(sourceById.get(article.source_id)?.name || "N").slice(
                          0,
                          1,
                        )}
                      </span>
                      <small>
                        {sourceById.get(article.source_id)?.name ||
                          "Không rõ nguồn"}
                      </small>
                    </div>
                    <div className="reviewMain">
                      <a
                        href={article.canonical_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {article.title} <Icon name="external" />
                      </a>
                      <p>
                        {(article.extracted?.changes ||
                          article.extracted?.claims ||
                          [])[0] || "Chưa có insight nổi bật."}
                      </p>
                      <div>
                        <span>{date(article.published_at)}</span>
                        <span>{insightCount} insight</span>
                      </div>
                    </div>
                    <span
                      className={insightCount ? "qaStatus ready" : "qaStatus"}
                    >
                      {insightCount ? "ĐÃ TRÍCH XUẤT" : "CẦN REVIEW"}
                    </span>
                    <button
                      className="editButton"
                      onClick={() =>
                        setEditor({ type: "article", item: article })
                      }
                    >
                      <Icon name="edit" /> Biên tập
                    </button>
                  </article>
                );
              })}
              {!filteredArticles.length && (
                <Empty
                  title="Không có bài viết"
                  copy="Chạy crawler hoặc thay đổi từ khoá tìm kiếm."
                />
              )}
            </div>
          )}

          {tab === "events" && (
            <div className="contentReviewList">
              {filteredEvents.map((event, index) => (
                <article className="eventAdminRow" key={event.id}>
                  <span className="eventNumber">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.summary || "Chưa có tóm tắt biên tập."}</p>
                  </div>
                  <div className="eventMetrics">
                    <span>
                      <b>{event.article_count}</b> bài
                    </span>
                    <span>
                      <b>{event.source_count}</b> nguồn
                    </span>
                    <small>{date(event.last_seen_at)}</small>
                  </div>
                  <button
                    className="editButton"
                    onClick={() => setEditor({ type: "event", item: event })}
                  >
                    <Icon name="edit" /> Biên tập
                  </button>
                </article>
              ))}
              {!filteredEvents.length && (
                <Empty
                  title="Không có cụm sự kiện"
                  copy="Cụm sẽ được tạo khi crawler xử lý bài viết."
                />
              )}
            </div>
          )}

          {tab === "opportunities" && (
            <div className="opportunityAdminGrid">
              {filteredOpportunities.map((item) => (
                <article className="opportunityAdminCard" key={item.id}>
                  <header>
                    <span className={`statusBadge ${item.status}`}>
                      {item.status}
                    </span>
                    <strong>{Math.round(item.score)}</strong>
                  </header>
                  <h3>{item.title}</h3>
                  <small>Dành cho {item.customer}</small>
                  <p>{item.problem}</p>
                  <footer>
                    <select
                      value={item.status}
                      disabled={busy === item.id}
                      onChange={(event) =>
                        updateOpportunity(item, { status: event.target.value })
                      }
                    >
                      {statuses.map((status) => (
                        <option key={status}>{status}</option>
                      ))}
                    </select>
                    <button
                      className="editButton"
                      onClick={() => setEditor({ type: "opportunity", item })}
                    >
                      <Icon name="edit" /> Chi tiết
                    </button>
                  </footer>
                </article>
              ))}
              {!filteredOpportunities.length && (
                <Empty
                  title="Chưa có opportunity"
                  copy="Hệ thống cần thêm tín hiệu đủ mạnh trước khi tạo luận điểm."
                />
              )}
            </div>
          )}
        </div>
      </section>

      {editor && (
        <div
          className="editorBackdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setEditor(null);
          }}
        >
          <section className="editorPanel">
            <header>
              <div>
                <p>{editor.item ? "UPDATE RECORD" : "NEW RECORD"}</p>
                <h2>
                  {editor.type === "source"
                    ? editor.item
                      ? "Chỉnh sửa nguồn"
                      : "Thêm nguồn dữ liệu"
                    : editor.type === "article"
                      ? "Biên tập bài & insight"
                      : editor.type === "event"
                        ? "Biên tập cụm sự kiện"
                        : "Duyệt opportunity"}
                </h2>
              </div>
              <button onClick={() => setEditor(null)}>
                <Icon name="close" />
              </button>
            </header>
            {editor.type === "source" && (
              <form onSubmit={saveSource} className="editorForm">
                <label>
                  <span>Tên nguồn</span>
                  <input
                    name="name"
                    required
                    defaultValue={editor.item?.name || ""}
                    placeholder="Ví dụ: CafeF"
                  />
                </label>
                <div className="formColumns">
                  <label>
                    <span>Domain</span>
                    <input
                      name="domain"
                      required
                      defaultValue={editor.item?.domain || ""}
                      placeholder="cafef.vn"
                    />
                  </label>
                  {editor.item && (
                    <label>
                      <span>Loại nguồn</span>
                      <select
                        name="source_type"
                        defaultValue={editor.item.source_type}
                      >
                        <option value="news">News</option>
                        <option value="government">Government</option>
                        <option value="research">Research</option>
                        <option value="company">Company</option>
                        <option value="community">Community</option>
                      </select>
                    </label>
                  )}
                </div>
                <label>
                  <span>RSS / Feed URL</span>
                  <input
                    type="url"
                    name="feed_url"
                    defaultValue={editor.item?.feed_url || ""}
                    placeholder="https://example.com/rss"
                  />
                </label>
                {editor.item ? (
                  <label>
                    <span>
                      Độ tin cậy: <b>{Math.round(editor.item.trust_score * 100)}%</b>
                    </span>
                    <input
                      type="range"
                      name="trust_score"
                      min="0"
                      max="1"
                      step="0.05"
                      defaultValue={editor.item.trust_score}
                      onInput={(event) => {
                        event.currentTarget.previousSibling.querySelector("b").textContent =
                          `${Math.round(event.currentTarget.value * 100)}%`;
                      }}
                    />
                  </label>
                ) : (
                  <p className="validationNote">
                    Feed sẽ được kiểm tra SSRF, độ mới, khả năng trích xuất và mức liên quan trước khi kích hoạt. Nguồn được duyệt bắt đầu với trust 60%.
                  </p>
                )}
                {editor.item && (
                  <label className="checkField">
                    <input
                      type="checkbox"
                      name="enabled"
                      defaultChecked={editor.item.enabled}
                    />
                    <i /> Cho phép crawler thu thập nguồn này
                  </label>
                )}
                <div className="formActions">
                  <button
                    type="button"
                    className="ghostButton"
                    onClick={() => setEditor(null)}
                  >
                    Huỷ
                  </button>
                  <button
                    className="primaryButton"
                    disabled={busy === "source-save"}
                  >
                    {busy === "source-save"
                      ? "Đang gửi..."
                      : editor.item
                        ? "Lưu nguồn"
                        : "Kiểm định nguồn"}
                  </button>
                </div>
              </form>
            )}
            {editor.type === "article" && (
              <form onSubmit={saveArticle} className="editorForm">
                <label>
                  <span>Tiêu đề</span>
                  <textarea
                    name="title"
                    rows="2"
                    required
                    defaultValue={editor.item.title}
                  />
                </label>
                <label>
                  <span>URL bài gốc</span>
                  <input
                    name="canonical_url"
                    type="url"
                    required
                    defaultValue={editor.item.canonical_url}
                  />
                </label>
                <label>
                  <span>Tác giả</span>
                  <input
                    name="author"
                    defaultValue={editor.item.author || ""}
                    placeholder="Chưa xác định"
                  />
                </label>
                <div className="insightEditor">
                  <p>Mỗi dòng là một insight riêng biệt.</p>
                  {insightFields.map(([field, label]) => (
                    <label key={field}>
                      <span>{label}</span>
                      <textarea
                        name={field}
                        rows="3"
                        defaultValue={(
                          editor.item.extracted?.[field] || []
                        ).join("\n")}
                        placeholder={`Nhập ${label.toLowerCase()}...`}
                      />
                    </label>
                  ))}
                </div>
                <div className="formActions">
                  <button
                    type="button"
                    className="ghostButton"
                    onClick={() => setEditor(null)}
                  >
                    Huỷ
                  </button>
                  <button
                    className="primaryButton"
                    disabled={busy === "article-save"}
                  >
                    {busy === "article-save" ? "Đang lưu..." : "Lưu thay đổi"}
                  </button>
                </div>
              </form>
            )}
            {editor.type === "event" && (
              <form onSubmit={saveEvent} className="editorForm">
                <label>
                  <span>Tên cụm sự kiện</span>
                  <textarea
                    name="title"
                    rows="2"
                    required
                    defaultValue={editor.item.title}
                  />
                </label>
                <label>
                  <span>Tóm tắt biên tập</span>
                  <textarea
                    name="summary"
                    rows="7"
                    defaultValue={editor.item.summary || ""}
                    placeholder="Tóm tắt diễn biến và ý nghĩa của cụm..."
                  />
                </label>
                <div className="recordContext">
                  <span>{editor.item.article_count} bài viết</span>
                  <span>{editor.item.source_count} nguồn</span>
                  <span>Cập nhật {date(editor.item.last_seen_at)}</span>
                </div>
                <div className="formActions">
                  <button
                    type="button"
                    className="ghostButton"
                    onClick={() => setEditor(null)}
                  >
                    Huỷ
                  </button>
                  <button
                    className="primaryButton"
                    disabled={busy === "event-save"}
                  >
                    Lưu cụm sự kiện
                  </button>
                </div>
              </form>
            )}
            {editor.type === "opportunity" && (
              <form onSubmit={saveOpportunity} className="editorForm">
                <label>
                  <span>Tiêu đề</span>
                  <textarea
                    name="title"
                    rows="2"
                    required
                    defaultValue={editor.item.title}
                  />
                </label>
                <label>
                  <span>Khách hàng</span>
                  <input
                    name="customer"
                    required
                    defaultValue={editor.item.customer}
                  />
                </label>
                <label>
                  <span>Vấn đề</span>
                  <textarea
                    name="problem"
                    rows="4"
                    required
                    defaultValue={editor.item.problem}
                  />
                </label>
                <label>
                  <span>Giải pháp</span>
                  <textarea
                    name="solution"
                    rows="4"
                    required
                    defaultValue={editor.item.solution}
                  />
                </label>
                <label>
                  <span>Trạng thái duyệt</span>
                  <select name="status" defaultValue={editor.item.status}>
                    {statuses.map((status) => (
                      <option key={status}>{status}</option>
                    ))}
                  </select>
                </label>
                <div className="formActions">
                  <button
                    type="button"
                    className="ghostButton"
                    onClick={() => setEditor(null)}
                  >
                    Huỷ
                  </button>
                  <button
                    className="primaryButton"
                    disabled={busy === editor.item.id}
                  >
                    Lưu opportunity
                  </button>
                </div>
              </form>
            )}
          </section>
        </div>
      )}
      {toast && (
        <div className={`cmsToast ${toast.tone}`}>
          {toast.tone === "error" ? "!" : "✓"} {toast.message}
        </div>
      )}
    </main>
  );
}
