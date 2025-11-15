#!/usr/bin/env python3

import asyncio
import json
from typing import Literal

from helpers import codex_path_override
from pydantic import BaseModel

from codex_sdk import Codex, CodexOptions, TurnOptions


class RepositoryStatus(BaseModel):
    """Schema for repository status response using Pydantic."""

    summary: str
    status: Literal["ok", "action_required"]


async def main() -> None:
    """Request a structured output using Pydantic schema."""
    codex = Codex(CodexOptions(codex_path_override=codex_path_override()))
    thread = codex.start_thread()

    # Convert Pydantic model to JSON Schema
    schema = RepositoryStatus.model_json_schema()
    # Ensure additionalProperties is set to false (required by Codex)
    schema["additionalProperties"] = False

    # Run a turn with output schema
    turn = await thread.run("Summarize repository status", TurnOptions(output_schema=schema))

    # Print the final response (should match the schema)
    print(json.dumps(turn.final_response, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
