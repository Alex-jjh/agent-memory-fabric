# STALE Benchmark Integration

## Paper

**"STALE: Detecting Staleness in LLM Agent Memory"**
- arXiv: 2605.06527 (published 2026-05-15)
- Key finding: Even frontier LLMs only achieve 55.2% accuracy on implicit contradiction detection

## Dataset Status

As of 2026-05-20, the dataset may not yet be publicly released. Check:
- HuggingFace: https://huggingface.co/datasets (search "STALE")
- Paper authors' GitHub (check paper for links)
- OpenReview (if submitted to a venue)

## When Dataset is Available

Place it at:
```
benchmarks/data/stale/
```

Expected format (from paper description):
- Pairs of (old_memory, new_information)
- Labels: contradicts / does_not_contradict
- Categories: explicit contradiction, implicit contradiction (state update), temporal update

## Mock Data

`mock_stale.py` generates 50 synthetic pairs (25 true contradictions + 25 non-contradictions)
for pipeline testing while awaiting the real dataset.

## Running

```bash
# With mock data
python -m benchmarks.stale.run_stale

# With real data (when available)
python -m benchmarks.stale.run_stale --data benchmarks/data/stale/test.json
```

## Metrics

- **TDA (True Detection Accuracy)**: Overall accuracy
- **TPR (True Positive Rate)**: Fraction of real contradictions detected
- **FPR (False Positive Rate)**: Fraction of non-contradictions incorrectly flagged
- **TNR (True Negative Rate)**: Fraction of non-contradictions correctly passed
- **FNR (False Negative Rate)**: Fraction of real contradictions missed
