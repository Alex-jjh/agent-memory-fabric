# Microsoft STATE-Bench (placeholder)

## Paper / Source

**"STATE: A Benchmark for Evaluating State Tracking in LLM-Based Agents"**
- Blog: https://www.microsoft.com/en-us/research/blog/ (search STATE-Bench)
- Potential GitHub: https://github.com/microsoft/OdysseyBench (may include this)
- Status: Not yet publicly available as of 2026-05-20

## What STATE-Bench Evaluates

From the blog description, STATE-Bench tests:
- Agent ability to track changing user states over extended conversations
- Detection of state updates (moved cities, changed jobs, completed tasks)
- Resistance to hallucinating state changes that didn't happen
- Temporal ordering of state transitions

## Relevance to AMF Paper 1

STATE-Bench directly tests our lifecycle state machine's core capability:
- Can the system correctly detect when a fact transitions from Active → Archived?
- Does it correctly preserve facts that are old but still valid?
- Does it handle implicit vs explicit state changes?

## Integration Plan (when available)

1. Download dataset to `benchmarks/data/state-bench/`
2. Create `benchmarks/state_bench/loader.py` — adapt format to our `StalePair` model
3. Run via: `python -m benchmarks.state_bench.run_state_bench`
4. Compare against STALE results (different angle on same problem)

## For Now

Using the STALE mock benchmark (`benchmarks/stale/`) for contradiction detection
evaluation. STATE-Bench will be added when the dataset is publicly released.
