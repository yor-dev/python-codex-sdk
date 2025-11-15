"""
Tests for thread.run_streamed() - streaming conversation execution.
"""

import json
from collections.abc import AsyncIterator

import pytest

from codex_sdk.codex import Codex
from codex_sdk.codex_options import CodexOptions
from codex_sdk.events import ThreadEvent
from codex_sdk.items import AgentMessageItem
from codex_sdk.turn_options import TurnOptions
from codex_sdk.utils import find_codex_binary

from .responses_proxy import (
    assistant_message,
    response_completed,
    response_started,
    sse,
    start_responses_test_proxy,
)

# Path to the codex binary
CODEX_EXEC_PATH = find_codex_binary()


async def drain_events(events: AsyncIterator[ThreadEvent]) -> None:
    """Helper to consume all events from an async generator."""
    async for _ in events:
        pass


@pytest.mark.asyncio
async def test_run_streamed_returns_thread_events() -> None:
    """Test that runStreamed() returns thread events correctly."""
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Hi!"), response_completed())]
    )

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )

        thread = client.start_thread()
        result = await thread.run_streamed("Hello, world!")

        # Collect all events
        events: list[ThreadEvent] = []
        async for event in result.events:
            events.append(event)

        # Verify event types and structure
        assert len(events) == 4, f"Expected 4 events, got {len(events)}"

        # thread.started
        assert events[0].type == "thread.started"
        assert hasattr(events[0], "thread_id")
        assert isinstance(events[0].thread_id, str)

        # turn.started
        assert events[1].type == "turn.started"

        # item.completed with agent_message
        assert events[2].type == "item.completed"
        assert hasattr(events[2], "item")
        item = events[2].item
        assert isinstance(item, AgentMessageItem)
        assert item.id == "item_0"
        assert item.type == "agent_message"
        assert item.text == "Hi!"

        # turn.completed with usage
        assert events[3].type == "turn.completed"
        assert hasattr(events[3], "usage")
        usage = events[3].usage
        assert usage.cached_input_tokens == 12
        assert usage.input_tokens == 42
        assert usage.output_tokens == 5

        # Verify thread ID was set
        assert thread.id is not None
        assert isinstance(thread.id, str)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_run_streamed_sends_previous_items_on_second_call() -> None:
    """Test that previous items are sent to API when runStreamed is called twice."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("First response", "item_1"),
                response_completed("response_1"),
            ),
            sse(
                response_started("response_2"),
                assistant_message("Second response", "item_2"),
                response_completed("response_2"),
            ),
        ]
    )

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )

        thread = client.start_thread()

        # First call
        first = await thread.run_streamed("first input")
        await drain_events(first.events)

        # Second call
        second = await thread.run_streamed("second input")
        await drain_events(second.events)

        # Verify at least 2 requests were made
        assert len(proxy.requests) >= 2, f"Expected at least 2 requests, got {len(proxy.requests)}"

        # Check second request contains assistant message from first response
        second_request = proxy.requests[1]
        payload = json.loads(second_request.body)

        # Find assistant entry in input
        assistant_entry = None
        for entry in payload["input"]:
            if entry.get("role") == "assistant":
                assistant_entry = entry
                break

        assert assistant_entry is not None, "Second request should include assistant entry"

        # Find output_text in assistant content
        assistant_text = None
        for item in assistant_entry.get("content", []):
            if item.get("type") == "output_text":
                assistant_text = item.get("text")
                break

        assert assistant_text == "First response", (
            "Second request should include first response text"
        )

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_run_streamed_resumes_thread_by_id() -> None:
    """Test that resumeThread() continues the same thread when streaming."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("First response", "item_1"),
                response_completed("response_1"),
            ),
            sse(
                response_started("response_2"),
                assistant_message("Second response", "item_2"),
                response_completed("response_2"),
            ),
        ]
    )

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )

        # Start original thread
        original_thread = client.start_thread()
        first = await original_thread.run_streamed("first input")
        await drain_events(first.events)

        # Resume thread by ID
        assert original_thread.id is not None
        resumed_thread = client.resume_thread(original_thread.id)
        second = await resumed_thread.run_streamed("second input")
        await drain_events(second.events)

        # Verify resumed thread has same ID
        assert resumed_thread.id == original_thread.id

        # Verify second request contains previous assistant message
        assert len(proxy.requests) >= 2
        second_request = proxy.requests[1]
        payload = json.loads(second_request.body)

        assistant_entry = None
        for entry in payload["input"]:
            if entry.get("role") == "assistant":
                assistant_entry = entry
                break

        assert assistant_entry is not None

        assistant_text = None
        for item in assistant_entry.get("content", []):
            if item.get("type") == "output_text":
                assistant_text = item.get("text")
                break

        assert assistant_text == "First response"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_run_streamed_applies_output_schema() -> None:
    """Test that outputSchema turn option is applied correctly when streaming."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Structured response", "item_1"),
                response_completed("response_1"),
            ),
        ]
    )

    schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
        },
        "required": ["answer"],
        "additionalProperties": False,
    }

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )

        thread = client.start_thread()
        streamed = await thread.run_streamed("structured", TurnOptions(output_schema=schema))
        await drain_events(streamed.events)

        # Verify request was made with output schema
        assert len(proxy.requests) >= 1
        first_request = proxy.requests[0]
        payload = json.loads(first_request.body)

        # Check text.format field contains schema
        text_config = payload.get("text")
        assert text_config is not None, "Request should have 'text' field"

        format_config = text_config.get("format")
        assert format_config is not None, "text should have 'format' field"

        assert format_config.get("name") == "codex_output_schema"
        assert format_config.get("type") == "json_schema"
        assert format_config.get("strict") is True
        assert format_config.get("schema") == schema

    finally:
        await proxy.close()
