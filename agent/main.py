"""EdTech Arena — Adaptive Misconception Debugger

A "debugger for student thinking." Finds the exact concept where a
student's understanding breaks, then provides the minimal intervention
to fix it.

Subagent topology:
  Orchestrator (Opus) — manages the diagnostic loop
    ├── Diagnostician (Opus)  — reasons about WHY the student is wrong
    ├── Probe Generator (Haiku) — generates targeted diagnostic questions
    ├── Scaffolder (Haiku)    — creates minimal interventions
    └── Verifier (Haiku)      — checks if misconception was resolved

Memory: persistent cognitive map tracks what each student knows,
misconceives, and has resolved — across the full session.

Economics: Opus fires only for deep diagnosis (~1 call per misconception).
Everything else runs on Haiku (~$0.001/call). Context window is managed
via conversation summarization after 20 turns.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

# --- Model routing: Opus for reasoning-about-reasoning, Haiku for everything else ---
ORCHESTRATOR_MODEL = "claude-opus-4-8"
FAST_MODEL = "claude-haiku-4-5"

# --- Pedagogically-grounded system prompt ---
SYSTEM = """\
You are MisconceptionDebugger, an AI tutor for university STEM students.
You don't explain solutions — you diagnose WHY a student is stuck and
provide the minimum intervention to unblock them.

## Your diagnostic loop

1. Listen to the student's problem or answer.
2. Call `diagnose_misconception` to hypothesize the root cause (uses Opus
   for deep reasoning about the student's thinking — this is the expensive
   call, use it deliberately).
3. Call `generate_probe` to ask a targeted question that confirms or
   refutes your hypothesis (uses Haiku — cheap, call freely).
4. Based on the student's response, either:
   a. Probe again (different angle) if uncertain, OR
   b. Call `update_cognitive_map` to record the confirmed misconception.
5. Call `generate_scaffold` to provide the MINIMAL hint that addresses
   the specific misconception (uses Haiku). Never give the full answer.
6. Call `verify_understanding` after the student tries again to check
   if the misconception is resolved (uses Haiku).
7. Call `update_cognitive_map` again to mark it resolved (or not).

You can call `get_cognitive_map` at any time to see the student's full
knowledge state and tailor your approach.

## Pedagogical principles

- Socratic method: ask questions that lead to insight. Never lecture.
- Zone of Proximal Development (Vygotsky): find the boundary between
  what they know and what they don't. Work right at that edge.
- Productive struggle: let them wrestle with it. Intervene only when
  they're stuck, not when they're thinking.
- Minimal intervention: the smallest hint that unblocks progress.
  "What happens to kinetic energy at the top of the arc?" not
  "Energy is conserved, so mgh = ½mv²..."
- Growth mindset: "You haven't connected these concepts yet" not
  "You don't understand energy conservation."
- One misconception at a time: fix the deepest one first. Surface
  errors often vanish when the root misconception is resolved.

## When NOT to use tools

