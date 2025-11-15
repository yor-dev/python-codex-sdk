"""
Spy utility for capturing CLI arguments and environment variables.

Replicates TypeScript's codexExecSpy functionality using monkeypatch.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest


@dataclass
class CodexExecSpyResult:
    """Results from spying on subprocess execution."""

    args: list[tuple[str, ...]]  # Recorded command line arguments
    envs: list[dict[str, str] | None]  # Recorded environment variables


@pytest.fixture
def codex_exec_spy(monkeypatch: pytest.MonkeyPatch) -> CodexExecSpyResult:
    """
    Fixture that spies on subprocess calls to record CLI arguments and environment variables.

    The actual codex binary is still executed - this only records the parameters.

    Returns:
        CodexExecSpyResult with recorded args and envs
    """
    recorded_args: list[tuple[str, ...]] = []
    recorded_envs: list[dict[str, str] | None] = []

    # Save original function
    original_create_subprocess_exec = asyncio.create_subprocess_exec

    async def spy_create_subprocess_exec(
        program: str,
        *args: str,
        stdin: Any = None,
        stdout: Any = None,
        stderr: Any = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> asyncio.subprocess.Process:
        """Spy wrapper that records arguments and env, then calls original."""
        # Record the command line arguments (excluding program name)
        recorded_args.append(args)

        # Record the environment variables
        recorded_envs.append(env.copy() if env else None)

        # Call the original function with all parameters
        return await original_create_subprocess_exec(
            program,
            *args,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            env=env,
            **kwargs,
        )

    # Patch asyncio.create_subprocess_exec
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spy_create_subprocess_exec)

    return CodexExecSpyResult(args=recorded_args, envs=recorded_envs)
