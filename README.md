# Ideas Hub

Local-first Vietnam news intelligence and startup opportunity engine.

Ideas Hub turns public information into evidence-backed startup theses through a deterministic pipeline:

`sources -> articles -> facts/claims -> events -> signals -> opportunities -> validation`

The system keeps data, embeddings, analytics, and most inference local. Cloud models are optional providers for high-value reasoning only.

## Architecture

```text
Internet / RSS / URLs
        |
        v
 Source Registry
        |
        v
 Crawl + Normalize -----> MinIO raw snapshots
        |
        v
 Dedup + Local Embeddings
        |
        +----> Claims / Entities
        |
        v
 Event Clustering
        |
        v
 Signal Engine (deterministic scoring)
        |
        v
 Opportunity Engine
   generator -> skeptic -> judge
        |
        v
 Evidence-backed Opportunity Radar
```

### Core stack

- API: FastAPI + Pydantic + SQLAlchemy
- Data: PostgreSQL + pgvector
- Queue: Redis + Celery
- Raw artifacts: MinIO/S3-compatible storage
- Local embeddings: Sentence Transformers (`BAAI/bge-m3` by default)
- Local LLM: any OpenAI-compatible endpoint, designed for vLLM/Ollama
- Model routing: app-level provider abstraction; optional LiteLLM proxy
- Cloud fallback/provider choices: OpenRouter, OpenAI, Anthropic
- Web: Next.js

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- API: http://localhost:8888/docs
- Web: http://localhost:3333
- CMS / data operations: http://localhost:3333/cms
- MinIO console: http://localhost:9001

Docker images install the `local-ai` Python extra, so local embeddings are available by default in containers. For a host-only Python environment use:

```bash
pip install '.[local-ai]'
```

The default configuration does **not** require a cloud API key. If no LLM endpoint is running, deterministic ingestion/analytics still work and article extraction gracefully falls back to empty structured insight.

Optional local vLLM service:

```bash
docker compose --profile local-ai up --build
```

The Compose vLLM service loads and exposes `LOCAL_LLM_MODEL`. The default,
`Qwen/Qwen3-14B-AWQ`, is sized for a 24 GB RTX 4090. It uses a 16K context window
to leave enough VRAM for concurrent pipeline requests.

On the first start, the API idempotently seeds 17 Vietnamese business, policy,
jobs, startup, and technology feeds. New seed sources bootstrap at three items;
the `scheduler` queues all enabled feeds at `CRAWL_LIMIT` every
`CRAWL_INTERVAL_MINUTES` (10 items every 30 minutes by default). Follow it with:

```bash
docker compose logs -f scheduler worker
```

Optional LiteLLM gateway:

```bash
docker compose --profile ai-gateway up --build
```

## Model routing

Business code addresses semantic tasks, not vendors:

- `article_extract`
- `event_summary`
- `opportunity_generate`
- `opportunity_skeptic`
- `opportunity_judge`

Each task has a route such as `local`, `openrouter`, `openai`, or `anthropic`. Change providers with environment variables; no domain code changes are required.

Example:

```env
TASK_ARTICLE_EXTRACT_PROVIDER=local
TASK_OPPORTUNITY_GENERATE_PROVIDER=local
TASK_OPPORTUNITY_SKEPTIC_PROVIDER=openrouter
TASK_OPPORTUNITY_JUDGE_PROVIDER=openrouter
```

## API flow

1. Create a source with `POST /v1/sources`.
2. Trigger `POST /v1/pipeline/sources/{source_id}/crawl`.
3. Inspect `/v1/articles`, `/v1/events`, `/v1/signals`, and `/v1/opportunities`.
4. Background processing can run through Celery with `POST /v1/pipeline/sources/{source_id}/enqueue`.

## Source discovery

Every ingest records eligible external publisher links without letting a discovery
failure roll back the article. Once per day, the worker also scans the latest raw
HTML snapshots in MinIO, discovers RSS/Atom feeds, samples article extraction, and
scores candidates on feed validity, freshness, extractability, market relevance,
referral diversity, and HTTPS.

- Score 85+ is auto-approved only when every safety and quality gate also passes.
- Score 60–84 stays in the CMS review queue; lower scores are rejected.
- Rejected sources are not automatically proposed again. Transient failures retry
  in up to three discovery cycles.
- Discovery fetches permit only HTTP(S) ports 80/443, validate DNS and each redirect,
  block non-public IP space, cap redirects at three, and cap responses at 2 MB.

Operators can inspect candidates and crawl history at `/cms`, or use
`/v1/source-candidates`, `/v1/source-discovery/enqueue`, and `/v1/crawl-runs`.

Signals enter the three-stage opportunity generator at
`SIGNAL_OPPORTUNITY_THRESHOLD` (50 by default). Existing eligible signals can be
processed idempotently with `POST /v1/opportunities/backfill`.

## Design principles

- Raw article snapshots are retained locally for reproducibility/reprocessing.
- Article text is treated as untrusted data and never as agent instructions.
- Observed facts, derived metrics, and hypotheses remain distinct.
- Event clustering and signal scoring are algorithmic and reproducible.
- LLM outputs must be structured and evidence-linked.
- Cloud calls are explicit, observable, and replaceable.
- Full article republishing is intentionally not part of the product surface.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for implementation details.
