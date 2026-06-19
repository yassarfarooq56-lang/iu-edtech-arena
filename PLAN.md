# MisconceptionDebugger — Strategy & Architecture

## What Went Wrong (v1: GradeAssist) → What We Fixed

| Criterion | v1 Problem | v3 Fix |
|-----------|-----------|--------|
| **Impact** | Vague learner, hardcoded essays, no interaction | Specific learner (first-year physics), real-time Socratic interaction, prerequisite tracing |
| **Architecture** | No memory, no subagents, thin tools, linear pipeline | 7-tool diagnostic LOOP, cognitive map with prerequisite graph, 3 zero-cost local tools, Opus specialist subagent |
| **Economics** | Opus orchestrator ($0.03/turn), unbounded context, costs only in pitch | Haiku orchestrator ($0.002/turn, 15× cheaper), context summarization, per-session cost tracking |
| **Ambition** | Essay grading (commoditized), linear improvement | Misconception diagnosis (requires theory of mind), prerequisite graph navigation, exponential improvement thesis |

## Architecture

### Model Routing (the key economics decision)
```
ORCHESTRATOR = Haiku   → $0.002/turn  (conversation + tool dispatch)
SPECIALIST   = Opus    → $0.03/call   (misconception diagnosis ONLY)
FAST_MODEL   = Haiku   → $0.001/call  (probes, scaffolds, verification)
```

WHY Haiku orchestrates: tool dispatch is pattern-matching, not deep reasoning.
Opus at $0.03/turn × 10 turns × 1M students = $300K/month.
Haiku: $20K/month. Same quality for orchestration, 15× cheaper.

### Subagent Topology
```
Orchestrator (Haiku) — manages diagnostic loop
  ├── Diagnostician (Opus)          — WHY is the student wrong? ($0.03)
  ├── Probe Generator (Haiku)       — targeted diagnostic questions ($0.001)
  ├── Scaffolder (Haiku)            — minimal interventions ($0.001)
  ├── Verifier (Haiku)              — check resolution ($0.001)
  └── Memory (local, $0):
       ├── update_cognitive_map     — record knowledge state
       ├── get_cognitive_map        — read full state
       └── suggest_next_concept     — navigate prerequisite graph
```

### Tool Design (7 tools)

| # | Tool | Model | Cost | Architectural role |
|---|------|-------|------|--------------------|
| 1 | `diagnose_misconception` | Opus | $0.03 | Deep reasoning: root misconception + missing prerequisite |
| 2 | `generate_probe` | Haiku | $0.001 | Discriminating diagnostic question |
| 3 | `update_cognitive_map` | Local | $0 | Memory write: persist knowledge state |
| 4 | `get_cognitive_map` | Local | $0 | Memory read: full cognitive map |
| 5 | `generate_scaffold` | Haiku | $0.001 | Minimal intervention (analogy, counter-example, question) |
| 6 | `verify_understanding` | Haiku | $0.001 | Check if misconception resolved |
| 7 | `suggest_next_concept` | Local | $0 | Navigate prerequisite graph for optimal next topic |

Key design discipline: 3 tools are zero-cost local operations. Not every tool needs an API call.

### Memory System
```
cognitive_maps[student_id] = {
    concepts: {name → {status, evidence, updated_at}},
    prerequisites: {concept → depends_on},     ← NEW in v3
    misconceptions: [{concept, detail, resolved, attempts}],
    session_summary: "compressed history"
}
```

### Context Management
- `_summarize_history()`: after 20 turns, compress old turns via Haiku
- Saves ~80% of context tokens
- Cognitive map: ~200 tokens vs ~2000+ raw history
- Session summary stored in cognitive map for continuity

### Cost Tracking
Real-time per-session cost breakdown printed on exit:
- Orchestrator (Haiku) calls
- Diagnosis (Opus) calls  
- Tool (Haiku) calls
- Memory (local) calls
- Estimated USD total

### Pedagogical Framework
- **Socratic method**: questions, never lectures
- **Zone of Proximal Development** (Vygotsky): work at the knowledge boundary
- **Prerequisite tracing**: if the root cause is a missing prerequisite, fix THAT first
- **Minimal intervention**: smallest hint that unblocks progress
- **Growth mindset**: "haven't connected yet" language

### Why This Gets Exponentially Better
Misconception diagnosis requires **theory of mind** — reasoning about reasoning.

| Model capability | What becomes detectable |
|-----------------|------------------------|
| Current | Surface errors: wrong formula, sign error, unit mismatch |
| Next gen | Structural misconceptions: confused causality, wrong analogies |
| Future | Deep: implicit assumptions, cross-domain transfer failures, meta-cognitive gaps |

Each tier was previously UNDETECTABLE, not just harder. That's exponential.

### Economics at Scale
Typical session: 1 Opus + 4 Haiku + 3 local = **~$0.04/student**
At 1M students: **~$40K/month**
Context summarization reduces long sessions by ~80%
Prerequisite graph enables session-to-session continuity without replaying history
