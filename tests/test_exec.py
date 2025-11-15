"""
Tests for exec.py - CLI process execution.
"""

import json

import pytest

from codex_sdk.exec import CodexExec, CodexExecArgs, CodexExecError
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


@pytest.mark.asyncio
async def test_exec_spawns_process_and_yields_jsonl() -> None:
    """Test that CodexExec can spawn the codex binary and yield JSONL lines."""
    # Start mock HTTP server
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Hi!"), response_completed())]
    )

    try:
        # Create CodexExec with actual codex binary
        exec_instance = CodexExec(executable_path=CODEX_EXEC_PATH)

        # Execute and collect JSONL lines
        lines = []
        async for line in exec_instance.run(
            CodexExecArgs(input="Hello, world!", base_url=proxy.url, api_key="test")
        ):
            lines.append(line)

        # Verify we got JSONL lines
        assert len(lines) > 0, "Should receive at least one JSONL line"

        # Verify lines are valid JSON
        events = []
        for line in lines:
            event = json.loads(line)
            events.append(event)
            assert "type" in event, f"Event should have 'type' field: {event}"

        # Verify we got expected event types
        event_types = [e["type"] for e in events]
        assert "thread.started" in event_types, "Should receive thread.started event"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_exec_passes_environment_variables() -> None:
    """Test that environment variables are passed to the CLI process."""
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Test"), response_completed())]
    )

    try:
        exec_instance = CodexExec(executable_path=CODEX_EXEC_PATH)

        lines = []
        async for line in exec_instance.run(
            CodexExecArgs(
                input="Test",
                base_url=proxy.url,  # This sets OPENAI_BASE_URL env var
                api_key="test_key",  # This sets CODEX_API_KEY env var
            )
        ):
            lines.append(line)

        # Verify request was made to our mock server
        assert len(proxy.requests) > 0, "Should make at least one HTTP request"

        # The fact that we got a response means env vars were passed correctly
        assert len(lines) > 0

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_exec_handles_command_line_arguments() -> None:
    """Test that command line arguments are properly constructed."""
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Test"), response_completed())]
    )

    try:
        exec_instance = CodexExec(executable_path=CODEX_EXEC_PATH)

        lines = []
        async for line in exec_instance.run(
            CodexExecArgs(
                input="Test",
                base_url=proxy.url,
                api_key="test",
                model="claude-3-5-sonnet-20241022",
                sandbox_mode="read-only",
                skip_git_repo_check=True,
            )
        ):
            lines.append(line)

        # Verify execution completed successfully
        assert len(lines) > 0

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_exec_raises_error_on_nonzero_exit() -> None:
    """Test that CodexExecError is raised when the CLI exits with non-zero code."""
    # Create exec with invalid executable path to force an error
    # Or use invalid arguments that will cause the CLI to fail
    exec_instance = CodexExec(executable_path=CODEX_EXEC_PATH)

    # Use invalid base_url (no server running) to cause failure
    with pytest.raises(CodexExecError) as exc_info:
        lines = []
        async for line in exec_instance.run(
            CodexExecArgs(
                input="Test",
                base_url="http://127.0.0.1:1",  # Invalid port
                api_key="test",
            )
        ):
            lines.append(line)

    # Verify error message contains exit code information
    assert "exited with code" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_exec_with_thread_id_for_resume() -> None:
    """Test that thread_id argument is passed correctly for resuming threads."""
    # Prepare 2 responses: one for initial run, one for resume
    proxy = await start_responses_test_proxy(
        [
            sse(response_started(), assistant_message("First"), response_completed()),
            sse(response_started(), assistant_message("Resumed"), response_completed()),
        ]
    )

    try:
        exec_instance = CodexExec(executable_path=CODEX_EXEC_PATH)

        # First run to get a thread ID
        thread_id = None
        async for line in exec_instance.run(
            CodexExecArgs(input="First", base_url=proxy.url, api_key="test")
        ):
            event = json.loads(line)
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")

        assert thread_id is not None, "Should receive thread_id from first run"

        # Second run with thread_id (resume)
        lines = []
        async for line in exec_instance.run(
            CodexExecArgs(
                input="Second",
                base_url=proxy.url,
                api_key="test",
                thread_id=thread_id,
            )
        ):
            lines.append(line)

        # Verify second run completed
        assert len(lines) > 0

    finally:
        await proxy.close()
