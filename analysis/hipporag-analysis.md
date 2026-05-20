# HippoRAG Memory System Analysis

## Overview

HippoRAG is a neurobiologically-inspired Retrieval-Augmented Generation framework that models long-term memory through a knowledge graph constructed from documents via Open Information Extraction (OpenIE). It draws an analogy to the hippocampal indexing theory: the neocortex stores raw passages (chunks), the hippocampus maintains a graph of entity relationships (knowledge graph), and the parahippocampal region handles pattern separation/completion via Personalized PageRank (PPR).

The core implementation lives in `src/hipporag/HippoRAG.py` (main orchestrator, ~1600 lines), `src/hipporag/embedding_store.py` (vector storage), and `src/hipporag/information_extraction/openie_openai.py` (knowledge extraction).

## Storage Layer

HippoRAG uses three parallel storage mechanisms:

### 1. Embedding Stores (Parquet-backed vector DB)
File: `src/hipporag/embedding_store.py`

Three `EmbeddingStore` instances manage different data types:
- **chunk_embedding_store** -- raw passage embeddings (lines 142-144 of HippoRAG.py)
- **entity_embedding_store** -- entity/phrase node embeddings (lines 145-147)
- **fact_embedding_store** -- triple/fact embeddings (lines 148-150)

Each store persists to a Parquet file (`vdb_{namespace}.parquet`) containing columns: `hash_id`, `content`, `embedding`. Data is loaded entirely into memory on init (lines 92-108 of embedding_store.py). IDs are MD5 hashes of content with a namespace prefix (e.g., `chunk-`, `entity-`, `fact-`).

### 2. Knowledge Graph (igraph, Pickle-serialized)
File: `src/hipporag/HippoRAG.py`, lines 167-198

An `igraph.Graph` (directed or undirected per config) stores entities and passages as nodes, connected by:
- **Fact edges** -- subject-object links from extracted triples (weighted by co-occurrence count)
- **Passage edges** -- chunk-to-entity links (weight=1.0)
- **Synonymy edges** -- entity-to-entity links based on embedding similarity (weight=cosine sim score)

Serialized via `graph.write_pickle()` / `Graph.Read_Pickle()`.

### 3. OpenIE Results Cache (JSON file)
File: `src/hipporag/HippoRAG.py`, lines 884-927

Extracted entities and triples are cached in a JSON file (`openie_results_ner_{llm_name}.json`) so re-indexing skips already-processed chunks.

## Write / Extraction Logic

The indexing pipeline (`HippoRAG.index()`, line 218) proceeds as:

1. **Chunk insertion** -- Documents are hashed and inserted into `chunk_embedding_store`. Duplicates are skipped via hash-based deduplication (embedding_store.py, lines 63-90).

2. **OpenIE extraction** (information_extraction/openie_openai.py):
   - **NER step** -- LLM extracts named entities from each passage using a one-shot JSON prompt (templates/ner.py).
   - **Triple extraction step** -- Given entities + passage, LLM extracts (subject, predicate, object) triples using an RDF-style prompt (templates/triple_extraction.py).
   - Both steps run in parallel via `ThreadPoolExecutor` (openie_openai.py, lines 135-210).

3. **Entity and fact encoding** -- Unique entities and stringified triples are embedded and stored in their respective embedding stores (HippoRAG.py, lines 259-263).

4. **Graph construction** (HippoRAG.py, lines 265-278):
   - `add_fact_edges()` -- Creates entity-entity edges from triples, tracks entity-to-chunk membership.
   - `add_passage_edges()` -- Links chunk nodes to their constituent entity nodes.
   - `add_synonymy_edges()` -- KNN search over entity embeddings; edges added when cosine similarity exceeds threshold (default 0.8, config `synonymy_edge_sim_threshold`).
   - `augment_graph()` -- Materializes nodes/edges into the igraph structure and persists.

5. **Deletion** (`HippoRAG.delete()`, line 280) -- Removes chunks, and only removes triples/entities that no longer appear in any remaining chunk (reference-counting logic).

## Read / Retrieval Logic

The retrieval pipeline (`HippoRAG.retrieve()`, line 363) performs:

1. **Prepare retrieval objects** (`prepare_retrieval_objects()`, line 1150) -- Loads all embeddings into NumPy arrays, builds node-name-to-index maps, reconstructs `ent_node_to_chunk_ids` if needed.

2. **Query embedding** (`get_query_embeddings()`, line 1254) -- Encodes query with two different instructions: one for fact matching (`query_to_fact`) and one for passage matching (`query_to_passage`).

