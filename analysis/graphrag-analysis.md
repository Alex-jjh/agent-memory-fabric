# Microsoft GraphRAG - Memory System Analysis

## Overview

GraphRAG is a graph-based retrieval-augmented generation system that converts unstructured text into a structured knowledge graph, then uses that graph to answer queries. The system operates in two phases:

1. **Indexing** (write path): Documents are chunked into text units, entities and relationships are extracted via LLM, communities are detected via hierarchical Leiden clustering, and community reports are generated.
2. **Query** (read path): User queries are resolved against the knowledge graph using one of several search strategies (local, global, DRIFT, basic).

The "memory" in GraphRAG is the knowledge graph itself -- a persistent, structured representation of facts extracted from source documents.

## Storage Layer

The storage system is organized as a monorepo with a dedicated `graphrag-storage` package.

**Abstract interfaces:**
- `Storage` (ABC) at `packages/graphrag-storage/graphrag_storage/storage.py` -- key-value blob storage with `get`, `set`, `has`, `delete`, `clear`, `find`, `keys`, `child` (namespace isolation).
- `TableProvider` (ABC) at `packages/graphrag-storage/graphrag_storage/tables/table_provider.py` -- higher-level tabular abstraction with `read_dataframe`, `write_dataframe`, `has`, `list`, `open` (streaming row access), `child`.
- `VectorStore` (ABC) at `packages/graphrag-vectors/graphrag_vectors/vector_store.py` -- vector similarity search with `load_documents`, `similarity_search_by_vector`, `similarity_search_by_text`, `search_by_id`, `remove`, `update`.

**Concrete implementations:**
- Storage backends: `FileStorage`, `MemoryStorage`, `AzureBlobStorage`, `AzureCosmosStorage` (factory at `storage_factory.py` lines 57-78).
- Table providers: `ParquetTableProvider` (file/blob), `CsvTableProvider`, `CosmosTableProvider`.
- Vector stores: `LanceDB`, `AzureAISearch`, `CosmosDB`.

**Cache layer** (`graphrag-cache` package):
- `Cache` ABC with `get`/`set`/`has`/`delete`/`clear`/`child` -- used to cache LLM responses during indexing.
- Implementations: `JsonCache` (file-backed), `MemoryCache`, `NoopCache`.

**Default serialization format:** Apache Parquet for all tabular data (entities, relationships, communities, text units, documents, community reports). Vector embeddings go to the configured vector store.

## Write / Extraction Logic

The indexing pipeline is defined in `packages/graphrag/graphrag/index/workflows/factory.py`. The standard pipeline consists of:

1. **load_input_documents** -- Read source documents into storage.
2. **create_base_text_units** -- Chunk documents into text units (configurable token size).
3. **create_final_documents** -- Finalize document records.
4. **extract_graph** (`workflows/extract_graph.py`) -- The core extraction step:
   - `GraphExtractor` (`index/operations/extract_graph/graph_extractor.py` lines 38-178) prompts an LLM with text chunks to extract `("entity", name, type, description)` and `("relationship", source, target, description, weight)` tuples using delimiter-based parsing.
   - Supports **gleanings** (lines 101-122): multiple LLM passes over the same text to extract additional entities missed in the first pass.
   - Entities are merged by `(title, type)` with descriptions collected as lists; relationships merged by `(source, target)` with weights summed (`extract_graph.py` lines 104-129).
   - Descriptions are then **summarized** via LLM (`summarize_descriptions.py`) to produce a single coherent description per entity/relationship.
5. **finalize_graph** -- Compute node degrees, assign IDs, add `community_ids`.
6. **extract_covariates** -- Optional claim extraction.
7. **create_communities** (`workflows/create_communities.py`) -- Hierarchical Leiden clustering via `graspologic_native` (`graphs/hierarchical_leiden.py`). Produces multi-level community hierarchy.
8. **create_final_text_units** -- Link text units to entities/relationships.
9. **create_community_reports** -- LLM-generated summaries of each community.
10. **generate_text_embeddings** (`workflows/generate_text_embeddings.py`) -- Embeds entity descriptions, text unit text, and community report content into configured vector store.

**Incremental update path** (`IndexingMethod.StandardUpdate`): Runs the standard extraction on new documents, then merges with previous index via `update_entities_relationships`, `update_communities`, etc. Entity merging logic is in `index/update/entities.py` (groups by title, concatenates text_unit_ids, resolves ID conflicts).

## Read / Retrieval Logic

Four search strategies are implemented:

### Local Search (`query/structured_search/local_search/search.py`)
- Maps query to entities via vector similarity (`entity_extraction.py` line 62: `similarity_search_by_text` on entity description embeddings).
- Builds a mixed context window (`local_search/mixed_context.py`) with configurable proportions:
  - **Community reports** (default 25% of token budget) -- reports from communities the matched entities belong to.
  - **Entity/Relationship/Covariate tables** (default 25%) -- structured data about matched entities and their neighbors.
  - **Source text units** (default 50%) -- original text chunks linked to matched entities.
- Passes assembled context + query to LLM for final answer generation.

