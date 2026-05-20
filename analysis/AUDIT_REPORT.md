# Code Audit Report: Phase 1+2 Implementation

*Generated: 2026-05-20 | Auditors: 5 parallel sub-agents*

---

## Executive Summary

177 tests pass. Individual modules are well-implemented. **Critical gap: the engine doesn't wire Phase 2 modules together.** WriteRouter, MultiSignalScorer, MemoryExtractor, and BetaConfidence are all implemented + tested but never called from `MemoryEngine`.

| Severity | Count | Key Pattern |
|----------|-------|-------------|
| Critical | 7 | Integration gaps (modules exist but aren't connected) |
| Medium | 25 | Spec deviations, edge cases, naming issues |
| Low | 17 | Code quality, dead code, minor edge cases |

---

## Critical Issues (Must Fix)

### C1. engine.write() does NOT use WriteRouter — dedup is dead code
- **File**: `core/engine.py:62-105`
- **Impact**: FR-003 violated. No hash dedup, no operation classification. Duplicates are never detected.
- **Fix**: Wire WriteRouter into engine.write() — classify operation, check dedup, dispatch.

### C2. engine.search() does NOT use MultiSignalScorer — raw FTS5 only
- **File**: `core/engine.py:163-187`
- **Impact**: Search returns raw BM25 order. Recency, frequency, and state-filter scoring never applied.
- **Fix**: After FTS5 retrieval, pass candidates through MultiSignalScorer.score().

### C3. scorer.py uses `self.weights.semantic` for BM25 signal — wrong weight field
- **File**: `read/scorer.py:119`
- **Impact**: When Phase 3 adds actual semantic similarity, the weight will be double-allocated.
- **Fix**: Use a temporary mapping or rename. For Phase 2, treat `semantic` as "relevance" weight.

### C4. engine.run_consolidation() and engine.retrieve_proactive() don't exist
- **File**: `core/engine.py`
- **Impact**: Spec-documented API methods missing entirely.
- **Fix**: Add stubs with `NotImplementedError("Phase 3")` to maintain API contract.

### C5. node.touch() in search not persisted back to stores
- **File**: `core/engine.py:182`
- **Impact**: access_count and last_accessed updates are ephemeral — lost after function returns.
- **Fix**: Persist touched node to markdown + sqlite after search.

### C6. Double os.close() in markdown.py error handler
- **File**: `storage/markdown.py:111`
- **Impact**: If os.replace() fails, error handler calls os.get_inheritable(fd) on already-closed fd → OSError masks original exception.
- **Fix**: Track closure with boolean flag.

### C7. _is_contradiction() always returns True for non-duplicate content
- **File**: `write/router.py:58-63`
- **Impact**: Any call to classify() with an existing_node will get REPLACE instead of APPEND.
- **Fix**: Remove _is_contradiction or make it a no-op until Phase 3 LLM classification.

---

## Medium Issues (Fix Before Phase 3)

### Integration
- M1. WriteRouter, MemoryExtractor, BetaConfidence all fully implemented but never imported by engine
- M2. Three separate `generate_name` implementations with different stripping logic (engine:74, router:120, extractor:28)
- M3. list_nodes() returns `list[dict]` not `list[MemoryNode]` — untyped at API boundary
- M4. `operation` parameter accepted by engine.write() but completely ignored

### Scoring
- M5. Active weights sum to 0.60 not 1.0 (3 of 6 signals used, no normalization)
- M6. Single-item scored list assigns "warm" instead of "hot"
- M7. Fixed BM25 sigmoid params (no query-length adaptation like Mem0)

### Lifecycle
- M8. `power_law_decay` returns >1.0 when strength>1.0 — violates [0,1] contract
- M9. No guard against negative time deltas (future last_accessed from clock skew)
- M10. Unbounded alpha/beta accumulation makes confidence increasingly rigid over time
- M11. `evaluate_predicates()` in StateMachine is dead code (actual logic in transitions.py)
- M12. Ebbinghaus implementation doesn't model spaced-repetition (static stability)
- M13. Asymmetric archival: DECIDED nodes wait 30d vs ACTIVE 14d; no auto ARCHIVED→EXPIRED

### Storage
- M14. file_path column in SQLite never populated (always NULL)
- M15. No PRAGMA busy_timeout — concurrent writes get immediate lock error
- M16. Reconcile is O(n) full re-upsert (performance concern at 10K nodes)
- M17. Duplicate `extract_wikilinks` in markdown.py (dead code; canonical version in graph.py)
- M18. MIT license attribution for GAAMA PPR should include full copyright notice

### Write
- M19. `classify()` never calls `has_ttl_pattern()` — TTL detection implemented but unused
- M20. Unicode normalization (NFC) not applied before hash
- M21. Internal whitespace not collapsed for hash comparison
- M22. BRANCH and PROMOTE operations fall through to generic Append handler

### Config/Model
- M23. No validation on numeric config fields (negative half_life, thresholds > 1.0 accepted)
- M24. No version field on MemoryNode for optimistic locking (spec mentions it)
- M25. strength field unbounded (spec says [1.0, 2.0])

---

## Low Issues (Address Opportunistically)

L1-L17: Dead Outcome dataclass, misleading outcome_count, hardcoded ln(2), content whitespace stripping on round-trip, FTS edge cases with long queries, abbreviation splitting, unused _sessions dir, no logging, timezone-naive risk from fromisoformat, etc.

---

## Fix Priority (Recommended Order)

### Immediate (before claiming Phase 2 "done"):
1. **Wire WriteRouter into engine.write()** — C1, C7, M4
2. **Wire MultiSignalScorer into engine.search()** — C2, C5
3. **Fix markdown.py error handler** — C6
4. **Add missing API stubs** — C4
5. **Fix weight naming** — C3

### Before Phase 3:
6. Unify generate_name → single function in write/extractor.py
7. Clamp power_law_decay output to [0, 1]
8. Add PRAGMA busy_timeout
9. Populate file_path in SQLite
10. Guard against negative time in compute_decay

---

## What's Done Well

- **Clean architecture**: No circular imports, strict layer separation
- **State machine**: Correct, complete, well-tested
- **PPR implementation**: Numerically stable, properly attributed
- **RRF implementation**: Correct per standard formula
- **BetaConfidence**: Good Phase 3 interface design
- **Atomic writes**: Correct tempfile + os.replace pattern (minus the error handler bug)
- **FTS5 setup**: Proper tokenizer, prefix indexes, BM25 scoring
- **Test coverage**: 177 tests covering all leaf modules
- **UTC consistency**: All datetime operations use timezone-aware UTC
