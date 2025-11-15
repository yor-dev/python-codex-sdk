"""
Thread management for conversations with the agent.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from .codex_options import CodexOptions
from .events import ThreadEvent, Usage, parse_event
from .exec import CodexExec, CodexExecArgs
from .items import ThreadItem
from .output_schema_file import create_output_schema_file
from .thread_options import ThreadOptions
from .turn_options import TurnOptions


@dataclass
class Turn:
    """Completed turn."""

    items: list[ThreadItem]
    final_response: str
    usage: Usage | None


# Alias for Turn to describe the result of run()
RunResult = Turn


@dataclass
class StreamedTurn:
    """The result of the runStreamed method."""

    events: AsyncIterator[ThreadEvent]


# Alias for StreamedTurn to describe the result of run_streamed()
RunStreamedResult = StreamedTurn


@dataclass
class UserInputText:
    """Text input from user."""

    type: Literal["text"]
    text: str


@dataclass
class UserInputImage:
    """Local image input from user."""

    type: Literal["local_image"]
    path: str


# Union type for user input
UserInput = UserInputText | UserInputImage

# Input can be a string or a list of UserInput
Input = str | list[UserInput]


class Thread:
    """Represent a thread of conversation with the agent. One thread can have multiple consecutive turns."""

    def __init__(
        self,
        exec: CodexExec,
        options: CodexOptions,
        thread_options: ThreadOptions,
        id: str | None = None,
    ):
        """
        Initialize a Thread instance.

        Args:
            exec: CodexExec instance for CLI process management
            options: Global Codex options
            thread_options: Thread-specific options
            id: Optional thread ID (for resuming existing threads)
        """
        self._exec = exec
        self._options = options
        self._id = id
        self._thread_options = thread_options

    @property
    def id(self) -> str | None:
        """Returns the ID of the thread. Populated after the first turn starts."""
        return self._id

    async def run_streamed(
        self, input: Input, turn_options: TurnOptions | None = None
    ) -> StreamedTurn:
        """
        Provides the input to the agent and streams events as they are produced during the turn.

        Args:
            input: User input (string or list of UserInput)
            turn_options: Optional turn-specific options

        Returns:
            StreamedTurn containing an async iterator of events
        """
        if turn_options is None:
            turn_options = TurnOptions()
        return StreamedTurn(events=self._run_streamed_internal(input, turn_options))

    async def _run_streamed_internal(
        self, input: Input, turn_options: TurnOptions
    ) -> AsyncIterator[ThreadEvent]:
        """
        Internal implementation of streaming turn execution.

        Args:
            input: User input
            turn_options: Turn-specific options

        Yields:
            ThreadEvent instances as they are produced
        """
        # Create output schema file if provided
        output_schema_file = await create_output_schema_file(turn_options.output_schema)

        # Normalize input to prompt string and images
        prompt, images = _normalize_input(input)

        options = self._thread_options

        # Build exec arguments
        exec_args = CodexExecArgs(
            input=prompt,
            base_url=self._options.base_url,
            api_key=self._options.api_key,
            thread_id=self._id,
            images=images,
            model=options.model,
            sandbox_mode=options.sandbox_mode,
            working_directory=options.working_directory,
            skip_git_repo_check=options.skip_git_repo_check,
            output_schema_file=output_schema_file.schema_path,
            model_reasoning_effort=options.model_reasoning_effort,
            signal=turn_options.signal,
            network_access_enabled=options.network_access_enabled,
            web_search_enabled=options.web_search_enabled,
            approval_policy=options.approval_policy,
            additional_directories=options.additional_directories,
        )

        generator = self._exec.run(exec_args)

        try:
            # Stream JSONL lines and parse them
            async for line in generator:
                try:
                    parsed_dict = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Failed to parse item: {line}") from error

                # Parse dictionary into ThreadEvent dataclass
                event = parse_event(parsed_dict)

                # Capture thread ID when thread starts
                if event.type == "thread.started":
                    self._id = event.thread_id

                yield event
        finally:
            # Always cleanup the temporary schema file
            await output_schema_file.cleanup()

    async def run(self, input: Input, turn_options: TurnOptions | None = None) -> Turn:
        """
        Provides the input to the agent and returns the completed turn.

        This method buffers all events and returns the final result.

        Args:
            input: User input (string or list of UserInput)
            turn_options: Optional turn-specific options

        Returns:
            Turn containing completed items, final response, and usage

        Raises:
            RuntimeError: If the turn fails
        """
        if turn_options is None:
            turn_options = TurnOptions()

        generator = self._run_streamed_internal(input, turn_options)

        items: list[ThreadItem] = []
        final_response: str = ""
        usage: Usage | None = None
        turn_failure: str | None = None

        async for event in generator:
            if event.type == "item.completed":
                item = event.item
                # Extract final response from agent_message
                if item.type == "agent_message":
                    final_response = item.text
                items.append(item)
            elif event.type == "turn.completed":
                usage = event.usage
            elif event.type == "turn.failed":
                turn_failure = event.error.message
                break

        if turn_failure:
            raise RuntimeError(turn_failure)

        return Turn(items=items, final_response=final_response, usage=usage)


def _normalize_input(input: Input) -> tuple[str, list[str]]:
    """
    Normalize input to prompt string and image paths.

    Args:
        input: User input (string or list of UserInput)

    Returns:
        Tuple of (prompt string, list of image paths)
    """
    if isinstance(input, str):
        return (input, [])

    prompt_parts: list[str] = []
    images: list[str] = []

    for item in input:
        if isinstance(item, UserInputText) or (
            isinstance(item, dict) and item.get("type") == "text"
        ):
            text = item.text if isinstance(item, UserInputText) else item.get("text", "")
            prompt_parts.append(text)
        elif isinstance(item, UserInputImage) or (
            isinstance(item, dict) and item.get("type") == "local_image"
        ):
            path = item.path if isinstance(item, UserInputImage) else item.get("path", "")
            images.append(path)

    # Join prompt parts with double newline
    prompt = "\n\n".join(prompt_parts)

    return (prompt, images)
