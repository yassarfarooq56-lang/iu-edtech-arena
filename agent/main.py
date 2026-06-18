"""EdTech Arena — Essay Grading Agent (GradeAssist)

Dual-model architecture: Opus orchestrates the grading workflow and adds
empathetic framing. Haiku scores each rubric criterion independently —
isolated scoring prevents halo bias and costs ~$0.001/call.

Flow: load_essay_batch → score_rubric_criterion (×5 per essay, Haiku)
    → generate_student_feedback (Haiku) → export_grade_summary
"""
from __future__ import annotations

import json
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

ORCHESTRATOR_MODEL = "claude-opus-4-8"
SCORER_MODEL = "claude-haiku-4-5"

SYSTEM = """\
You are GradeAssist, an AI teaching assistant that helps teachers grade
essays efficiently and fairly. You are grounded in evidence-based pedagogy.

## Workflow (follow this order)

1. If the teacher wants a custom rubric, call `customize_rubric` first.
   Otherwise use the default 5-criterion rubric.
2. Call `load_essay_batch` to get the essays.
3. For EACH essay, call `score_rubric_criterion` once per criterion.
   Each call is cheap (~$0.001 on Haiku). Do ALL criteria for one student
   before moving to the next.
4. After scoring all criteria for a student, call `generate_student_feedback`
   to compile a personalized feedback letter.
5. After ALL students are graded, call `suggest_revision_focus` for each
   student to give them a single, actionable priority.
6. Call `export_grade_summary` LAST for a class-wide report.

## Pedagogical framework

- Bloom's Taxonomy: note which cognitive level (remember → create) the
  student is operating at, and nudge them one level up.
- Growth mindset: use "yet" language — "Your thesis doesn't have specific
  evidence yet" not "Your thesis lacks evidence."
- Specificity: quote the student's own words when praising or suggesting
  changes. Vague feedback ("good job") is not actionable.
- Fairness: apply the same rubric standard to every essay. Score each
  criterion in isolation to prevent halo bias.
- Efficiency: the teacher's time is precious — save them hours, not minutes.
"""

RUBRIC_CRITERIA = [
    "Thesis & Argument — clarity, specificity, defensibility of the central claim",
    "Evidence & Support — relevance, quality, and integration of evidence",
    "Organization & Structure — logical flow, transitions, paragraph cohesion",
    "Language & Style — vocabulary, sentence variety, tone, grammar",
    "Critical Thinking — depth of analysis, counterarguments, originality",
]

SAMPLE_ESSAYS = [
    {
        "student": "Alex M.",
        "title": "Should School Start Later?",
        "text": (
            "I think school should start later because students are tired. "
            "Many students stay up late doing homework and then have to wake up "
            "at 6am. This is not good for their health. Studies show that "
            "teenagers need 8-10 hours of sleep. If school started at 9am "
            "instead of 7:30am, students would be more alert and learn better. "
            "Some people say it would mess up parents' work schedules, but I "
            "think student health is more important. In conclusion, schools "
            "should start later so students can sleep more and do better."
        ),
    },
    {
        "student": "Jamie L.",
        "title": "The Impact of Social Media on Teen Mental Health",
        "text": (
            "Social media has become an integral part of teenage life, with "
            "over 95% of teens reporting access to a smartphone (Pew Research, "
            "2023). While platforms like Instagram and TikTok offer connection "
            "and creative expression, mounting evidence suggests a troubling "
            "correlation between heavy social media use and declining mental "
            "health among adolescents. This essay argues that schools must "
            "implement digital literacy programs that teach students to engage "
            "critically with social media rather than banning it outright.\n\n"
            "The American Psychological Association's 2023 advisory highlights "
            "that social media's effects are not uniform — they depend on the "
            "individual's developmental stage, pre-existing vulnerabilities, "
            "and usage patterns. For instance, passive scrolling correlates "
            "with increased depression symptoms, while active engagement shows "
            "neutral or mildly positive effects (Thorisdottir et al., 2019). "
            "This nuance is critical: a blanket ban ignores that social media "
            "can be a lifeline for marginalized teens who find community "
            "online.\n\n"
            "However, the counterargument that teens can self-regulate is "
            "undermined by neuroscience. The prefrontal cortex, responsible "
            "for impulse control, is not fully developed until the mid-20s "
            "(Casey et al., 2008). Platforms engineered for engagement exploit "
            "this vulnerability through variable-ratio reinforcement schedules "
            "— the same mechanism that makes slot machines addictive. Schools "
            "therefore have a duty to scaffold students' digital decision-"
            "making.\n\n"
            "A digital literacy curriculum should include: media analysis, "
            "self-monitoring tools, and structured offline alternatives. Pilot "
            "programs in Finland and Australia showed a 23% reduction in "
            "problematic usage (OECD Education Working Paper, 2024).\n\n"
            "The question is not whether teens will use social media — they "
            "will. The question is whether we equip them to use it wisely."
        ),
    },
    {
        "student": "Sam K.",
        "title": "Why Dogs Are the Best Pets",
        "text": (
            "Dogs are the best pets ever. They are loyal and fun. My dog Buddy "
            "always greets me when I come home. He wags his tail and jumps on "
            "me. Dogs are better than cats because cats are lazy and don't care "
            "about you. Dogs can also do tricks like sit and roll over. My "
            "neighbor has a cat and it just sleeps all day. Dogs are also good "
            "for security because they bark at strangers. In conclusion dogs "
            "are the best pets because they are loyal fun and protective."
        ),
    },
]

