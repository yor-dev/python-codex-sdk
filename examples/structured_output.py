#!/usr/bin/env python3

import asyncio
import json

from helpers import codex_path_override

from codex_sdk import Codex, CodexOptions, TurnOptions

# Define JSON Schema for structured output
schema = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "status": {"type": "string", "enum": ["ok", "action_required"]},
    },
    "required": ["summary", "status"],
    "additionalProperties": False,
}


async def main() -> None:
    """Request a structured output using JSON Schema."""
    codex = Codex(CodexOptions(codex_path_override=codex_path_override()))
    thread = codex.start_thread()

    # Run a turn with output schema
    turn = await thread.run("Summarize repository status", TurnOptions(output_schema=schema))

    # Print the final response (should match the schema)
    print(json.dumps(turn.final_response, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
