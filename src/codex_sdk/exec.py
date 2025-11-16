"""
CLI process execution and management.
"""

import asyncio
import contextlib
import os
import platform
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from .thread_options import ApprovalMode, ModelReasoningEffort, SandboxMode


@dataclass
class CodexExecArgs:
    """Arguments for executing the Codex CLI."""

    input: str  # User prompt or structured input

    base_url: str | None = None
    api_key: str | None = None
    thread_id: str | None = None
    images: list[str] | None = None
    # --model
    model: str | None = None
    # --sandbox
    sandbox_mode: SandboxMode | None = None
    # --cd
    working_directory: str | None = None
    # --add-dir
    additional_directories: list[str] | None = None
    # --skip-git-repo-check
    skip_git_repo_check: bool | None = None
    # --output-schema
    output_schema_file: str | None = None
    # --config model_reasoning_effort
    model_reasoning_effort: ModelReasoningEffort | None = None
    # Signal to cancel the execution
    # Python uses asyncio.Event to replicate TypeScript's AbortSignal
    # TypeScript: controller.abort() -> Node.js automatically kills process
    # Python: event.set() -> we monitor event and manually kill process
    signal: asyncio.Event | None = None
    # --config sandbox_workspace_write.network_access
    network_access_enabled: bool | None = None
    # --config features.web_search_request
    web_search_enabled: bool | None = None
    # --config approval_policy
    approval_policy: ApprovalMode | None = None


INTERNAL_ORIGINATOR_ENV = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"
PYTHON_SDK_ORIGINATOR = "codex_sdk_py"


