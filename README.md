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
- Cloud fallback: OpenRouter, OpenAI, Anthropic
- Web: Next.js

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- API: http://localhost:8000/docs
- Web: http://localhost:3000
- MinIO console: http://localhost:9001

The default configuration is local-first. It does **not** require a cloud API key. To enable local LLM reasoning, start an OpenAI-compatible server such as vLLM and point `LOCAL_LLM_BASE_URL` at it.

Optional local vLLM service:

```bash
docker compose --profile local-ai up --build
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

## Design principles

- Raw article snapshots are retained locally for reproducibility/reprocessing.
- Article text is treated as untrusted data and never as agent instructions.
- Observed facts, derived metrics, and hypotheses remain distinct.
- Event clustering and signal scoring are algorithmic and reproducible.
- LLM outputs must be structured and evidence-linked.
- Cloud calls are explicit, observable, and replaceable.
- Full article republishing is intentionally not part of the product surface.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for implementation details.