### Global Search (`query/structured_search/global_search/search.py`)
- **Map-Reduce** pattern over community reports.
- Map phase: Each community report batch is sent to LLM to extract key points with importance scores (lines 216-274).
- Reduce phase: Key points are filtered (score > 0), sorted by score descending, truncated to token budget, then sent to LLM for final synthesis (lines 306-431).

### DRIFT Search (`query/structured_search/drift_search/search.py`)
- Dynamic Reasoning and Inference with Flexible Traversal.
- Starts with a primer that identifies relevant communities via `DynamicCommunitySelection` (rates community relevance by LLM, traverses hierarchy top-down).
- Iteratively generates follow-up queries and performs local searches, building a query state graph.
- Final reduction synthesizes all intermediate answers.

### Basic Search
- Simplified vector-similarity-only retrieval without graph traversal.

**Entity matching** (`entity_extraction.py` lines 41-96): Uses `VectorStore.similarity_search_by_text` with oversampling (2x) to find top-k entities by description embedding similarity. Supports include/exclude entity name filters.

## Lifecycle / Decay Mechanism

**GraphRAG has no built-in memory decay or TTL mechanism.** Observations:

- The `VectorStoreDocument` dataclass has `create_date` and `update_date` fields (vector_store.py lines 39-42), and the `VectorStore` base class auto-populates timestamps and explodes them into filterable component fields (lines 97-133). This infrastructure supports time-based filtering at query time, but no automatic expiry or decay logic exists.
- `Community.period` and `CommunityReport.period` fields exist (community.py line 43, community_report.py line 37) and are set to the current date during indexing (`create_communities.py` line 181). These could support temporal versioning but no pruning logic uses them.
- The incremental update pipeline identifies **deleted documents** (`incremental_index.py` lines 49-57: documents in previous index but not in current input) but does not implement actual deletion of their associated entities/relationships from the graph.
- There is no relevance decay, access-frequency tracking, or aging mechanism.

## Key Data Structures

All defined in `packages/graphrag/graphrag/data_model/`:

| Structure | Base Class | Key Fields |
|-----------|-----------|------------|
| `Entity` | `Named` (has `id`, `title`) | `type`, `description`, `description_embedding`, `community_ids`, `text_unit_ids`, `rank` (degree centrality) |
| `Relationship` | `Identified` (has `id`) | `source`, `target`, `weight`, `description`, `description_embedding`, `text_unit_ids`, `rank` |
| `Community` | `Named` | `level`, `parent`, `children`, `entity_ids`, `relationship_ids`, `text_unit_ids`, `size`, `period` |
| `CommunityReport` | `Named` | `community_id`, `summary`, `full_content`, `rank`, `full_content_embedding`, `size`, `period` |
| `TextUnit` | `Identified` | `text`, `entity_ids`, `relationship_ids`, `n_tokens`, `document_id` |
| `Document` | `Named` | `type`, `text_unit_ids`, `text` |
| `Covariate` | `Identified` | `subject_id`, `attributes` (claim data) |

**Hierarchy:** `Identified` -> `Named` -> domain types. All use Python `dataclasses`.

**Runtime structures:**
- `VectorStoreDocument`: `id`, `vector`, `data` dict, `create_date`, `update_date`
- `VectorStoreSearchResult`: `document` + `score`
- `PipelineRunContext`: bundles `input_storage`, `output_storage`, `output_table_provider`, `cache`, `callbacks`, `state`

## Notable Design Decisions

1. **LLM-driven extraction over rule-based NER**: Entity and relationship extraction relies entirely on prompted LLM calls, not traditional NLP. The "fast" pipeline (`extract_graph_nlp`) offers a noun-phrase-based alternative but is secondary.

2. **Hierarchical community structure**: Uses graspologic's hierarchical Leiden algorithm to create multi-level communities, enabling both high-level global queries (traverse top-level community reports) and detailed local queries.

3. **Description summarization as deduplication**: When the same entity appears across multiple text chunks, all descriptions are collected and summarized by LLM into a single coherent description -- effectively a memory consolidation step.

4. **Token-budget-aware context building**: All context builders carefully count tokens and partition the context window by configurable proportions (community_prop, text_unit_prop, local_prop), ensuring the LLM prompt never exceeds limits.

5. **Pluggable storage with factory pattern**: Storage, table providers, vector stores, and caches all use abstract base classes with factory-based registration, allowing easy swapping between local files and cloud services.

6. **No automatic decay or forgetting**: The system is append-only during incremental updates. Deleted documents are detected but their graph contributions are not pruned. This is a conscious trade-off for simplicity at the cost of potential stale information.

7. **Parquet as the canonical table format**: All intermediate and final indexing outputs are stored as Parquet files, providing efficient columnar access for the pandas-heavy query path.

8. **Streaming table API**: The `Table` / `TableProvider.open()` interface supports row-by-row streaming for large datasets during embedding generation, avoiding loading entire DataFrames into memory.

9. **Separation of extraction and embedding**: Graph extraction and embedding generation are distinct pipeline stages, allowing re-embedding without re-extraction.

10. **DRIFT as iterative refinement**: The DRIFT search strategy models query answering as a graph traversal problem with follow-up queries, providing deeper coverage than single-shot local search at the cost of more LLM calls.
