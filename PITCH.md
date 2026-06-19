# Team: I-me-myself

## Problem
First-year physics students fail not because they can't do math, but because they hold wrong mental models they can't identify. Lectures can't personalize, TAs have 200 students each, and textbooks show the right path — not where the student's path diverged. The learner: any first-year physics student stuck on a problem with no one to diagnose their specific confusion.

## Approach
MisconceptionDebugger is a **cognitive debugger** with a diagnostic loop (not a pipeline). `diagnose_misconception` is the only Opus call — it reasons about the student's thinking to find the root misconception AND the missing prerequisite. Everything else runs on Haiku: `generate_probe` creates discriminating questions, `generate_scaffold` delivers minimal hints, `verify_understanding` checks resolution. Three zero-cost local tools manage a **persistent cognitive map** with prerequisite tracking — the memory system. `suggest_next_concept` navigates the prerequisite graph to find the optimal next topic.

## Why it scales
**Haiku orchestrates** at $0.002/turn (not Opus at $0.03 — 15× cheaper). Opus fires only for diagnosis: 1-2 calls/session. Typical session: ~$0.04. At 1M students: **~$40K/month**. Context summarization after 20 turns cuts tokens ~80%. Cognitive maps are ~200 tokens vs ~2000+ raw history.
