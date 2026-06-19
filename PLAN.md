# MisconceptionDebugger — Strategy & Plan

## What Went Wrong (v1: GradeAssist)

### Impact (~20/100)
- Vague learner ("every student who submits writing")
- Hardcoded sample essays — not a real tool, just a constant
- Teacher-facing, not learner-facing. The student never interacts with the agent
- No adaptive behavior

### Architecture (~25/100)
- No memory — agent forgets everything between turns
- No subagent topology — one agent loop calling Haiku is a wrapper, not architecture
- Thin tools: `load_essay_batch` returns a constant, `customize_rubric` swaps a list
- No structured output — relied on `_parse_json_safe` hack
- Redundant tools doing the same thing (Haiku summarizes scores)

### Economics (~20/100)
- Calculated costs in PITCH.md but code implements zero optimization
- Unbounded context window — `history` grows forever
- Full essay text sent 5× per essay (once per criterion)
- No model routing logic — always same model for same task

### Ambition (~10/100)
- Essay grading is the #1 most common AI+education demo. Zero novelty
- Better models → slightly better scores (linear, not exponential)
- No theory of mind — agent doesn't reason about WHY
- No forward-looking architecture

---

## The Fix: Adaptive Misconception Debugger

### Core Concept
A "debugger for student thinking." Like a code debugger finds the exact line where code breaks, this finds the exact concept where understanding breaks.

### Specific Learner
University STEM students who get wrong answers but don't know WHERE their reasoning went wrong. Underserved because lectures can't personalize, TAs have 200 students each, and textbook answers show the right path but not where the student's path diverged.

### Subagent Topology

```
Orchestrator (Opus) — manages the diagnostic loop
  ├── Diagnostician (Opus)  — reasons about WHY the student is wrong
  ├── Probe Generator (Haiku) — generates targeted diagnostic questions
  ├── Scaffolder (Haiku)    — creates minimal interventions
  └── Verifier (Haiku)      — checks if misconception was resolved
  
Memory (local, zero-cost):
  ├── update_cognitive_map  — record what's learned about the student
  └── get_cognitive_map     — read full knowledge state
```

### Tool Pipeline (diagnostic LOOP, not linear)

| Tool | Model | Cost | Purpose |
|------|-------|------|---------|
| `diagnose_misconception` | Opus | ~$0.03 | Deep reasoning about student's wrong mental model |
| `generate_probe` | Haiku | ~$0.001 | Targeted question to confirm/refute hypothesis |
| `update_cognitive_map` | None (local) | $0 | Persist knowledge state — the memory system |
| `get_cognitive_map` | None (local) | $0 | Read student's full cognitive map |
| `generate_scaffold` | Haiku | ~$0.001 | Minimal intervention — analogy, counter-example, leading question |
| `verify_understanding` | Haiku | ~$0.001 | Check if misconception was resolved |

### Memory System
```python
cognitive_maps = {
    "student_id": {
        "concepts": {
            "energy_conservation": {"status": "mastered", "evidence": "...", "updated_at": "..."},
            "vector_decomposition": {"status": "misconception", "evidence": "...", "updated_at": "..."},
        },
        "misconceptions": [
            {"concept": "vector_decomposition", "detail": "confuses magnitude with component", "resolved": False}
        ],
        "session_summary": "..."
    }
}
```

### Context Management (Economics)
- `_summarize_history()`: After 20 turns, compresses old conversation via Haiku summary. Saves ~80% of context tokens
- Cognitive map is ~200 tokens of structured data vs ~2000+ of raw conversation
- Haiku calls capped at `max_tokens=256` — probes and verification don't need more
- Token usage printed per turn (stderr) for cost monitoring

### Pedagogical Framework
- **Socratic method**: questions, not lectures
- **Zone of Proximal Development** (Vygotsky): find the boundary of understanding
- **Productive struggle**: intervene only when truly stuck
- **Minimal intervention**: smallest hint that unblocks progress
- **Growth mindset**: "haven't connected yet" not "don't understand"
- **One misconception at a time**: fix the deepest root cause first

### Why This Gets Disproportionately Better With Smarter Models
- Misconception detection requires **theory of mind** — reasoning about WHY someone thinks what they think
- Today: catches surface errors (wrong formula, sign error)
- Smarter models: catches deep structural misunderstandings (confused causality, wrong analogies, missing connections between concepts)
- This is exponential because each improvement in reasoning-about-reasoning unlocks a new tier of misconceptions that couldn't be detected before
- Multi-modal future: analyze handwritten work, diagrams, lab photos

### Economics at Scale
- 1 Opus diagnosis + 4 Haiku calls = ~$0.035/session
- At 1M students: ~$35K/month
- Context summarization reduces long-session costs by ~80%
- Cognitive maps enable session-to-session continuity without replaying full history