TOOLS: list[dict] = [
    {
        "name": "customize_rubric",
        "description": (
            "Call this BEFORE grading if the teacher wants to use their own "
            "rubric criteria instead of the default 5. Replaces the active "
            "rubric for this session. Skip if the teacher is happy with the "
            "default (Thesis, Evidence, Organization, Language, Critical Thinking)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of rubric criteria, each as a short phrase "
                        "with description, e.g. 'Creativity — originality "
                        "of ideas and approach'"
                    ),
                },
            },
            "required": ["criteria"],
        },
    },
    {
        "name": "load_essay_batch",
        "description": (
            "Call this FIRST when the teacher asks to grade essays. Loads the "
            "student essays and rubric criteria from the class batch. In "
            "production this connects to an LMS (Canvas, Google Classroom)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {
                    "type": "string",
                    "description": "Name of the class or assignment",
                },
            },
            "required": [],
        },
    },
    {
        "name": "score_rubric_criterion",
        "description": (
            "Score ONE essay on ONE rubric criterion. Delegates to Haiku "
            "(fast, ~$0.001/call) so you can call it many times cheaply. "
            "Call once per criterion per essay: 5 criteria × 3 essays = 15 "
            "calls. Each criterion is scored in isolation to prevent halo bias."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_name": {
                    "type": "string",
                    "description": "Name of the student",
                },
                "essay_text": {
                    "type": "string",
                    "description": "Full essay text",
                },
                "criterion": {
                    "type": "string",
                    "description": "Rubric criterion to evaluate",
                },
            },
            "required": ["student_name", "essay_text", "criterion"],
        },
    },
    {
        "name": "generate_student_feedback",
        "description": (
            "Call AFTER scoring all 5 criteria for one student. Compiles the "
            "per-criterion scores into a personalized, constructive feedback "
            "letter. Uses Haiku for cost — you (Opus) add holistic framing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_name": {"type": "string"},
                "essay_title": {"type": "string"},
                "criterion_scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "criterion": {"type": "string"},
                            "score": {"type": "integer"},
                            "justification": {"type": "string"},
                        },
                    },
                    "description": "Scores from score_rubric_criterion calls",
                },
            },
            "required": ["student_name", "essay_title", "criterion_scores"],
        },
    },
    {
        "name": "suggest_revision_focus",
        "description": (
            "Call AFTER generating feedback for a student. Analyzes their "
            "scores to identify the ONE thing they should work on first. "
            "Uses Haiku to produce a 2-sentence actionable priority. "
            "Helps students avoid overwhelm by focusing on highest-leverage fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_name": {"type": "string"},
                "essay_title": {"type": "string"},
                "criterion_scores": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "criterion": {"type": "string"},
                            "score": {"type": "integer"},
                            "justification": {"type": "string"},
                        },
                    },
                    "description": "Scores from the scoring step",
                },
            },
            "required": ["student_name", "essay_title", "criterion_scores"],
        },
    },
    {
        "name": "export_grade_summary",
        "description": (
            "Call LAST, after all essays are graded and feedback generated. "
            "Produces a class-wide summary: score distributions, common "
            "weaknesses, and teaching recommendations. Helps the teacher "
            "plan targeted instruction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "class_name": {"type": "string"},
                "grade_reports": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "student_name": {"type": "string"},
                            "overall_score": {"type": "number"},
                            "criterion_scores": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "criterion": {"type": "string"},
                                        "score": {"type": "integer"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "required": ["class_name", "grade_reports"],
        },
    },
]

grade_reports: dict[str, dict] = {}
active_rubric: list[str] = list(RUBRIC_CRITERIA)


