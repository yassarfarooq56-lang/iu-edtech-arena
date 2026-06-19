"""EdTech Arena — Adaptive Misconception Debugger

A "debugger for student thinking" for first-year university physics
students. Finds the exact concept where understanding breaks, traces
it to a missing prerequisite, then provides the minimal intervention.

MODEL ROUTING (the key economics decision):
  Orchestrator  = Haiku   — conversation + tool dispatch is cheap ($0.001/turn)
  Diagnostician = Opus    — reasoning about WHY a student is wrong ($0.03/call)
  Everything else = Haiku — probes, scaffolds, verification ($0.001/call)

  Why not Opus for orchestration? Orchestration is pattern-matching
  (decide which tool to call next). That's Haiku's strength. Opus is
  overkill — and at $0.03/turn × 10 turns × 1M students = $300K/month.
  Haiku orchestration: $10K/month. Same quality, 30× cheaper.

SUBAGENT TOPOLOGY:
  Orchestrator (Haiku) — manages diagnostic loop, Socratic conversation
    ├── Diagnostician (Opus)    — deep reasoning: root misconception + prerequisite gaps
    ├── Probe Generator (Haiku) — targeted diagnostic questions
    ├── Scaffolder (Haiku)      — minimal interventions
    └── Verifier (Haiku)        — checks if misconception resolved

MEMORY: cognitive map with prerequisite graph — tracks what each student
knows, misconceives, and has resolved. Persists across the full session.
Zero-cost local operations (no API call).

CONTEXT MANAGEMENT: conversation history summarized after 20 turns via
Haiku, cutting context tokens ~80%. Cognitive map is ~200 tokens of
structured data vs ~2000+ tokens of raw conversation.

AMBITION: misconception diagnosis requires theory of mind — reasoning
about WHY someone thinks what they think. This capability is the
primary bottleneck. Each generation of models unlocks a new tier:
  Today's models:  surface errors (wrong formula, sign error)
  Next generation: structural misconceptions (confused causality)
  Future models:   deep analogical errors, implicit assumptions,
                   cross-domain transfer failures
This is exponential: better reasoning-about-reasoning doesn't just
improve accuracy — it makes previously UNDETECTABLE misconceptions
detectable for the first time.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

# --- Model routing ---
# Haiku orchestrates (cheap). Opus diagnoses (deep reasoning, expensive).
# This is the single most important economics decision in the agent.
ORCHESTRATOR_MODEL = "claude-haiku-4-5"
SPECIALIST_MODEL = "claude-opus-4-8"
FAST_MODEL = "claude-haiku-4-5"

SYSTEM = """\
You are MisconceptionDebugger, an AI tutor for first-year university
physics students who are at risk of failing. You don't explain solutions
— you diagnose WHY a student is stuck and provide the minimum
intervention to unblock them.

## Your diagnostic loop

1. Listen to the student's problem or answer.
2. Call `diagnose_misconception` to hypothesize the root cause AND
   identify which prerequisite concept they're missing. This is the
   ONLY expensive call (Opus) — use it deliberately, once per
   misconception, not every turn.
3. Call `generate_probe` to ask a targeted question that confirms or
   refutes your hypothesis (Haiku — cheap, call freely).
4. Based on the student's response, either:
   a. Probe again (different angle) if uncertain, OR
   b. Call `update_cognitive_map` to record the confirmed misconception
      and its prerequisite gap.
5. Call `generate_scaffold` to provide the MINIMAL hint addressing the
   specific misconception (Haiku). Never give the full answer.
6. Call `verify_understanding` after the student tries again (Haiku).
7. Call `update_cognitive_map` to mark it resolved (or increment attempts).

Call `get_cognitive_map` at any time to see the student's full knowledge
state. Use it to: avoid re-diagnosing resolved misconceptions, build on
mastered concepts, and trace prerequisite chains.

## Pedagogical principles

