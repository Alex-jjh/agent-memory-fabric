# Agent Memory Fabric (AMF)

**A lifecycle-aware memory system for LLM agents with discrete state machines, proactive retrieval, and user transparency.**

---

## Status

| Component | Status |
|-----------|--------|
| Research & Literature Review | Done (40+ papers, 15 systems analyzed) |
| System Design | Done (10 components x 4 layers) |
| Paper 1 Experimental Design | Done (Claude Code clone baseline + state machine treatment) |
| Implementation | Not started (Phase 1 target: Sep 2026) |
| Paper 1 Writing | Not started (CHI 2027 LBW target: Jan 2027) |

## One-Line Summary

AMF adds discrete lifecycle state machines (Active/Decided/Archived/Expired) to agent memory — making forgetting an explicit architectural decision rather than an emergent property of decay functions.

## Key Research Gap

Analyzed 15 real systems' source code (3 industrial + 12 open-source). **Zero** implement discrete lifecycle state machines with explicit transition predicates. CortexGraph (closest prior art) uses continuous power-law decay; AMF proposes semantically meaningful states with per-state write semantics.

## Paper 1

**Title**: "Let Agents Forget: A Lifecycle State Machine for Memory Management in LLM Agents"

**Design**: Control (Claude Code-style proactive + dedup extraction, no lifecycle) vs Treatment (same + state machine). Optional third condition: CortexGraph-style continuous decay.

**Target**: CHI 2027 LBW / NeurIPS Workshop

## Architecture

```
┌──── Layer 4: User / Interaction ───────────────────────────────────┐
│  Transparency & Control (Obsidian plugin: state badges, graph view) │
└────────────────────────────────────────────────────────────────────┘
┌──── Layer 3: Write / Decision ─────────────────────────────────────┐
│  Write Semantics Router (Replace/Append/Synthesize/Expire/Branch)   │
│  Dual-Stream (fast append + async consolidation)                    │
└────────────────────────────────────────────────────────────────────┘
┌──── Layer 2: Read / Retrieval ─────────────────────────────────────┐
│  Proactive Retrieval Gateway (<100ms, intent-aware)                 │
│  Multi-Signal Scorer (semantic + graph + hierarchy + decay + freq)  │
└────────────────────────────────────────────────────────────────────┘
┌──── Layer 1: Storage / Organization ───────────────────────────────┐
│  Graph (KG topology) │ State Machine │ Vector Index │ Tiered Memory │
└────────────────────────────────────────────────────────────────────┘
```

## Repository Structure (Planned)

```
agent-memory-fabric/          <- this repo (open-source product)
  core/                       Python core engine
  obsidian-plugin/            TypeScript Obsidian plugin
  docs/                       User documentation

amf-experiments/              <- separate repo (research)
  baselines/                  Comparison systems
  ablations/                  Ablation experiments
  datasets/                   LoCoMo, LongMemEval processing

let-agents-forget-paper/      <- separate repo (LaTeX)
```

## Research Documents

All design discussion and research synthesis lives in `discussion-files/`:

| # | File | Content |
|---|------|---------|
| 00 | research-landscape-v1 | V1 literature review (read path focus) |
| 01 | research-log | Core findings + original insights + state machine model |
| 02 | deep-research-prompt-v2 | Write path deep research prompt |
| 03 | brennan-meeting-prep | Supervisor discussion handbook (architecture + case studies + 12-system findings) |
| 04 | project-plan | Dual-track plan (engineering + papers + timeline + competitive landscape) |
| 05 | reference-sources | Complete reference index (18 open-source + 3 closed-source + 7 paper-only) |
| 06 | agentcore-comparison | AgentCore Memory deep comparison |
| 07 | quick-memory-analysis | Quick Desktop memory system analysis |
| 08 | multi-project-scope | Multi-project memory scoping design |
| 09 | reference-systems-deep-dive | Hermes / OpenClaw / Claude Code source code comparison |

## Key Differentiators (vs 15 analyzed systems)

| Feature | AMF | Nearest Competitor |
|---------|-----|-------------------|
| Discrete lifecycle states | Active/Decided/Archived/Expired | None (CortexGraph has continuous decay) |
| Write semantics taxonomy | 6 typed operations, tracked per-write | None (Mem0 V3 is ADD-only) |
| Proactive injection | Intent-aware gateway <100ms | CortexGraph (spaced repetition) |
| Knowledge graph for lifecycle | Graph informs state transitions | None (graphs used only for retrieval) |
| User transparency | Obsidian state badges + graph color-coding | basic-memory (Markdown files, no lifecycle viz) |

## Timeline

- **Jun-Aug 2026**: Research + system design with supervisor Brennan
- **Sep 2026**: FYP starts + Phase 1 (foundation)
- **Oct 2026**: Phase 2 (lifecycle engine) + experiments setup
- **Nov-Dec 2026**: Ablation experiments + Paper 1 writing
- **Jan 2027**: Submit CHI 2027 LBW + Phase 3 (retrieval)
- **Feb-Mar 2027**: Phase 4 (UI) + user study
- **Apr-May 2027**: FYP defense + open-source launch

## FYP

- **Course**: SAT301 (2026-2027)
- **Supervisor**: Brennan Jones
- **Institution**: XJTLU

---

*Not yet accepting contributions. Will open up after initial implementation (Q4 2026).*
