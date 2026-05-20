## Overview

MemoryOS is a three-tier memory operating system for LLM-based AI agents, developed by BAI-LAB. It models human-like memory with short-term, mid-term, and long-term stores. The system automatically promotes memories across tiers based on capacity pressure and "heat" (a composite relevance/recency score), and extracts structured knowledge and user profiles from conversation history using LLM calls.

The primary implementation analyzed is `memoryos-chromadb/`, which uses ChromaDB as its vector store backend.

---

## Storage Layer

**File:** `memoryos-chromadb/storage_provider.py`

The `ChromaStorageProvider` class is the unified persistence backend. It combines:

1. **ChromaDB PersistentClient** (line 24) -- stores embeddings and enables vector similarity search. Three collections are created per user/assistant pair:
   - `mid_term_memory_user_{user_id}` -- session summaries and page embeddings
   - `user_knowledge_{user_id}` -- long-term user knowledge entries
   - `assistant_knowledge_{assistant_id}` -- long-term assistant knowledge entries

2. **JSON metadata file** (`metadata_{user_id}_{assistant_id}.json`, line 35) -- stores everything that is not a vector:
   - `mid_term_sessions` (full session objects with `pages_backup` arrays)
   - `access_frequency` (LFU counters per session)
   - `heap_state` (serialized max-heap for heat ordering)
   - `short_term_memory` (raw QA pair list)
   - `user_profiles` (structured profile dicts)
   - `update_times` (timestamps for last profile/knowledge update)

Persistence is lazy -- `save_all_metadata()` writes the JSON file and is called via `atexit` (line 81 of `memoryos.py`). ChromaDB persists automatically via `PersistentClient`.

Distance function is configurable (default: cosine). Distances are converted to similarity scores (lines 38-47).

---

## Write / Extraction Logic

### Ingestion path (`memoryos.py` lines 236-260, `updater.py`)

1. **`add_memory(user_input, agent_response)`** appends a QA pair to short-term memory.
2. When short-term is full (default capacity 10), the `Updater.process_short_term_to_mid_term()` method is triggered **before** the new item is added (to prevent silent data loss from deque auto-eviction).

### Short-term to mid-term promotion (`updater.py` lines 107-204)

1. All QA pairs are popped from short-term.
2. For each pair, an LLM call checks **conversation continuity** with the previous page (`check_conversation_continuity`). If continuous, a linked-list (`pre_page`/`next_page`) is formed and a running **meta_info** summary is generated.
3. The batch is sent to `gpt_generate_multi_summary` which returns up to 2 thematic sub-summaries (with keywords).
4. For each theme, `MidTermMemory.insert_pages_into_session()` searches existing sessions by combined semantic + keyword similarity (Jaccard). If a match exceeds the threshold (default 0.6), pages are merged into the existing session; otherwise a new session is created.

### Mid-term to long-term promotion (`memoryos.py` lines 138-234)

Triggered after every `add_memory` call via `_trigger_profile_and_knowledge_update_if_needed()`:
1. Peeks at the hottest session on the heap.
2. If heat >= threshold (default 5.0), collects all `analyzed=False` pages.
3. In parallel (ThreadPoolExecutor), two LLM tasks run:
   - **Profile update** (`gpt_user_profile_analysis`) -- analyzes conversation against 90 personality dimensions and merges with existing profile.
   - **Knowledge extraction** (`gpt_knowledge_extraction`) -- extracts user private data and assistant knowledge as bullet-point facts.
4. Extracted knowledge items are embedded and stored in the ChromaDB knowledge collections.
5. Session heat is reset (`N_visit=0`, `L_interaction=0`), pages marked `analyzed=True`.

---

## Read / Retrieval Logic

**File:** `memoryos-chromadb/retriever.py`

`Retriever.retrieve_context()` runs three retrieval paths **in parallel** (lines 112-134):

1. **Mid-term page retrieval** (`_retrieve_mid_term_context`):
   - Embeds the query, searches ChromaDB for top-k session summaries filtered by similarity threshold.
   - For matched sessions, searches individual pages within those sessions.
   - Uses a min-heap of capacity `retrieval_queue_capacity` (default 7) to collect the highest-scoring pages across all sessions.
   - On access, increments session `N_visit`, updates `last_visit_time`, recalculates heat.

2. **User knowledge retrieval** (`_retrieve_user_knowledge`):
   - Embeds query, searches `user_knowledge` collection, filters by similarity threshold (default 0.01).

3. **Assistant knowledge retrieval** (`_retrieve_assistant_knowledge`):
   - Same pattern against `assistant_knowledge` collection.

