# 🎓 EdTech Arena — Build an Education Agent in 60 Minutes

**IU Tech Conference 2026 · Anthropic Workshop · Thu 18 June, 16:00–17:00**

You have one hour, one API key, and Claude Code. Build an AI agent that moves
the needle on a real education problem. Push your branch. Claude judges every
entry live on the big screen.

## The rules

1. Form a team of 2–4. Pick a name.
2. Clone this repo and branch: `git checkout -b team-<your-name>`
3. Pick **one** problem from the list below (or bring your own).
4. Build your agent in `agent/`. Use Claude Code — that's the point.
5. Fill in `PITCH.md` (≤150 words).
6. **Push your branch by 16:55.** Last commit before the bell counts.
7. Watch the leaderboard.

Prizes for the top 3 teams. Claude is the only judge.

## Pick a problem

| # | Problem | Hint: which primitive shines |
|---|---|---|
| 1 | A tutor that adapts to a dyslexic 12-year-old learning fractions | memory, multi-turn |
| 2 | Dropout early-warning agent that drafts intervention messages | tool use, structured output |
| 3 | Multilingual STEM tutor for refugee students with interrupted schooling | system prompts, subagents |
| 4 | Teacher-workload agent: grade 30 essays + personalised feedback | batch / parallel calls |
| 5 | Adult-literacy coach that works over SMS (160 chars, no emoji) | token discipline, Haiku |
| 6 | Accessibility agent: make a physics chapter usable for a blind student | vision → text, tool use |
| 7 | Curriculum-gap detector: read a student's chat history, find the misconception | long context, reasoning |

Or pitch your own — but it must be an **education** problem.

## What "build an agent" means

The skeleton in `agent/main.py` is a working-but-useless tutor loop. Your job
is to make it *good* at your chosen problem. Some directions:

- Rewrite the system prompt for your learner
- Add tools (`search_curriculum`, `save_progress`, `send_sms`, …)
- Add memory across turns
- Spawn subagents for parallel work
- Pick the right model for the job (Opus for reasoning, Haiku for speed/cost)
- Go full Managed Agents (CMA) if you're feeling brave —
  https://platform.claude.com/docs/en/managed-agents/overview

The judge reads your **code** and your **PITCH.md** — not your runtime output.
Show your thinking in the code.

## How you're scored (1–10 each)

| Criterion | Judge persona |
|---|---|
| **Impact** — does this actually help the learner? | The Educator |
| **Architecture** — smart use of agent primitives (tools, memory, subagents, model choice) | The Engineer |
| **Scalability** — would this work for 1M students without bankrupting IU? | The Economist |
| **Creativity** — would IU actually ship this? | All three |

## Setup

```sh
git clone <this-repo>
cd iu-edtech-arena
git checkout -b team-<your-name>
pip install -r agent/requirements.txt
export ANTHROPIC_API_KEY=<the key on your card>
python agent/main.py   # prove it runs, then start hacking
```

Use HTTPS for the remote (port 443) — conference wifi may block SSH.

## Fallback: can't push?

Paste your `PITCH.md` and a gist link into the form on the screen. We'll pull
it in manually.

Good luck. 🚀
