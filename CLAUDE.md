# EdTech Arena — context for Claude Code

You are helping a team in a 60-minute hackathon. They are building an AI agent
that solves an education problem — `README.md` has examples for inspiration.

## What matters

The judge scores on **Impact**, **Architecture**, **Economics**, and
**Ambition** by reading the code and `PITCH.md` — runtime output is not
evaluated. Help the team make the *design* legible: clear system prompts,
well-named tools with good descriptions, sensible model choices, and a tight
PITCH.md.

## Ground rules

- Work inside `agent/`. The entry point is `agent/main.py`.
- Use the Anthropic Python SDK (`anthropic`). Default model `claude-opus-4-8`;
  use `claude-haiku-4-5` where latency/cost is the lesson.
- Adaptive thinking: `thinking={"type": "adaptive"}`. Never `budget_tokens`.
- Tools are dicts with `name`, `description`, `input_schema` — make the
  descriptions explain *when* to call the tool, not just what it does.
- Don't gold-plate. 60 minutes. Ship the idea, not the framework.

## When the team asks "what should we build"

Point them at the examples in `README.md` for inspiration, ask which learner
they care about, then sketch the smallest agent loop that demonstrates the
idea. One good tool beats five stubbed ones.

## Before they push

Make sure `PITCH.md` is filled in — an empty pitch scores zero on Impact.