The final response generation (`get_response`, lines 262-373) assembles:
- Short-term history (full recent context)
- Retrieved mid-term pages (with dialogue chain meta_info)
- User profile (JSON)
- Relevant user and assistant knowledge

All fed into a system+user prompt for the LLM.

---

## Lifecycle / Decay Mechanism

### Heat function (`mid_term.py` lines 22-37)

```
H_segment = alpha * N_visit + beta * L_interaction + gamma * R_recency
```

Where:
- `N_visit` -- number of times the session was accessed during retrieval
- `L_interaction` -- number of pages in the session
- `R_recency = exp(-delta_hours / tau)` with `tau=24 hours` (exponential time decay, `utils.py` lines 154-163)
- Default weights: `alpha=1.0, beta=1.0, gamma=1.0`

### Eviction policies

- **Short-term:** FIFO via deque with `maxlen` (default 10). Oldest items are popped and promoted to mid-term.
- **Mid-term:** LFU (Least Frequently Used). When session count exceeds `max_capacity` (default 2000), the session with the lowest `access_count_lfu` is deleted from both ChromaDB and metadata (`evict_lfu`, `mid_term.py` lines 75-95).
- **Long-term knowledge:** Oldest-first eviction. When knowledge count exceeds `knowledge_capacity` (default 100), items are sorted by timestamp and the oldest are deleted (`enforce_knowledge_capacity`, `storage_provider.py` lines 336-348).

### Heat reset

After profile/knowledge extraction from a hot session, its `N_visit` and `L_interaction` are zeroed and the heap is rebuilt. This prevents the same session from repeatedly triggering analysis.

---

## Key Data Structures

| Structure | Location | Description |
|-----------|----------|-------------|
| `deque(maxlen=N)` | `short_term.py` | Fixed-size FIFO buffer for recent QA pairs |
| Max-heap (via negated min-heap) | `mid_term.py` `self.heap` | Priority queue of `(-H_segment, session_id)` tuples for heat ordering |
| Session dict | `storage_provider.py` lines 107-136 | Contains `id`, `summary`, `summary_keywords`, `L_interaction`, `R_recency`, `N_visit`, `H_segment`, `timestamp`, `last_visit_time`, `access_count_lfu`, `pages_backup[]` |
| Page dict | `updater.py` lines 125-135 | Contains `page_id`, `user_input`, `agent_response`, `timestamp`, `preloaded`, `analyzed`, `pre_page`, `next_page`, `meta_info`, `page_keywords`, `page_embedding` |
| `access_frequency` | `mid_term.py` | `defaultdict(int)` mapping session_id to LFU access count |
| User profile | `storage_provider.py` metadata | Free-form dict (structured by 90 personality dimensions) |
| Knowledge entry | ChromaDB collections | Embedding vector + metadata (`type`, `timestamp`, `text`) |

---

## Notable Design Decisions

1. **Dual storage architecture:** ChromaDB handles vector search while a JSON sidecar file stores all structured metadata. This avoids complex ChromaDB metadata queries but creates a consistency risk if the process crashes before `atexit` fires.

2. **LLM-in-the-loop at write time:** Every short-to-mid-term promotion requires multiple LLM calls (continuity check, multi-summary, keyword extraction, meta_info generation). This makes writes expensive but ensures semantically rich session organization.

3. **Heat-based analysis trigger:** Profile/knowledge extraction is lazy -- only triggered when a session accumulates enough heat. This amortizes the cost of expensive LLM analysis calls.

4. **Conversation chain tracking:** Pages form a doubly-linked list (`pre_page`/`next_page`) with running `meta_info` summaries. This preserves dialogue context across session boundaries and is surfaced during retrieval.

5. **Parallel retrieval:** All three retrieval paths (mid-term pages, user knowledge, assistant knowledge) execute concurrently via ThreadPoolExecutor, minimizing latency.

6. **Capacity-first eviction strategy:** Short-term uses FIFO (simple, predictable), mid-term uses LFU (preserves frequently-accessed sessions), long-term uses oldest-first (assumes newer knowledge is more relevant).

7. **Embedding model flexibility:** Supports both SentenceTransformers (default: `all-MiniLM-L6-v2`) and BGE-M3 via FlagEmbedding, with an in-memory embedding cache to avoid redundant computation.

8. **90-dimension personality model:** The user profile is structured around a detailed taxonomy spanning psychological traits, AI alignment expectations, and content interest tags -- significantly more granular than typical chatbot memory systems.
