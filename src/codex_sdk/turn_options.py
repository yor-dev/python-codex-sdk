"""
Turn execution options.
"""

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class TurnOptions:
    """Options for executing a turn."""

    # JSON schema describing the expected agent output
    # Must be a valid JSON Schema object (dict with type, properties, etc.)
    output_schema: dict[str, Any] | None = None
    # Signal to cancel the turn execution
    # Python uses asyncio.Event to mimic TypeScript's AbortSignal
    # Usage: event = asyncio.Event(); event.set() to cancel
    signal: asyncio.Event | None = None
