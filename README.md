# 🎓 EdTech Arena — Build an Education Agent in 60 Minutes

**IU Tech Conference 2026 · Anthropic Workshop · Thu 18 June, 16:00–17:00**

You have one hour, one API key, and Claude Code. Build an AI agent that moves
the needle on a real education problem. Push your branch. Claude judges every
entry live on the big screen.

## The rules

1. Form a team of 2–4. Pick a name.
2. Clone this repo and branch: `git checkout -b team-<your-name>`
3. Choose an education problem — see below for examples.
4. Build your agent in `agent/`. Use Claude Code — that's the point.
5. Fill in `PITCH.md` (≤150 words).
6. **Push your branch by 16:55.** Last commit before the bell counts.
7. Watch the leaderboard.

Prizes for the top 3 teams. Claude is the only judge.

## Example problems

These are starting points, not a menu — bring your own if you have one. The
only rule is that it's an **education** problem with a real learner.

| | Example | Hint: which primitive shines |
|---|---|---|
| 1 | A tutor that adapts to a dyslexic 12-year-old learning fractions | memory, multi-turn |
| 2 | Dropout early-warning agent that drafts intervention messages | tool use, structured output |
| 3 | Multilingual STEM tutor for refugee students with interrupted schooling | system prompts, subagents |
| 4 | Teacher-workload agent: grade 30 essays + personalised feedback | batch / parallel calls |
| 5 | Adult-literacy coach that works over SMS (160 chars, no emoji) | token discipline, Haiku |
| 6 | Accessibility agent: make a physics chapter usable for a blind student | vision → text, tool use |
| 7 | Curriculum-gap detector: read a student's chat history, find the misconception | long context, reasoning |

## What "build an agent" means

The skeleton in `agent/main.py` is a working-but-useless tutor loop. Your job
is to make it *good* at your problem. Some directions:

- Rewrite the system prompt for your learner
- Add tools (`search_curriculum`, `save_progress`, `send_sms`, …)
- Add memory across turns
- Spawn subagents for parallel work
- Pick the right model for the job (Opus for reasoning, Haiku for speed/cost)
- Go full Managed Agents (CMA) if you're feeling brave —
  https://platform.claude.com/docs/en/managed-agents/overview

The judge reads your **code** and your **PITCH.md** — not your runtime output.
Show your thinking in the code.

## How you're scored (0–100 each, total out of 400 wins)

| Criterion | Judge lens |
|---|---|
| **Impact** — does a real learner end up better off? Be specific about who and how. | The Educator |
| **Architecture** — the agent-design choices *you* control: tool definitions, system prompt, memory, model selection, subagent topology. Managed Agents handles the sandbox — don't reinvent it. | The Engineer |
| **Economics** — cost per learner at scale. Model tier, caching, batching, context discipline. The infra scales for free; the bill doesn't. | The Economist |
| **Ambition** — does this get *disproportionately better* as models get smarter? Aim where AI is going, not where it is. | The Futurist |

## Setup

Your Anthropic Console org has been loaded with credits for the workshop.
Create an API key at https://console.anthropic.com/settings/keys, then:

```sh
git clone <this-repo>
cd iu-edtech-arena
git checkout -b team-<your-name>
python3 -m venv .venv && source .venv/bin/activate
pip install -r agent/requirements.txt
cp agent/.env.example agent/.env   # then paste your key into agent/.env
python agent/main.py               # prove it runs, then start hacking
```

On Windows, activate with `.venv\Scripts\activate` instead.

`.env` is git-ignored — your key won't end up in your branch. Use HTTPS for
the remote (port 443) — conference wifi may block SSH.