- Socratic method: ask questions that lead to insight. Never lecture.
- Zone of Proximal Development (Vygotsky): work at the boundary between
  what they know and what they don't.
- Productive struggle: intervene only when truly stuck, not just thinking.
- Minimal intervention: smallest hint that unblocks progress.
- Growth mindset: "You haven't connected these yet" not "You don't understand."
- Prerequisite tracing: if the root cause is a missing prerequisite,
  address THAT first. Surface errors vanish when foundations are solid.
"""

# --- Session cost tracking ---
session_cost = {
    "orchestrator_calls": 0,
    "opus_calls": 0,
    "haiku_calls": 0,
    "local_calls": 0,
    "estimated_usd": 0.0,
}

# Approximate per-call costs for monitoring
COST_OPUS_CALL = 0.03
COST_HAIKU_CALL = 0.001
COST_HAIKU_ORCHESTRATOR = 0.002

# --- Memory: per-student cognitive map with prerequisite tracking ---
cognitive_maps: dict[str, dict] = {}

CONTEXT_SUMMARY_THRESHOLD = 20


def _get_or_create_map(student_id: str = "default") -> dict:
    if student_id not in cognitive_maps:
        cognitive_maps[student_id] = {
            "student_id": student_id,
            "concepts": {},
            "prerequisites": {},
            "misconceptions": [],
            "session_summary": "",
        }
    return cognitive_maps[student_id]


def _parse_json_safe(text: str) -> dict:
    """Extract JSON from model responses that may include markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_text": text, "parse_error": True}


def _summarize_history(client: anthropic.Anthropic, history: list[dict]) -> list[dict]:
    """Compress old turns to manage context window. Saves ~80% of tokens."""
    if len(history) <= CONTEXT_SUMMARY_THRESHOLD:
        return history

    old_turns = history[:-6]
    recent_turns = history[-6:]

    summary_text = ""
    for msg in old_turns:
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            summary_text += f"{msg['role']}: {content[:200]}\n"

    if not summary_text.strip():
        return history

    resp = client.messages.create(
        model=FAST_MODEL,
        max_tokens=256,
        system="Summarize this tutoring conversation in 3-4 sentences. Focus on: topic, misconceptions found, what was resolved, what's still open.",
        messages=[{"role": "user", "content": summary_text}],
    )
    session_cost["haiku_calls"] += 1
    session_cost["estimated_usd"] += COST_HAIKU_CALL

    summary = resp.content[0].text

    student_map = _get_or_create_map("default")
    student_map["session_summary"] = summary

    compressed = [
        {"role": "user", "content": f"[Session context: {summary}]"},
        {"role": "assistant", "content": "Continuing from where we left off."},
    ]
    return compressed + recent_turns


