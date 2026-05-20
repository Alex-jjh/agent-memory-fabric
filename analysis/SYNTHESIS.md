# Agent Memory Systems — Comparative Synthesis

Generated 2026-05-20 from analysis of 12 open-source repositories.

## Comparison Table

| System | Storage Type | Write Ops | Decay / Lifecycle | Retrieval Method | Graph Support | Proactive Injection |
|--------|-------------|-----------|-------------------|-----------------|---------------|-------------------|
| **GAAMA** | SQLite + sqlite-vec + FTS5 | LLM extracts episodes → facts → reflections (3-level) | None (hard delete only) | Vector KNN + Personalized PageRank; combined score | Yes (igraph; entity/concept/fact nodes) | No |
| **HippoRAG** | Parquet-backed vector stores + igraph (pickle) | LLM OpenIE: NER → triple extraction → KG construction | None | Fact scoring → LLM rerank → PPR over KG → passage ranking | Yes (igraph; entity + passage nodes, 3 edge types) | No |
| **Hindsight** | PostgreSQL + pgvector (schema-per-tenant) | 3-phase transaction: entity resolution → ANN lookup → write; streaming producer-consumer | Recency-weighted scoring (implicit); consolidation merges facts into observations | 4-way parallel (semantic HNSW, BM25, graph expansion, temporal spreading) → RRF → cross-encoder rerank | Yes (memory_links table: temporal/semantic/causal/entity edges) | No |
| **GraphRAG** | Parquet + LanceDB/Azure AI Search | 10-step pipeline: chunk → LLM entity extraction (multi-pass) → Leiden community detection → LLM report generation | None (append-only) | Local (entity vector match), Global (map-reduce over communities), DRIFT (iterative), Basic (vector) | Yes (hierarchical communities via Leiden algorithm) | No |
| **LightRAG** | JSON KV + NanoVectorDB + NetworkX GraphML | LLM entity/relation extraction → graph merge; map-reduce summarization on accumulation | None (additive only; explicit delete requires graph rebuild) | LLM keyword extraction → vector search → graph traversal → token truncation → LLM synthesis; 5 modes | Yes (NetworkX; entity + relation nodes) | No |
| **Cognee** | Neo4j/Ladybug (graph) + LanceDB/PGVector (vector) + SQLite/PostgreSQL (relational) + Redis (cache) | `remember()` → `add()` → `cognify()` pipeline; LLM entity extraction into structured KG | Session cache TTL (7-day default); permanent layer has no decay; feedback_weight on nodes | Multi-source auto-routing: session, trace, graph context, full graph search; feedback-weighted ranking | Yes (knowledge graph with typed triplets; feedback weights) | No |
| **Mem0** | Vector store (30+ providers, default Qdrant) + SQLite (history) + entity vector store | LLM extracts atomic facts (ADD-only V3); MD5 hash dedup; spaCy entity extraction | None in OSS SDK (decay is platform-only server feature) | Hybrid: semantic similarity + BM25 keyword + entity boost; adaptive normalization; optional reranking | Partial (entity linking via auxiliary vector store; not a traversable graph) | No |
| **Letta** | PostgreSQL + pgvector (up to 4096 dims); optional Turbopuffer/Pinecone dual-write; optional git-backed | Agent self-edits core memory blocks via tool calls (replace/insert/rethink/patch); archival via `insert_archival` | None (explicit overwrite only); "sleeptime" agents do async consolidation | Core: in-context (always injected); Archival: semantic search + tag/temporal filters; Recall: hybrid text+vector RRF | No | **Partial** (core memory always in system prompt; sleeptime agents proactively consolidate) |
| **MemoryOS** | ChromaDB (vector) + JSON sidecar (metadata) | LLM summarization + continuity detection; short→mid promotion via updater | **Yes**: Heat formula `H = α·visits + β·interaction_len + γ·exp(-Δt/24)`; LFU eviction in mid-term | Parallel retrieval across 3 tiers (short/mid/long) via ThreadPoolExecutor | No | No |
| **CortexGraph** | JSONL (append-only) or SQLite; Obsidian vault for LTM | Auto-enrichment: entity extraction (spaCy/regex), importance scoring, embeddings | **Yes**: Power-law/exponential/two-component decay; threshold forget (0.05) / promote (0.65); GC + consolidation | Decay-weighted search + optional semantic similarity (cosine/Jaccard); spaced repetition blended into results | Yes (knowledge graph with typed relations, clusters) | **Yes** (spaced repetition: fading memories opportunistically injected when contextually relevant) |
| **basic-memory** | SQLite/PostgreSQL (derived index) + filesystem Markdown (source of truth) | MCP tool → write Markdown file → upsert DB entity/observations/relations; custom markdown-it parsing | None (sync removes stale index rows only) | Multi-strategy: permalink → title → FTS fallback; graph traversal via `build_context` | Yes (relations extracted from Markdown `[[links]]`) | No |
| **mcp-mem0** | Supabase/PostgreSQL + pgvector (1536 or 768 dims) | Text → mem0 `add()` (LLM fact extraction + embedding); single hardcoded user | None (memories persist indefinitely; no delete tool) | Semantic vector search (default limit 3) or full paginated retrieval | No | No |

