"""EdTech Arena starter agent.

This is a working but deliberately naive tutor. Your job: make it actually
useful for ONE problem from README.md. The judge reads this code — make the
design obvious.
"""
from __future__ import annotations

from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

MODEL = "claude-opus-4-8"

SYSTEM = """\
You are a tutor. Help the student.
"""

TOOLS: list[dict] = [
    # add tools here — name, description (say WHEN to call it), input_schema
]


def run(first_message: str) -> None:
    client = anthropic.Anthropic()
    history: list[dict] = [{"role": "user", "content": first_message}]

    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

        for block in resp.content:
            if block.type == "text":
                print(f"\n🤖 {block.text}\n")
            elif block.type == "tool_use":
                result = handle_tool(block.name, block.input)
                history.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }],
                })

        if resp.stop_reason != "tool_use":
            user = input("👤 ").strip()
            if not user:
                return
            history.append({"role": "user", "content": user})


def handle_tool(name: str, args: dict) -> str:
    # Implement your tools here. Returning a string is fine.
    return f"(tool {name!r} not implemented — args={args})"


if __name__ == "__main__":
    run("Hi, I need help with fractions.")
