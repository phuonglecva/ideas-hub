import CmsConsole from "./CmsConsole";
import "./cms.css";

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

export default async function CmsPage() {
  const [sources, articles, events, opportunities, candidates, crawlRuns] =
    await Promise.all([
    load("/v1/sources"),
    load("/v1/articles?limit=200"),
    load("/v1/events?limit=200"),
    load("/v1/opportunities?limit=200"),
    load("/v1/source-candidates?limit=200"),
    load("/v1/crawl-runs?limit=200"),
  ]);

  return (
    <CmsConsole
      apiBase={BROWSER_API}
      initialSources={sources}
      initialArticles={articles}
      initialEvents={events}
      initialOpportunities={opportunities}
      initialCandidates={candidates}
      initialCrawlRuns={crawlRuns}
    />
  );
}