3. **Fact scoring** (`get_fact_scores()`, line 1290) -- Dot product between query embedding and all fact embeddings, min-max normalized.

4. **Recognition memory / Reranking** (`rerank_facts()`, line 1522 + `rerank.py`) -- Top-k facts are filtered by an LLM-based reranker (DSPyFilter) that uses few-shot prompting to select the most relevant facts for the query.

5. **Graph-based retrieval** (`graph_search_with_fact_entities()`, line 1407):
   - Assigns phrase weights from fact scores (inversely weighted by entity frequency across chunks).
   - Computes dense passage retrieval scores (dot product with passage embeddings).
   - Combines phrase and passage weights as PPR reset probabilities.
   - Runs **Personalized PageRank** (`run_ppr()`, line 1572) on the knowledge graph with damping=0.5 (configurable). Uses igraph's `personalized_pagerank()` with PRPACK implementation.
   - Extracts passage node scores from PPR result, sorted descending.

6. **Fallback** -- If no facts survive reranking, falls back to pure dense passage retrieval (DPR).

## Lifecycle / Decay Mechanism

**HippoRAG has no explicit temporal decay, forgetting, or memory lifecycle mechanism.** Once indexed, memories persist indefinitely until explicitly deleted via `HippoRAG.delete()`. There is no:
- Time-based decay of edge weights or node relevance
- Access-frequency boosting
- Consolidation/compaction of old memories
- Capacity limits triggering eviction

The only lifecycle-like behavior is:
- **Incremental updates** -- New documents can be added without reprocessing existing ones (hash-based dedup).
- **Explicit deletion** -- Documents can be removed, cascading to orphaned entities/triples.
- **Force rebuild** -- Config flags `force_index_from_scratch` and `force_openie_from_scratch` allow full reconstruction.

## Key Data Structures

| Structure | Type | Purpose |
|-----------|------|---------|
| `EmbeddingStore` | Class (Parquet + in-memory lists) | Stores hash_id, content, embedding vectors for chunks/entities/facts |
| `igraph.Graph` | Pickle-serialized graph | Knowledge graph with entity/passage nodes and weighted edges |
| `node_to_node_stats` | `Dict[(str,str), float]` | Edge weight accumulator during indexing |
| `ent_node_to_chunk_ids` | `Dict[str, Set[str]]` | Maps entity node keys to the set of chunk IDs containing them |
| `NerRawOutput` | Dataclass | Holds chunk_id, raw LLM response, extracted unique entities, metadata |
| `TripleRawOutput` | Dataclass | Holds chunk_id, raw LLM response, extracted triples, metadata |
| `QuerySolution` | Dataclass | Query + retrieved docs + scores + optional answer/gold data |
| `BaseConfig` | Dataclass | All hyperparameters (damping, top-k, thresholds, model names, etc.) |
| `query_to_embedding` | `Dict['triple'\|'passage', Dict[str, ndarray]]` | Cached query embeddings for reuse |

Content IDs are computed as `prefix + MD5(content)` via `compute_mdhash_id()` (misc_utils.py, lines 115-126).

## Notable Design Decisions

1. **Dual-instruction query encoding** -- Queries are embedded twice with different task instructions (`query_to_fact` vs `query_to_passage`) to optimize similarity for different targets (linking.py, lines 1-10).

2. **LLM-as-reranker (Recognition Memory)** -- Rather than relying solely on embedding similarity, an LLM filters candidate facts in a few-shot classification setup (rerank.py). This models hippocampal pattern completion.

3. **Synonymy edges via embedding KNN** -- Entities that embed similarly (cosine > 0.8) get connected, enabling the graph to bridge paraphrases and aliases without explicit coreference resolution (HippoRAG.py, lines 821-882).

4. **Inverse document frequency weighting for entities** -- When computing phrase weights for PPR, fact scores are divided by the number of chunks containing that entity (`len(ent_node_to_chunk_ids[phrase_key])`), down-weighting common entities (HippoRAG.py, lines 1463-1464).

5. **PPR as associative retrieval** -- Personalized PageRank propagates activation from matched entities/passages through the graph, naturally surfacing documents connected via multi-hop reasoning paths -- analogous to hippocampal pattern completion.

6. **Undirected graph default** -- Despite triples being directional, the graph defaults to undirected (`is_directed_graph=False`), allowing bidirectional information flow during PPR.

7. **No chunking built-in** -- The `index()` method accepts pre-chunked documents; chunking is handled externally (config suggests token-based chunking parameters but implementation is separate).

8. **Purely in-memory retrieval** -- All embeddings are loaded into NumPy arrays for retrieval; no approximate nearest neighbor index is used. This trades memory for simplicity and exact results.
