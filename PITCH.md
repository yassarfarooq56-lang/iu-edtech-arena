# Team: I-me-myself

## Problem
Teachers spend 5+ hours/week grading essays. Students get vague feedback too late to act on. The learner: every student who submits writing and deserves specific, growth-oriented guidance — not just a letter grade.

## Approach
GradeAssist uses a **dual-model architecture**. Opus orchestrates the workflow using Bloom's Taxonomy and growth-mindset framing; Haiku scores each rubric criterion independently to prevent halo bias (~$0.001/call). Six tools form a pipeline: `customize_rubric` lets teachers set criteria, `score_rubric_criterion` calls Haiku per-criterion, `generate_student_feedback` compiles personalized letters quoting the student's own words, and `suggest_revision_focus` distills one actionable priority per student. Prompt caching keeps system-prompt costs near zero.

## Why it scales
30 essays × 5 criteria = 150 Haiku calls ($0.15) + 30 feedback letters ($0.06) + 1 Opus call ($0.10) = **$0.31/class, ~1 cent/student**. Batches API halves async costs. At 1M students: ~$10K/month — less than one TA.