class CodexExec:
    """Manages spawning and communication with the Codex CLI process."""

    def __init__(self, executable_path: str | None = None, env: dict[str, str] | None = None):
        """
        Initialize CodexExec with optional custom executable path and environment.

        Args:
            executable_path: Override path to the codex binary. If None, auto-detect.
            env: Environment variables to pass to the CLI. If None, inherit from os.environ.
        """
        self.executable_path = executable_path or _find_codex_path()
        self.env_override = env

    async def run(self, args: CodexExecArgs) -> AsyncIterator[str]:
        """
        Execute the Codex CLI and yield JSONL lines from stdout.

        Args:
            args: Execution arguments including input, options, and configuration.

        Yields:
            JSONL lines as strings from the CLI stdout.

        Raises:
            RuntimeError: If process creation fails or stdin/stdout are unavailable.
            CodexExecError: If the CLI exits with a non-zero code.
        """
        command_args = ["exec", "--json"]

        if args.model:
            command_args.extend(["--model", args.model])

        if args.sandbox_mode:
            command_args.extend(["--sandbox", args.sandbox_mode])

        if args.working_directory:
            command_args.extend(["--cd", args.working_directory])

        if args.additional_directories:
            for dir_path in args.additional_directories:
                command_args.extend(["--add-dir", dir_path])

        if args.skip_git_repo_check:
            command_args.append("--skip-git-repo-check")

        if args.output_schema_file:
            command_args.extend(["--output-schema", args.output_schema_file])

        if args.model_reasoning_effort:
            command_args.extend(
                ["--config", f'model_reasoning_effort="{args.model_reasoning_effort}"']
            )

        if args.network_access_enabled is not None:
            command_args.extend(
                [
                    "--config",
                    f"sandbox_workspace_write.network_access={str(args.network_access_enabled).lower()}",
                ]
            )

        if args.web_search_enabled is not None:
            command_args.extend(
                [
                    "--config",
                    f"features.web_search_request={str(args.web_search_enabled).lower()}",
                ]
            )

        if args.approval_policy:
            command_args.extend(["--config", f'approval_policy="{args.approval_policy}"'])

        if args.images:
            for image in args.images:
                command_args.extend(["--image", image])

        if args.thread_id:
            command_args.extend(["resume", args.thread_id])

        # Prepare environment variables
        env: dict[str, str] = {}
        if self.env_override:
            env.update(self.env_override)
            # If PATH is not explicitly set in env_override, inherit from os.environ
            # This ensures the codex binary can find system commands (like node)
            if "PATH" not in env and "PATH" in os.environ:
                env["PATH"] = os.environ["PATH"]
        else:
            # Inherit from current environment
            env.update(os.environ)

        if INTERNAL_ORIGINATOR_ENV not in env:
            env[INTERNAL_ORIGINATOR_ENV] = PYTHON_SDK_ORIGINATOR

        if args.base_url:
            env["OPENAI_BASE_URL"] = args.base_url

        if args.api_key:
            env["CODEX_API_KEY"] = args.api_key

        # Spawn the process

        process = await asyncio.create_subprocess_exec(
            self.executable_path,
            *command_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            # Increase buffer limit to handle large file contents in JSON responses
            limit=1024 * 1024 * 50,  # 50MB buffer limit
        )

        if not process.stdin:
            process.kill()
            await process.wait()
            raise RuntimeError("Child process has no stdin")

        if not process.stdout:
            process.kill()
            await process.wait()
            raise RuntimeError("Child process has no stdout")

        # Write input to stdin and close
        process.stdin.write(args.input.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        # Start stderr collection in background
        stderr_chunks: list[bytes] = []

        async def collect_stderr() -> None:
            if process.stderr:
                async for chunk in process.stderr:
                    stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(collect_stderr())

        # Start signal monitoring in background
        # Replicates TypeScript's AbortSignal behavior where Node.js automatically
        # kills the child process when signal.abort() is called
        async def monitor_signal() -> None:
            if args.signal:
                await args.signal.wait()
                if process.returncode is None:
                    process.kill()

        signal_task = asyncio.create_task(monitor_signal())

        try:
            # Read and yield stdout lines
            if process.stdout:
                async for line_bytes in process.stdout:
                    # Check if signal was set - abort immediately if so
                    if args.signal and args.signal.is_set():
                        break

                    line = line_bytes.decode("utf-8").rstrip("\r\n")
                    if line:  # Skip empty lines
                        yield line

            # Wait for process to complete
            exit_code = await process.wait()

            if exit_code != 0:
                stderr_output = b"".join(stderr_chunks).decode("utf-8")
                raise CodexExecError(f"Codex Exec exited with code {exit_code}: {stderr_output}")

        finally:
            # Cleanup - always wait for stderr collection to finish
            stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task

            signal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await signal_task

            if process.returncode is None:
                process.kill()
                await process.wait()


class CodexExecError(Exception):
    """Raised when the Codex CLI exits with a non-zero code."""

    pass


def _find_codex_path() -> str:
    """
    Auto-detect the codex binary path based on platform and architecture.

    Returns:
        Absolute path to the codex binary in the vendor directory.

    Raises:
        RuntimeError: If the platform/architecture is unsupported.
    """
    system = platform.system()
    machine = platform.machine()

    target_triple: str | None = None

    if system in ("Linux", "Android"):
        if machine in ("x86_64", "AMD64"):
            target_triple = "x86_64-unknown-linux-musl"
        elif machine in ("aarch64", "arm64"):
            target_triple = "aarch64-unknown-linux-musl"
    elif system == "Darwin":
        if machine in ("x86_64", "AMD64"):
            target_triple = "x86_64-apple-darwin"
        elif machine in ("aarch64", "arm64"):
            target_triple = "aarch64-apple-darwin"
    elif system == "Windows":
        if machine in ("x86_64", "AMD64"):
            target_triple = "x86_64-pc-windows-msvc"
        elif machine in ("aarch64", "arm64"):
            target_triple = "aarch64-pc-windows-msvc"

    if not target_triple:
        raise RuntimeError(f"Unsupported platform: {system} ({machine})")

    # Find vendor directory relative to this script
    script_path = Path(__file__)
    sdk_root = script_path.parent.parent.parent
    vendor_root = sdk_root / "vendor"
    arch_root = vendor_root / target_triple

    binary_name = "codex.exe" if system == "Windows" else "codex"
    binary_path = arch_root / "codex" / binary_name

    return str(binary_path)
