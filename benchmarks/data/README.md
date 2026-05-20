# Benchmark Data

## LoCoMo Dataset

Download from: https://github.com/snap-research/locomo

```bash
cd benchmarks/data/
git clone --depth=1 https://github.com/snap-research/locomo locomo-raw
```

Expected structure after download:
```
data/
└── locomo-raw/
    └── data/
        ├── test.json      # 10 sessions, ~50 conversations each
        └── ...
```

## Data Format (LoCoMo)

Each session contains:
- `conversation`: list of turns (speaker + utterance)
- `questions`: list of QA pairs with:
  - `question`: the query
  - `answer`: gold answer
  - `evidence`: supporting conversation turns
  - `category`: type (single-hop, multi-hop, temporal, etc.)

## LongMemEval Dataset

Download from: https://github.com/xiaowu0162/LongMemEval

```bash
git clone --depth=1 https://github.com/xiaowu0162/LongMemEval locomo-raw/longmemeval
```
