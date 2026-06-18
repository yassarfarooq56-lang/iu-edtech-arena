# GradeAssist — Strategy & Plan

## The Problem We're Solving

Teachers spend 5+ hours/week grading essays. Students get generic, delayed feedback that doesn't help them improve. We're building an AI agent that grades a batch of essays with rubric-aligned, personalized feedback — saving teacher time while giving students better guidance.

## Target Learner

Any student who submits written work (essays, reports, reflections) and currently receives only a letter grade or a one-line comment like "good job."

## Architecture Strategy

### Dual-Model Design (the core insight)

| Model | Role | Cost | Why |
|-------|------|------|-----|
| **Opus** | Orchestrator — manages the grading workflow, applies Bloom's Taxonomy + growth-mindset framing, coordinates all 6 tools | ~$0.10/batch | Needs deep reasoning to coordinate tools and synthesize holistic commentary |
| **Haiku** | Scorer + feedback writer — evaluates each rubric criterion independently, generates feedback letters and revision priorities | ~$0.001/call | Fast, cheap, and isolated scoring prevents halo bias (one criterion doesn't influence another) |

### Tool Pipeline (6 tools, strict ordering)

1. **`customize_rubric`** *(optional)* — Teacher sets custom rubric criteria. Skipped if the default 5-criterion rubric fits. Supports any assignment type.
2. **`load_essay_batch`** — Load essays from the class (simulates LMS integration: Canvas, Google Classroom).
3. **`score_rubric_criterion`** — Score ONE essay on ONE criterion via Haiku. Called N× per essay (one per rubric dimension). Isolated calls prevent halo bias.
4. **`generate_student_feedback`** — Compile all criterion scores into a personalized feedback letter. Quotes the student's text, frames weaknesses as concrete next steps using growth-mindset language.
5. **`suggest_revision_focus`** — Distills scores into ONE actionable priority per student. Prevents overwhelm by focusing on the highest-leverage improvement.
6. **`export_grade_summary`** — Class-wide summary: score distributions, common weaknesses, teaching recommendations for targeted instruction.

### Pedagogical Framework (baked into the system prompt)

- **Bloom's Taxonomy** — identify which cognitive level the student operates at, nudge them one level up
- **Growth mindset** — "yet" language ("Your thesis doesn't have specific evidence *yet*")
- **Specificity** — quote the student's own words when praising or critiquing
- **Fairness** — same rubric standard for every essay, isolated criterion scoring

### Default Rubric Dimensions

1. Thesis & Argument
2. Evidence & Support
3. Organization & Structure
4. Language & Style
5. Critical Thinking

### Robustness

- `_parse_json_safe()` handles Haiku responses wrapped in markdown fences or malformed JSON — graceful fallback instead of crash.
- Prompt caching (`cache_control: ephemeral`) on all system prompts across both models.

## Economics (how it scales to 1M students)

- 30 essays × 5 criteria = 150 Haiku calls → **$0.15**
- 30 feedback letters (Haiku) → **$0.06**
- 30 revision focus calls (Haiku) → **$0.03**
- 1 Opus orchestration → **$0.10**
- **Total: ~$0.34/class, ~1¢ per student**
- Batches API cuts async grading by 50%
- Prompt caching keeps system prompts near-free across turns

## Why This Gets Better With Smarter Models

- Better models → more nuanced feedback (catching subtle logical gaps, style issues)
- Better models → cross-essay pattern detection (class-wide misconceptions)
- Better models → real-time writing coaching (not just post-hoc grading)
- Better models → multi-modal grading (handwritten essays via vision)
- Better models → deeper Bloom's Taxonomy analysis (recognizing implicit reasoning)

## What We Built

- [x] Dual-model agent with Opus orchestration + Haiku scoring
- [x] 6 well-designed tools with clear "when to call" descriptions
- [x] Custom rubric support (`customize_rubric` tool)
- [x] Per-student revision priorities (`suggest_revision_focus` tool)
- [x] Bloom's Taxonomy + growth-mindset pedagogical framework
- [x] Robust JSON parsing for Haiku responses
- [x] Prompt caching on all system prompts
- [x] 3 sample essays of varying quality for demonstration
- [x] PITCH.md under 150 words

## What We'd Add With More Time

- LMS integration (Canvas API, Google Classroom API)
- Parallel scoring with `asyncio` (score all criteria simultaneously)
- Student progress tracking across assignments (memory)
- Plagiarism detection as an additional tool
- Batch API integration for overnight grading of large classes
- Multi-modal support (grading handwritten essays via vision)
