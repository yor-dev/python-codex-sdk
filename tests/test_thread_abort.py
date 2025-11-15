"""
Tests for signal/abort support - cancellation via asyncio.Event.

In Python, we use asyncio.Event to replicate TypeScript's AbortSignal.
- TypeScript: controller.abort() -> signal.aborted becomes true
- Python: event.set() -> event.is_set() becomes True
"""

import asyncio
from collections.abc import Iterator

import pytest

from codex_sdk.codex import Codex
from codex_sdk.codex_options import CodexOptions
from codex_sdk.exec import CodexExecError
from codex_sdk.turn_options import TurnOptions
from codex_sdk.utils import find_codex_binary

from .responses_proxy import (
    SseResponseBody,
    assistant_message,
    response_completed,
    response_started,
    shell_call,
    sse,
    start_responses_test_proxy,
)

# Path to the codex binary
CODEX_EXEC_PATH = find_codex_binary()


def infinite_shell_call() -> Iterator[SseResponseBody]:
    """Generate infinite shell_call responses for testing abort scenarios."""
    while True:
        yield sse(response_started(), shell_call(), response_completed())


@pytest.mark.asyncio
async def test_abort_run_when_signal_already_set() -> None:
    """Test that run() fails when signal is already set before execution."""
    proxy = await start_responses_test_proxy(infinite_shell_call())

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )
        thread = client.start_thread()

        # Create signal and set it immediately (equivalent to controller.abort())
        signal = asyncio.Event()
        signal.set()

        # The operation should fail because signal is already set
        with pytest.raises(CodexExecError):
            await thread.run("Hello, world!", TurnOptions(signal=signal))

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_abort_run_streamed_when_signal_already_set() -> None:
    """Test that runStreamed() fails when signal is already set before iteration."""
    proxy = await start_responses_test_proxy(infinite_shell_call())

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )
        thread = client.start_thread()

        # Create signal and set it immediately
        signal = asyncio.Event()
        signal.set()

        result = await thread.run_streamed("Hello, world!", TurnOptions(signal=signal))

        # Attempting to iterate should fail
        iteration_started = False
        with pytest.raises(CodexExecError):
            async for event in result.events:
                iteration_started = True
                # Should not get here
                raise AssertionError(f"Should not iterate, got event: {event}")

        # Should fail before any iteration
        assert not iteration_started

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_abort_run_during_execution() -> None:
    """Test that run() is aborted when signal is set during execution."""
    proxy = await start_responses_test_proxy(infinite_shell_call())

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )
        thread = client.start_thread()

        signal = asyncio.Event()

        # Start the operation and abort it after a small delay
        run_task = asyncio.create_task(thread.run("Hello, world!", TurnOptions(signal=signal)))

        # Abort after tiny delay to simulate aborting during execution
        await asyncio.sleep(0.01)
        signal.set()

        # The operation should fail
        with pytest.raises(CodexExecError):
            await run_task

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_abort_run_streamed_during_iteration() -> None:
    """Test that runStreamed() is aborted when signal is set during iteration."""
    proxy = await start_responses_test_proxy(infinite_shell_call())

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
            )
        )
        thread = client.start_thread()

        signal = asyncio.Event()

        result = await thread.run_streamed("Hello, world!", TurnOptions(signal=signal))

        # Abort during iteration
        event_count = 0

        with pytest.raises(CodexExecError):
            async for _event in result.events:
                event_count += 1
                # Abort after a few events
                if event_count == 5:
                    signal.set()
                # Continue iterating - should eventually throw

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_run_completes_normally_when_signal_not_set() -> None:
    """Test that run() completes successfully when signal is not set."""

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

        signal = asyncio.Event()

        # Don't set signal - should complete successfully
        result = await thread.run("Hello, world!", TurnOptions(signal=signal))

        assert result.final_response == "Hi!"
        assert len(result.items) == 1

    finally:
        await proxy.close()
