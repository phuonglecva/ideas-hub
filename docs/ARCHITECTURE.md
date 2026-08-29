# Architecture

## 1. Why local-first

Bulk news processing is high-volume and repetitive. Sending every article to a premium model is expensive, slow, hard to reproduce, and unnecessary. Ideas Hub therefore keeps the following local by default:

- raw content storage
- normalized article database
- embeddings
- deduplication
- event clustering
- time-series/signal scoring
- most extraction and summarization inference

Only high-value reasoning stages may use a cloud provider.

## 2. Provider independence

`ModelGateway` is the only module that knows vendor SDK details. Domain code asks for a semantic task (`article_extract`, `opportunity_skeptic`, etc.), then validates the response against a Pydantic schema.

Providers:

- `local`: any OpenAI-compatible endpoint such as vLLM or Ollama
- `openrouter`: OpenRouter's OpenAI-compatible endpoint
- `openai`: direct OpenAI
- `anthropic`: direct Anthropic

The task-to-provider map is environment configuration. This prevents vendor names from leaking into business logic.

## 3. Evidence pipeline

### Source -> Article

Source registry stores provenance and trust weight. RSS discovery is implemented first because it is cheap and predictable; source-specific adapters can be added later without changing downstream processing.

Raw HTML is saved to MinIO before analysis so improved extractors can replay historical data.

### Article -> Structured insight

Article text is explicitly marked untrusted. The extraction model receives a strict schema and is asked only for evidence present in the article. Model failure does not block ingestion.

### Article -> Event

Clustering is deterministic: local embedding similarity attaches an article to a recent event above a configured threshold. Otherwise it creates a new event. LLMs do not decide cluster membership.

The MVP centroid is the first matching article vector. A later version should maintain a normalized rolling centroid and incorporate entity overlap + temporal distance.

### Event -> Signal

Signal scores are numerical features, not LLM judgments. MVP features are velocity, persistence, source breadth, authority, novelty, and economic relevance. Novelty and economic relevance currently start with conservative priors; they should be replaced by historical topic baselines and ontology-driven economic features once enough history exists.

### Signal -> Opportunity

Only stronger signals are sent to the reasoning pipeline. It runs three typed stages:

1. generator: customer/problem/solution/why-now/wedge/distribution/reason-to-win
2. skeptic: counter-evidence, substitutes, fatal risks, validation tests, kill criteria
3. judge: conservative dimension scores + separate evidence confidence

`OpportunityScore.weighted_score()` is deterministic. Confidence is distinct from attractiveness.

## 4. Data model

Core entities:

- `Source`
- `Article`
- `Event`
- `EventArticle`
- `Signal`
- `Opportunity`
- `ModelRun`

The next schema milestone should normalize extracted `Claim`, `Entity`, and `Relation` records from the current JSON insight field. That forms the Evidence Graph without requiring Neo4j; PostgreSQL adjacency tables are sufficient initially.

## 5. Scaling path

Do not introduce infrastructure before workload demands it.

MVP:

- PostgreSQL + pgvector
- Redis/Celery
- MinIO

Add OpenSearch only when PostgreSQL full-text becomes limiting. Add ClickHouse when historical analytical queries become large enough to justify a separate OLAP store. Add Kafka/Redpanda when multiple independent consumers need replayable high-throughput streams. Add a graph database only when graph traversal complexity proves PostgreSQL relations insufficient.

## 6. Quality roadmap

The strongest future differentiator is not crawling or the LLM. It is the evaluation dataset and historical signal graph.

Priorities:

1. Build Vietnamese problem/change/regulation/company ontology.
2. Normalize claims with provenance and claim type.
3. Detect syndicated news so one press release does not count as many independent sources.
4. Add external demand signals: jobs, app reviews, search trends, company launches, GitHub activity.
5. Add evidence contradiction detection.
6. Add human ratings such as strong/obvious/no-WTP/too-competitive/impossible.
7. Backtest historical cutoffs and measure Precision@K for opportunities that later showed real market traction.

## 7. Legal/product boundary

The system is designed as an intelligence layer rather than an article republisher. Store raw snapshots privately for processing/reproducibility; user-facing surfaces should emphasize source metadata, links, extracted facts, derived signals, and original analysis. Source-specific crawling, retention, and display policies should be added to `Source` as the registry grows.