Simple questions ("what's Newton's second law?") don't need the
diagnostic loop. Just answer directly. Save tool calls for moments
when the student is genuinely stuck or has a misconception to debug.
"""

# --- Memory: per-student cognitive map ---
cognitive_maps: dict[str, dict] = {}

CONTEXT_SUMMARY_THRESHOLD = 20


def _get_or_create_map(student_id: str = "default") -> dict:
    if student_id not in cognitive_maps:
        cognitive_maps[student_id] = {
            "student_id": student_id,
            "concepts": {},
            "misconceptions": [],
            "session_summary": "",
        }
    return cognitive_maps[student_id]


def _summarize_history(client: anthropic.Anthropic, history: list[dict]) -> list[dict]:
    """Compress old conversation turns to manage context window costs."""
    if len(history) <= CONTEXT_SUMMARY_THRESHOLD:
        return history

    old_turns = history[:-6]
    recent_turns = history[-6:]

    summary_text = ""
    for msg in old_turns:
        if isinstance(msg.get("content"), str):
            role = msg["role"]
            summary_text += f"{role}: {msg['content'][:200]}\n"

    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=256,
        system="Summarize this tutoring conversation in 3-4 sentences. Focus on: what topic, what misconceptions were found, what was resolved.",
        messages=[{"role": "user", "content": summary_text}],
    )
    summary = resp.content[0].text

    compressed = [
        {"role": "user", "content": f"[Earlier conversation summary: {summary}]"},
        {"role": "assistant", "content": "I have the context from our earlier discussion. Let's continue."},
    ]
    return compressed + recent_turns


# --- Tool definitions ---
TOOLS: list[dict] = [
    {
        "name": "diagnose_misconception",
        "description": (
            "Call when the student gives a wrong answer or shows confused "
            "reasoning. This is the EXPENSIVE call — it uses Opus to reason "
            "deeply about WHY the student thinks what they think. Returns a "
            "structured hypothesis: the concept, the misconception type, "
            "evidence from the student's words, and confidence level. "
            "Use deliberately — once per misconception, not every turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_work": {
                    "type": "string",
                    "description": "The student's answer, reasoning, or work that shows the error",
                },
                "problem_context": {
                    "type": "string",
                    "description": "The problem or topic being discussed",
                },
                "known_concepts": {
                    "type": "string",
                    "description": "What the student already understands (from cognitive map)",
                },
            },
            "required": ["student_work", "problem_context"],
        },
    },
    {
        "name": "generate_probe",
        "description": (
            "Call to generate a targeted diagnostic question that tests a "
            "specific hypothesis about the student's misconception. Uses "
            "Haiku (cheap — call freely). The question should discriminate: "
            "if the student answers correctly, the hypothesis is wrong; if "
            "they answer incorrectly in the predicted way, it's confirmed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hypothesis": {
                    "type": "string",
                    "description": "The misconception hypothesis to test",
                },
                "concept": {
                    "type": "string",
                    "description": "The concept area (e.g., 'energy conservation')",
                },
                "difficulty": {
                    "type": "string",
                    "enum": ["simpler", "same", "harder"],
                    "description": "Relative to the original problem",
                },
            },
            "required": ["hypothesis", "concept"],
        },
    },
    {
        "name": "update_cognitive_map",
        "description": (
            "Call to record what you've learned about the student's "
            "understanding. NO API call — pure local memory update, zero "
            "cost. Call after confirming a misconception, resolving one, "
            "or discovering a mastered concept. This is the memory system."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Student identifier (default: 'default')",
                },
                "concept": {
                    "type": "string",
                    "description": "The concept being updated (e.g., 'energy conservation')",
                },
                "status": {
                    "type": "string",
                    "enum": ["mastered", "misconception", "partial", "resolved"],
                    "description": "mastered=understands, misconception=confirmed wrong model, partial=some understanding, resolved=previously misconceived now fixed",
                },
                "evidence": {
                    "type": "string",
                    "description": "Brief evidence for this assessment",
                },
                "misconception_detail": {
                    "type": "string",
                    "description": "If status=misconception, describe the specific wrong mental model",
                },
            },
            "required": ["concept", "status", "evidence"],
        },
    },
    {
        "name": "get_cognitive_map",
        "description": (
            "Call to retrieve the student's full cognitive map — what they "
            "know, what they misconceive, and what's been resolved. NO API "
            "call, zero cost. Use this to tailor your approach: don't "
            "re-diagnose resolved misconceptions, build on mastered concepts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "Student identifier (default: 'default')",
                },
            },
            "required": [],
        },
    },
    {
        "name": "generate_scaffold",
        "description": (
            "Call AFTER confirming a misconception to provide the MINIMAL "
            "intervention. Uses Haiku (cheap). The scaffold should be the "
            "smallest hint that unblocks progress — an analogy, a "
            "counter-example, a pointed question. Never the full solution."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "misconception": {
                    "type": "string",
                    "description": "The confirmed misconception to address",
                },
                "concept": {
                    "type": "string",
                    "description": "The concept area",
                },
                "student_level": {
                    "type": "string",
                    "description": "What the student already understands (to avoid over-explaining)",
                },
            },
            "required": ["misconception", "concept"],
        },
    },
    {
        "name": "verify_understanding",
        "description": (
            "Call AFTER scaffolding when the student tries again. Uses "
            "Haiku (cheap). Checks whether the misconception is resolved "
            "by analyzing the student's new response. Returns structured "
            "verdict: resolved (bool), confidence, and suggested next step."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "original_misconception": {
                    "type": "string",
                    "description": "The misconception that was scaffolded",
                },
                "student_response": {
                    "type": "string",
                    "description": "The student's new answer or reasoning after scaffolding",
                },
                "expected_correct": {
                    "type": "string",
                    "description": "What a correct understanding would look like",
                },
            },
            "required": ["original_misconception", "student_response"],
        },
    },
]


def handle_tool(client: anthropic.Anthropic, name: str, args: dict) -> str:
    # --- Diagnostician subagent (Opus) — the expensive, deep-reasoning call ---
    if name == "diagnose_misconception":
        resp = client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=512,
            system=[{
                "type": "text",
                "text": (
                    "You are an expert diagnostician of student misconceptions "
                    "in STEM. Analyze the student's work and identify the ROOT "
                    "misconception — not the surface error, but the underlying "
                    "wrong mental model. Respond with ONLY a JSON object:\n"
                    "{\n"
                    '  "concept": "<the concept area>",\n'
                    '  "misconception_type": "procedural|conceptual|factual",\n'
                    '  "hypothesis": "<the specific wrong mental model>",\n'
                    '  "evidence": "<quote from student work that reveals this>",\n'
                    '  "confidence": <0.0-1.0>,\n'
                    '  "probe_suggestion": "<a question to confirm this hypothesis>"\n'
                    "}"
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            thinking={"type": "adaptive"},
            messages=[{
                "role": "user",
                "content": (
                    f"Student's work:\n{args['student_work']}\n\n"
                    f"Problem context: {args['problem_context']}\n\n"
                    f"Known concepts: {args.get('known_concepts', 'None yet')}"
                ),
            }],
        )
        text = resp.content[-1].text if resp.content else "{}"
        return text

    # --- Probe Generator subagent (Haiku) — cheap diagnostic questions ---
    if name == "generate_probe":
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "Generate ONE short, targeted diagnostic question that "
                    "tests whether a student has a specific misconception. "
                    "The question should discriminate: a correct answer means "
                    "the hypothesis is wrong; a specific wrong answer pattern "
                    "confirms it. Return ONLY a JSON object:\n"
                    '{"question": "<the probe question>", '
                    '"confirms_if": "<what answer pattern confirms the misconception>", '
                    '"refutes_if": "<what answer pattern refutes it>"}'
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Hypothesis: {args['hypothesis']}\n"
                    f"Concept: {args['concept']}\n"
                    f"Difficulty: {args.get('difficulty', 'same')}"
                ),
            }],
        )
        return resp.content[0].text

    # --- Memory: update cognitive map (NO API call — zero cost) ---
    if name == "update_cognitive_map":
        student_id = args.get("student_id", "default")
        cmap = _get_or_create_map(student_id)
        concept = args["concept"]
        status = args["status"]

        cmap["concepts"][concept] = {
            "status": status,
            "evidence": args["evidence"],
            "updated_at": time.strftime("%H:%M:%S"),
        }

        if status == "misconception":
            cmap["misconceptions"].append({
                "concept": concept,
                "detail": args.get("misconception_detail", ""),
                "resolved": False,
                "attempts": 0,
            })
        elif status == "resolved":
            for m in cmap["misconceptions"]:
                if m["concept"] == concept and not m["resolved"]:
                    m["resolved"] = True
                    break

        return json.dumps({
            "status": "updated",
            "concept": concept,
            "new_status": status,
            "total_concepts_tracked": len(cmap["concepts"]),
            "active_misconceptions": sum(
                1 for m in cmap["misconceptions"] if not m["resolved"]
            ),
        })

    # --- Memory: read cognitive map (NO API call — zero cost) ---
    if name == "get_cognitive_map":
        student_id = args.get("student_id", "default")
        cmap = _get_or_create_map(student_id)
        return json.dumps(cmap, indent=2)

    # --- Scaffolder subagent (Haiku) — minimal intervention ---
    if name == "generate_scaffold":
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "You are a Socratic tutor. Given a confirmed misconception, "
                    "provide the MINIMAL scaffold to help the student see the "
                    "error themselves. Use ONE of: a counter-example, an analogy, "
                    "a leading question, or a thought experiment. NEVER give the "
                    "answer directly. 2-3 sentences maximum."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Misconception: {args['misconception']}\n"
                    f"Concept: {args['concept']}\n"
                    f"Student already understands: {args.get('student_level', 'unknown')}"
                ),
            }],
        )
        return resp.content[0].text

    # --- Verifier subagent (Haiku) — check resolution ---
    if name == "verify_understanding":
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "Check whether a student's response shows that a specific "
                    "misconception has been resolved. Return ONLY a JSON object:\n"
                    '{"resolved": true/false, "confidence": <0.0-1.0>, '
                    '"evidence": "<what in their response shows resolution or persistence>", '
                    '"next_step": "<what to do next>"}'
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Misconception: {args['original_misconception']}\n"
                    f"Student's new response: {args['student_response']}\n"
                    f"Expected correct: {args.get('expected_correct', 'not specified')}"
                ),
            }],
        )
        return resp.content[0].text

    return json.dumps({"error": f"Unknown tool: {name}"})


def run() -> None:
    client = anthropic.Anthropic()
    history: list[dict] = []
    turn_count = 0

    print("\n" + "=" * 58)
    print("  MisconceptionDebugger")
    print("  I find where your understanding breaks — and fix it.")
    print("  Describe a STEM problem you're stuck on.")
    print("=" * 58 + "\n")

    user = input("🧑‍🎓 ").strip()
    if not user:
        return
    history.append({"role": "user", "content": user})

    while True:
        turn_count += 1

        history = _summarize_history(client, history)

        t0 = time.time()
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
        elapsed = time.time() - t0
        tokens_in = resp.usage.input_tokens
        tokens_out = resp.usage.output_tokens
        print(
            f"   [{elapsed:.1f}s | in:{tokens_in} out:{tokens_out} | "
            f"model:{ORCHESTRATOR_MODEL}]",
            file=sys.stderr,
        )

        history.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type == "text":
                print(f"\n🤖 {block.text}\n")
            elif block.type == "tool_use":
                model_tag = (
                    "Opus" if block.name == "diagnose_misconception"
                    else "local" if block.name in ("update_cognitive_map", "get_cognitive_map")
                    else "Haiku"
                )
                print(f"   ⚙️  {block.name} [{model_tag}]...")
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
            user = input("🧑‍🎓 ").strip()
            if not user:
                cmap = _get_or_create_map("default")
                if cmap["concepts"]:
                    print("\n📊 Session cognitive map:")
                    for concept, data in cmap["concepts"].items():
                        icon = {"mastered": "✅", "misconception": "❌",
                                "partial": "🟡", "resolved": "🔄"}.get(data["status"], "?")
                        print(f"   {icon} {concept}: {data['status']}")
                    resolved = sum(1 for m in cmap["misconceptions"] if m["resolved"])
                    total = len(cmap["misconceptions"])
                    if total:
                        print(f"\n   Misconceptions resolved: {resolved}/{total}")
                return
            history.append({"role": "user", "content": user})


if __name__ == "__main__":
    run()