# --- Tool definitions (7 tools) ---
TOOLS: list[dict] = [
    {
        "name": "diagnose_misconception",
        "description": (
            "Call when the student shows confused reasoning or a wrong answer. "
            "This is the ONLY expensive call — it uses Opus to reason deeply "
            "about the student's thinking. Returns: the root misconception, "
            "its type (procedural/conceptual/factual), which PREREQUISITE "
            "concept is missing, and a suggested probe question. Use once per "
            "misconception, not every turn — budget ~$0.03 per call."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_work": {
                    "type": "string",
                    "description": "The student's answer or reasoning showing the error",
                },
                "problem_context": {
                    "type": "string",
                    "description": "The problem or topic being discussed",
                },
                "cognitive_map_summary": {
                    "type": "string",
                    "description": "Current state from get_cognitive_map (mastered concepts, active misconceptions)",
                },
            },
            "required": ["student_work", "problem_context"],
        },
    },
    {
        "name": "generate_probe",
        "description": (
            "Generate a targeted diagnostic question that tests a specific "
            "misconception hypothesis. Uses Haiku (~$0.001). The question "
            "should discriminate: correct answer refutes the hypothesis, a "
            "specific wrong pattern confirms it. Call freely — it's cheap."
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
                    "description": "The concept area",
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
            "Record what you learned about the student's understanding. "
            "NO API call — zero cost, pure local memory. Call after: "
            "confirming a misconception, resolving one, discovering a "
            "mastered concept, or identifying a prerequisite gap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "The concept (e.g., 'kinetic energy', 'vector decomposition')",
                },
                "status": {
                    "type": "string",
                    "enum": ["mastered", "misconception", "partial", "resolved"],
                },
                "evidence": {
                    "type": "string",
                    "description": "Brief evidence for this assessment",
                },
                "misconception_detail": {
                    "type": "string",
                    "description": "If misconception: the specific wrong mental model",
                },
                "prerequisite_of": {
                    "type": "string",
                    "description": "If this concept is a prerequisite for another, name the dependent concept",
                },
            },
            "required": ["concept", "status", "evidence"],
        },
    },
    {
        "name": "get_cognitive_map",
        "description": (
            "Read the student's full cognitive map — mastered concepts, "
            "active misconceptions, resolved misconceptions, and "
            "prerequisite relationships. NO API call, zero cost. Use to "
            "tailor your approach and avoid redundant diagnosis."
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
            "Provide the MINIMAL intervention for a confirmed misconception. "
            "Uses Haiku (~$0.001). One of: counter-example, analogy, leading "
            "question, thought experiment. Never the full solution. If the "
            "root cause is a missing prerequisite, scaffold THAT instead."
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
                    "description": "What the student already understands",
                },
                "missing_prerequisite": {
                    "type": "string",
                    "description": "If the misconception stems from a prerequisite gap, name it here so the scaffold targets the foundation",
                },
            },
            "required": ["misconception", "concept"],
        },
    },
    {
        "name": "verify_understanding",
        "description": (
            "Check if a misconception is resolved after scaffolding. Uses "
            "Haiku (~$0.001). Analyzes the student's new response and returns "
            "a verdict: resolved (bool), confidence, evidence, and next step."
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
                    "description": "The student's new answer after scaffolding",
                },
                "expected_correct": {
                    "type": "string",
                    "description": "What correct understanding looks like",
                },
            },
            "required": ["original_misconception", "student_response"],
        },
    },
    {
        "name": "suggest_next_concept",
        "description": (
            "Call after resolving a misconception to identify what the "
            "student should work on next, based on their cognitive map. "
            "NO API call — uses prerequisite graph to find the optimal "
            "next concept (the one closest to their current frontier). "
            "This is where the agent gets disproportionately better with "
            "smarter models: richer prerequisite graphs, deeper chains."
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
]


def handle_tool(client: anthropic.Anthropic, name: str, args: dict) -> str:
    # --- Diagnostician subagent (Opus) — deep reasoning about student thinking ---
    if name == "diagnose_misconception":
        resp = client.messages.create(
            model=SPECIALIST_MODEL,
            max_tokens=512,
            system=[{
                "type": "text",
                "text": (
                    "You are an expert diagnostician of student misconceptions "
                    "in physics. Analyze the student's work to find:\n"
                    "1. The ROOT misconception (not the surface error)\n"
                    "2. Which PREREQUISITE concept they're missing\n"
                    "3. The specific wrong mental model they hold\n\n"
                    "Respond with ONLY a JSON object:\n"
                    "{\n"
                    '  "concept": "<the concept area>",\n'
                    '  "misconception_type": "procedural|conceptual|factual",\n'
                    '  "hypothesis": "<the specific wrong mental model>",\n'
                    '  "evidence": "<quote from student work>",\n'
                    '  "missing_prerequisite": "<which foundational concept is weak>",\n'
                    '  "confidence": <0.0-1.0>,\n'
                    '  "probe_suggestion": "<question to confirm this>"\n'
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
                    f"Cognitive map: {args.get('cognitive_map_summary', 'First interaction')}"
                ),
            }],
        )
        session_cost["opus_calls"] += 1
        session_cost["estimated_usd"] += COST_OPUS_CALL

        for block in reversed(resp.content):
            if hasattr(block, "text"):
                return block.text
        return json.dumps({"error": "No text in diagnosis response"})

    # --- Probe Generator subagent (Haiku) ---
    if name == "generate_probe":
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "Generate ONE targeted diagnostic question. It should "
                    "discriminate: correct answer refutes the hypothesis, "
                    "a specific wrong pattern confirms it. Return JSON:\n"
                    '{"question": "...", "confirms_if": "...", "refutes_if": "..."}'
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
        session_cost["haiku_calls"] += 1
        session_cost["estimated_usd"] += COST_HAIKU_CALL
        return resp.content[0].text

    # --- Memory: update cognitive map (NO API call) ---
    if name == "update_cognitive_map":
        cmap = _get_or_create_map("default")
        concept = args["concept"]
        status = args["status"]

        cmap["concepts"][concept] = {
            "status": status,
            "evidence": args["evidence"],
            "updated_at": time.strftime("%H:%M:%S"),
        }

        if args.get("prerequisite_of"):
            cmap["prerequisites"][concept] = args["prerequisite_of"]

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

        session_cost["local_calls"] += 1
        return json.dumps({
            "status": "updated",
            "concept": concept,
            "new_status": status,
            "total_concepts_tracked": len(cmap["concepts"]),
            "active_misconceptions": sum(1 for m in cmap["misconceptions"] if not m["resolved"]),
            "prerequisite_links": len(cmap["prerequisites"]),
        })

    # --- Memory: read cognitive map (NO API call) ---
    if name == "get_cognitive_map":
        student_id = args.get("student_id", "default")
        cmap = _get_or_create_map(student_id)
        session_cost["local_calls"] += 1
        return json.dumps(cmap, indent=2)

    # --- Scaffolder subagent (Haiku) ---
    if name == "generate_scaffold":
        prerequisite_note = ""
        if args.get("missing_prerequisite"):
            prerequisite_note = (
                f"\nIMPORTANT: The root cause is a gap in '{args['missing_prerequisite']}'. "
                "Scaffold THAT prerequisite, not the surface-level misconception."
            )
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "You are a Socratic physics tutor. Provide the MINIMAL "
                    "scaffold: one counter-example, analogy, or leading question. "
                    "NEVER give the answer. 2-3 sentences max." + prerequisite_note
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Misconception: {args['misconception']}\n"
                    f"Concept: {args['concept']}\n"
                    f"Student knows: {args.get('student_level', 'unknown')}"
                ),
            }],
        )
        session_cost["haiku_calls"] += 1
        session_cost["estimated_usd"] += COST_HAIKU_CALL
        return resp.content[0].text

    # --- Verifier subagent (Haiku) ---
    if name == "verify_understanding":
        resp = client.messages.create(
            model=FAST_MODEL,
            max_tokens=256,
            system=[{
                "type": "text",
                "text": (
                    "Check if the student's response shows a misconception "
                    "is resolved. Return JSON:\n"
                    '{"resolved": true/false, "confidence": 0.0-1.0, '
                    '"evidence": "...", "next_step": "..."}'
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Misconception: {args['original_misconception']}\n"
                    f"Student response: {args['student_response']}\n"
                    f"Expected correct: {args.get('expected_correct', 'not specified')}"
                ),
            }],
        )
        session_cost["haiku_calls"] += 1
        session_cost["estimated_usd"] += COST_HAIKU_CALL
        return resp.content[0].text

    # --- Prerequisite navigator (NO API call) ---
    if name == "suggest_next_concept":
        cmap = _get_or_create_map(args.get("student_id", "default"))
        session_cost["local_calls"] += 1

        active = [m["concept"] for m in cmap["misconceptions"] if not m["resolved"]]
        if active:
            return json.dumps({
                "suggestion": f"Resolve active misconception: {active[0]}",
                "reason": "Active misconceptions block downstream learning",
                "active_misconceptions": active,
            })

        unmastered_prereqs = [
            concept for concept, depends_on in cmap["prerequisites"].items()
            if cmap["concepts"].get(concept, {}).get("status") != "mastered"
        ]
        if unmastered_prereqs:
            return json.dumps({
                "suggestion": f"Strengthen prerequisite: {unmastered_prereqs[0]}",
                "reason": "This concept is a prerequisite for topics with prior misconceptions",
                "weak_prerequisites": unmastered_prereqs,
            })

        return json.dumps({
            "suggestion": "Student's tracked concepts look solid. Introduce a new topic or increase difficulty.",
            "mastered": [c for c, d in cmap["concepts"].items() if d["status"] == "mastered"],
        })

    return json.dumps({"error": f"Unknown tool: {name}"})