def _parse_json_safe(text: str) -> dict:
    """Extract JSON from Haiku responses that may include markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"score": 5, "justification": text}


def run() -> None:
    client = anthropic.Anthropic()
    history: list[dict] = []

    print("\n─" * 58)
    print("  GradeAssist — AI Essay Grading Agent")
    print("  Grade a batch of essays with rubric-aligned feedback.")
    print("  Type 'grade my essays' to start, or describe your task.")
    print("─" * 58 + "\n")

    user = input("👩‍🏫 ").strip()
    if not user:
        return
    history.append({"role": "user", "content": user})

    while True:
        resp = client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=TOOLS,
            thinking={"type": "adaptive"},
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type == "text":
                print(f"\n🤖 {block.text}\n")
            elif block.type == "tool_use":
                print(f"   ⚙️  {block.name}...")
                result = handle_tool(client, block.name, block.input)
                history.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }],
                })

        if resp.stop_reason != "tool_use":
            user = input("👩‍🏫 ").strip()
            if not user:
                return
            history.append({"role": "user", "content": user})


def handle_tool(client: anthropic.Anthropic, name: str, args: dict) -> str:
    if name == "customize_rubric":
        active_rubric.clear()
        active_rubric.extend(args["criteria"])
        return json.dumps({
            "status": "rubric_updated",
            "criteria": active_rubric,
            "count": len(active_rubric),
        })

    if name == "load_essay_batch":
        return json.dumps({
            "essays": [
                {"student": e["student"], "title": e["title"], "text": e["text"]}
                for e in SAMPLE_ESSAYS
            ],
            "count": len(SAMPLE_ESSAYS),
            "rubric_criteria": active_rubric,
            "note": "3 essays of varying quality for demonstration",
        })

    if name == "score_rubric_criterion":
        resp = client.messages.create(
            model=SCORER_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "You are a rubric scorer. Score the essay on the given "
                    "criterion from 1–10. Respond with ONLY a JSON object:\n"
                    '{"score": <int 1-10>, "justification": "<2 sentences, '
                    'quote student text>"}'
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Criterion: {args.get('criterion', args.get('rubric_criterion', 'General Quality'))}\n\n"
                    f"Essay by {args.get('student_name', 'Unknown')}:\n{args.get('essay_text', '')}"
                ),
            }],
        )
        raw = resp.content[0].text
        parsed = _parse_json_safe(raw)
        return json.dumps(parsed)

    if name == "generate_student_feedback":
        resp = client.messages.create(
            model=SCORER_MODEL,
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": (
                    "Write a short feedback letter (3 paragraphs) to the student. "
                    "Start with strengths. Frame weaknesses as concrete next steps. "
                    "Quote their text. Be warm but honest."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Student: {args['student_name']}\n"
                    f"Essay: \"{args['essay_title']}\"\n"
                    f"Scores:\n{json.dumps(args['criterion_scores'], indent=2)}"
                ),
            }],
        )
        feedback = resp.content[0].text
        scores = args["criterion_scores"]
        avg = sum(s.get("score", 0) for s in scores) / max(len(scores), 1)
        grade_reports[args["student_name"]] = {
            "overall_score": round(avg, 1),
            "criterion_scores": scores,
        }
        return feedback

    if name == "suggest_revision_focus":
        resp = client.messages.create(
            model=SCORER_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "You are a writing coach. Given a student's rubric scores, "
                    "identify their SINGLE highest-leverage improvement. Respond "
                    "in exactly 2 sentences: what to focus on and one concrete "
                    "action they can take on their next draft. Use growth-mindset "
                    "language ('yet', 'next step')."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Student: {args['student_name']}\n"
                    f"Essay: \"{args['essay_title']}\"\n"
                    f"Scores:\n{json.dumps(args['criterion_scores'], indent=2)}"
                ),
            }],
        )
        return resp.content[0].text

    if name == "export_grade_summary":
        reports = args.get("grade_reports", [])
        if not reports:
            return json.dumps({"error": "No reports provided"})
        scores = [r["overall_score"] for r in reports]
        return json.dumps({
            "class": args.get("class_name", "Unknown"),
            "students_graded": len(reports),
            "average_score": round(sum(scores) / len(scores), 1),
            "highest": max(scores),
            "lowest": min(scores),
            "per_student": [
                {"student": r["student_name"], "score": r["overall_score"]}
                for r in reports
            ],
        }, indent=2)

    return f"(tool {name!r} not implemented)"


if __name__ == "__main__":
    run()
