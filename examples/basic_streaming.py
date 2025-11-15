#!/usr/bin/env python3

import asyncio
import sys

from helpers import codex_path_override

from codex_sdk import Codex, CodexOptions, ThreadEvent, ThreadItem
from codex_sdk.events import ItemCompletedEvent, ItemStartedEvent, ItemUpdatedEvent


def handle_item_completed(item: ThreadItem) -> None:
    """Handle completed items and display relevant information."""
    if item.type == "agent_message":
        print(f"Assistant: {item.text}")
    elif item.type == "reasoning":
        print(f"Reasoning: {item.text}")
    elif item.type == "command_execution":
        exit_text = f" Exit code {item.exit_code}." if item.exit_code is not None else ""
        print(f"Command {item.command} {item.status}.{exit_text}")
    elif item.type == "file_change":
        for change in item.changes:
            print(f"File {change.kind} {change.path}")


def handle_item_updated(item: ThreadItem) -> None:
    """Handle updated items and display relevant information."""
    if item.type == "todo_list":
        print("Todo:")
        for todo in item.items:
            status = "x" if todo.completed else " "
            print(f"\t {status} {todo.text}")


def handle_event(event: ThreadEvent) -> None:
    """Handle different event types from the thread."""
    if isinstance(event, ItemCompletedEvent):
        handle_item_completed(event.item)
    elif isinstance(event, (ItemUpdatedEvent, ItemStartedEvent)):
        handle_item_updated(event.item)
    elif event.type == "turn.completed":
        usage = event.usage
        print(
            f"Used {usage.input_tokens} input tokens, "
            f"{usage.cached_input_tokens} cached input tokens, "
            f"{usage.output_tokens} output tokens."
        )
    elif event.type == "turn.failed":
        print(f"Turn failed: {event.error.message}", file=sys.stderr)


async def main() -> None:
    """Main interactive REPL loop."""
    codex = Codex(CodexOptions(codex_path_override=codex_path_override()))
    thread = codex.start_thread()

    try:
        while True:
            # Read input from user
            input_text = input(">")
            trimmed = input_text.strip()

            if not trimmed:
                continue

            # Run turn in streaming mode
            result = await thread.run_streamed(input_text)

            # Process each event as it arrives
            async for event in result.events:
                handle_event(event)

    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")
    except Exception as err:
        print(f"Unexpected error: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