## Key Findings

### 1. Decay/Lifecycle is Rare
Only **2 of 12** systems implement meaningful automatic decay:
- **MemoryOS**: Heat-based scoring with temporal exponential decay and LFU eviction
- **CortexGraph**: Power-law decay with explicit promote/forget thresholds and GC

Most systems are purely additive — memories persist until explicitly deleted. This validates the AMF research gap: lifecycle management is under-explored in practice.

### 2. Proactive Injection is Nearly Absent
Only **CortexGraph** implements true proactive injection (spaced repetition blended into search results). **Letta** has a partial version (core memory always in system prompt + sleeptime consolidation). The remaining 10 systems are entirely reactive — they only retrieve when explicitly queried.

### 3. Graph Support is Common but Shallow
**9 of 12** systems incorporate some form of graph structure, but most use it only for retrieval augmentation (hop expansion, PPR). Only CortexGraph and Cognee use graph structure for lifecycle decisions (promotion, consolidation, feedback weighting).

### 4. LLM-at-Write-Time is the Dominant Pattern
**10 of 12** systems use LLMs during the write path for entity/fact extraction. The two exceptions are basic-memory (structured Markdown parsing) and mcp-mem0 (delegates to mem0 which itself uses LLM). This creates a significant latency/cost trade-off at ingestion time.

### 5. Retrieval Sophistication Varies Widely
- **Simple**: mcp-mem0 (vector only), basic-memory (FTS + permalink)
- **Hybrid**: Mem0 (semantic + BM25 + entity), Hindsight (4-way + RRF), Letta (hybrid RRF)
- **Graph-augmented**: GAAMA, HippoRAG (PPR), GraphRAG (community-based), LightRAG (graph traversal)
- **Decay-weighted**: CortexGraph, MemoryOS (heat-based)

### 6. Storage Convergence
PostgreSQL + pgvector is the most common production-grade storage choice (Hindsight, Letta, Cognee, basic-memory, mcp-mem0). Research systems prefer lighter options (SQLite, Parquet, JSON). Graph databases (Neo4j, igraph) appear alongside relational stores rather than replacing them.

## Relevance to AMF (Agent Memory Fabric)

| AMF Design Goal | Best Reference Systems |
|----------------|----------------------|
| Lifecycle state machine (active → archive → expire) | CortexGraph (promote/forget thresholds), MemoryOS (heat + eviction) |
| Multi-signal retrieval | Hindsight (4-way RRF), GAAMA (PPR + cosine), GraphRAG (community reports) |
| Proactive injection gateway | CortexGraph (spaced repetition injection), Letta (always-on core memory) |
| Graph-augmented memory | HippoRAG (PPR), GAAMA (GEL self-healing), Cognee (feedback-weighted KG) |
| Hierarchical tiers (hot/warm/cold) | MemoryOS (short/mid/long), Letta (core/archival/recall) |
| User transparency | basic-memory (Markdown files as source of truth), Letta (visible core blocks) |
| Production scalability | Hindsight (schema-per-tenant PG), GraphRAG (Azure backends), Mem0 (30+ vector providers) |