def run() -> None:
    client = anthropic.Anthropic()
    history: list[dict] = []

    print("\n" + "=" * 58)
    print("  MisconceptionDebugger")
    print("  I find where your understanding breaks — and fix it.")
    print("  Tell me about a physics problem you're stuck on.")
    print("=" * 58 + "\n")

    user = input("🧑‍🎓 ").strip()
    if not user:
        return
    history.append({"role": "user", "content": user})

    while True:
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
            messages=history,
        )
        elapsed = time.time() - t0
        session_cost["orchestrator_calls"] += 1
        session_cost["estimated_usd"] += COST_HAIKU_ORCHESTRATOR

        print(
            f"   [{elapsed:.1f}s | in:{resp.usage.input_tokens} "
            f"out:{resp.usage.output_tokens} | "
            f"orchestrator:{ORCHESTRATOR_MODEL} | "
            f"session:${session_cost['estimated_usd']:.3f}]",
            file=sys.stderr,
        )

        history.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type == "text":
                print(f"\n🤖 {block.text}\n")
            elif block.type == "tool_use":
                if block.name == "diagnose_misconception":
                    model_tag = f"Opus ~${COST_OPUS_CALL}"
                elif block.name in ("update_cognitive_map", "get_cognitive_map", "suggest_next_concept"):
                    model_tag = "local $0"
                else:
                    model_tag = f"Haiku ~${COST_HAIKU_CALL}"
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
                _print_session_summary()
                return
            history.append({"role": "user", "content": user})


