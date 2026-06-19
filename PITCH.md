# Team: I-me-myself

## Problem
University STEM students get wrong answers but don't know WHERE their reasoning broke. Lectures can't personalize, TAs have 200 students each, and textbooks show the right path — not where the student's path diverged. The learner: any STEM student stuck on a problem with no one to diagnose their specific confusion.

## Approach
MisconceptionDebugger is a **cognitive debugger** — it finds the exact concept where understanding breaks, then provides the minimal fix. A diagnostic loop (not a pipeline): `diagnose_misconception` calls Opus to reason about the student's thinking, `generate_probe` (Haiku) creates targeted questions to confirm the hypothesis, `update_cognitive_map` tracks knowledge state as persistent memory (zero-cost local calls), and `generate_scaffold` (Haiku) delivers the smallest hint that unblocks progress. Socratic method throughout — never gives answers.

## Why it scales
Opus fires once per misconception (~$0.03). Everything else is Haiku (~$0.001/call). Typical session: 1 Opus diagnosis + 4 Haiku calls = **~$0.035/session, ~3.5 cents/student**. Context summarization compresses old turns after 20 messages, cutting token costs ~80%. Cognitive maps are ~200 tokens of structured data vs ~2000+ of raw history.