def _print_session_summary() -> None:
    cmap = _get_or_create_map("default")
    print("\n" + "=" * 58)
    print("  SESSION SUMMARY")
    print("=" * 58)

    if cmap["concepts"]:
        print("\n  Cognitive map:")
        for concept, data in cmap["concepts"].items():
            icon = {"mastered": "✅", "misconception": "❌",
                    "partial": "🟡", "resolved": "🔄"}.get(data["status"], "?")
            print(f"    {icon} {concept}: {data['status']}")

        if cmap["prerequisites"]:
            print("\n  Prerequisites identified:")
            for prereq, depends in cmap["prerequisites"].items():
                print(f"    {prereq} → needed for → {depends}")

        resolved = sum(1 for m in cmap["misconceptions"] if m["resolved"])
        total = len(cmap["misconceptions"])
        if total:
            print(f"\n  Misconceptions: {resolved}/{total} resolved")

    print(f"\n  Cost breakdown:")
    print(f"    Orchestrator (Haiku): {session_cost['orchestrator_calls']} calls")
    print(f"    Diagnosis (Opus):     {session_cost['opus_calls']} calls")
    print(f"    Tools (Haiku):        {session_cost['haiku_calls']} calls")
    print(f"    Memory (local):       {session_cost['local_calls']} calls")
    print(f"    Estimated total:      ${session_cost['estimated_usd']:.3f}")
    print("=" * 58)


if __name__ == "__main__":
    run()
