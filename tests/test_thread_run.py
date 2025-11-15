"""
Tests for Thread.run() method.

Based on TypeScript tests from tests/run.test.ts
"""

import os
import tempfile
from collections.abc import Iterator

import pytest

from codex_sdk.codex import Codex
from codex_sdk.codex_options import CodexOptions
from codex_sdk.thread_options import ThreadOptions
from codex_sdk.utils import find_codex_binary

from .codex_exec_spy import CodexExecSpyResult
from .responses_proxy import (
    SseResponseBody,
    assistant_message,
    response_completed,
    response_failed,
    response_started,
    sse,
    start_responses_test_proxy,
)

# Path to the codex binary
CODEX_EXEC_PATH = find_codex_binary()


@pytest.mark.asyncio
async def test_returns_thread_events() -> None:
    """Test that run() returns buffered thread events."""
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Hi!"), response_completed())]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        result = await thread.run("Hello, world!")

        # Verify items
        assert len(result.items) == 1
        item = result.items[0]
        assert item.type == "agent_message"
        assert item.text == "Hi!"
        assert isinstance(item.id, str)

        # Verify usage
        assert result.usage is not None
        assert result.usage.cached_input_tokens == 12
        assert result.usage.input_tokens == 42
        assert result.usage.output_tokens == 5

        # Verify finalResponse
        assert result.final_response == "Hi!"

        # Verify thread ID was set
        assert thread.id is not None
        assert isinstance(thread.id, str)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_sends_previous_items_when_run_called_twice() -> None:
    """Test that calling run() twice continues the same thread."""
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
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        result1 = await thread.run("first input")
        result2 = await thread.run("second input")

        # Verify first response
        assert result1.final_response == "First response"

        # Verify second response
        assert result2.final_response == "Second response"

        # Check that second request continues the same thread
        assert len(proxy.requests) >= 2
        second_request = proxy.requests[1]

        # Verify the second request contains the first assistant message
        assistant_entry = None
        for entry in second_request.json_data.get("input", []):
            if entry.get("role") == "assistant":
                assistant_entry = entry
                break

        assert assistant_entry is not None
        assistant_text = None
        for content_item in assistant_entry.get("content", []):
            if content_item.get("type") == "output_text":
                assistant_text = content_item.get("text")
                break

        assert assistant_text == "First response"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_resumes_thread_by_id() -> None:
    """Test that resumeThread() resumes an existing thread."""
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
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        original_thread = client.start_thread()
        await original_thread.run("first input")

        # Resume thread by ID
        assert original_thread.id is not None
        resumed_thread = client.resume_thread(original_thread.id)
        result = await resumed_thread.run("second input")

        # Verify thread IDs match
        assert resumed_thread.id == original_thread.id

        # Verify response
        assert result.final_response == "Second response"

        # Check that second request contains previous messages
        assert len(proxy.requests) >= 2
        second_request = proxy.requests[1]

        assistant_entry = None
        for entry in second_request.json_data.get("input", []):
            if entry.get("role") == "assistant":
                assistant_entry = entry
                break

        assert assistant_entry is not None

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_thread_options() -> None:
    """Test that ThreadOptions are passed to the CLI."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("With options", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(
            ThreadOptions(model="claude-3-5-sonnet-20241022", sandbox_mode="workspace-write")
        )
        result = await thread.run("apply options")

        # Verify execution completed
        assert result.final_response == "With options"

        # Verify request was made with model option
        assert len(proxy.requests) > 0
        request_data = proxy.requests[0].json_data
        assert request_data.get("model") == "claude-3-5-sonnet-20241022"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_combines_structured_text_input() -> None:
    """Test that multiple text inputs are combined with double newline."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Combined input applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        from codex_sdk.thread import UserInputText

        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        result = await thread.run(
            [
                UserInputText(type="text", text="Describe file changes"),
                UserInputText(type="text", text="Focus on impacted tests"),
            ]
        )

        # Verify execution completed
        assert len(result.items) > 0

        # Check that inputs were combined correctly
        assert len(proxy.requests) > 0
        request_data = proxy.requests[0].json_data
        last_user_message = request_data.get("input", [])[-1]
        content = last_user_message.get("content", [])
        if content:
            text = content[0].get("text", "")
            assert text == "Describe file changes\n\nFocus on impacted tests"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_thread_options_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that ThreadOptions are passed as CLI arguments."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Turn options applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(
            ThreadOptions(model="claude-3-5-sonnet-20241022", sandbox_mode="workspace-write")
        )
        await thread.run("apply options")

        # Verify CLI arguments
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]
        assert "--model" in command_args
        model_index = command_args.index("--model")
        assert command_args[model_index + 1] == "claude-3-5-sonnet-20241022"

        assert "--sandbox" in command_args
        sandbox_index = command_args.index("--sandbox")
        assert command_args[sandbox_index + 1] == "workspace-write"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_sets_codex_sdk_originator_header() -> None:
    """Test that the SDK sets the correct originator header."""
    proxy = await start_responses_test_proxy(
        [sse(response_started(), assistant_message("Hi!"), response_completed())]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        await thread.run("Hello, originator!")

        # Verify originator header
        assert len(proxy.requests) > 0
        originator_header = proxy.requests[0].headers.get("originator")

        assert originator_header is not None
        assert "codex_sdk_py" in originator_header

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_model_reasoning_effort_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that modelReasoningEffort is passed as --config argument."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Reasoning effort applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(ThreadOptions(model_reasoning_effort="high"))
        await thread.run("apply reasoning effort")

        # Verify CLI arguments contain model_reasoning_effort config
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]
        config_args = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--config" and i + 1 < len(command_args)
        ]
        assert any('model_reasoning_effort="high"' in arg for arg in config_args)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_network_access_enabled_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that networkAccessEnabled is passed as --config argument."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Network access enabled", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(ThreadOptions(network_access_enabled=True))
        await thread.run("test network access")

        # Verify CLI arguments contain network_access config
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]
        config_args = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--config" and i + 1 < len(command_args)
        ]
        assert any("sandbox_workspace_write.network_access=true" in arg for arg in config_args)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_web_search_enabled_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that webSearchEnabled is passed as --config argument."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Web search enabled", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(ThreadOptions(web_search_enabled=True))
        await thread.run("test web search")

        # Verify CLI arguments contain web_search config
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]
        config_args = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--config" and i + 1 < len(command_args)
        ]
        assert any("features.web_search_request=true" in arg for arg in config_args)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_passes_approval_policy_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that approvalPolicy is passed as --config argument."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Approval policy set", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(ThreadOptions(approval_policy="on-request"))
        await thread.run("test approval policy")

        # Verify CLI arguments contain approval_policy config
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]
        config_args = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--config" and i + 1 < len(command_args)
        ]
        assert any('approval_policy="on-request"' in arg for arg in config_args)

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_allows_overriding_env_passed_to_cli(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that custom env overrides os.environ."""

    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Custom env", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    # Set an env var that should NOT leak
    os.environ["CODEX_ENV_SHOULD_NOT_LEAK"] = "leak"

    try:
        client = Codex(
            CodexOptions(
                codex_path_override=CODEX_EXEC_PATH,
                base_url=proxy.url,
                api_key="test",
                env={"CUSTOM_ENV": "custom"},
            )
        )

        thread = client.start_thread()
        await thread.run("custom env")

        # Verify environment variables
        assert len(codex_exec_spy.envs) > 0
        spawn_env = codex_exec_spy.envs[0]
        assert spawn_env is not None

        assert spawn_env.get("CUSTOM_ENV") == "custom"
        assert "CODEX_ENV_SHOULD_NOT_LEAK" not in spawn_env
        assert spawn_env.get("OPENAI_BASE_URL") == proxy.url
        assert spawn_env.get("CODEX_API_KEY") == "test"
        assert "CODEX_INTERNAL_ORIGINATOR_OVERRIDE" in spawn_env

    finally:
        del os.environ["CODEX_ENV_SHOULD_NOT_LEAK"]
        await proxy.close()


@pytest.mark.skip(reason="--add-dir option not yet supported in codex-cli 0.58.0")
@pytest.mark.asyncio
async def test_passes_additional_directories_as_repeated_flags(
    codex_exec_spy: CodexExecSpyResult,
) -> None:
    """Test that additionalDirectories are passed as repeated --add-dir flags."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Additional directories applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(
            ThreadOptions(additional_directories=["../backend", "/tmp/shared"])
        )
        await thread.run("test additional dirs")

        # Verify CLI arguments contain all --add-dir flags
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]

        add_dir_values = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--add-dir" and i + 1 < len(command_args)
        ]
        assert add_dir_values == ["../backend", "/tmp/shared"]

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_writes_output_schema_to_temp_file(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that outputSchema is written to a temporary file and cleaned up."""

    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Structured response", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
        "additionalProperties": False,
    }

    try:
        from codex_sdk.turn_options import TurnOptions

        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        await thread.run("structured", TurnOptions(output_schema=schema))

        # Verify CLI arguments contain --output-schema
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]

        assert "--output-schema" in command_args
        schema_flag_index = command_args.index("--output-schema")
        schema_path = command_args[schema_flag_index + 1]
        assert isinstance(schema_path, str)

        # Verify temp file was cleaned up (should not exist after run)
        assert not os.path.exists(schema_path), "Temp schema file should be cleaned up"

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_forwards_images_to_exec(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that local images are passed as --image flags."""
    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Images applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    # Create temporary image files
    temp_dir = tempfile.mkdtemp(prefix="codex-images-")
    image_paths = [
        os.path.join(temp_dir, "first.png"),
        os.path.join(temp_dir, "second.jpg"),
    ]
    for i, image_path in enumerate(image_paths):
        with open(image_path, "w") as f:
            f.write(f"image-{i}")

    try:
        from codex_sdk.thread import UserInputImage, UserInputText

        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread()
        await thread.run(
            [
                UserInputText(type="text", text="describe the images"),
                UserInputImage(type="local_image", path=image_paths[0]),
                UserInputImage(type="local_image", path=image_paths[1]),
            ]
        )

        # Verify CLI arguments contain all --image flags
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]

        forwarded_images = [
            command_args[i + 1]
            for i, arg in enumerate(command_args)
            if arg == "--image" and i + 1 < len(command_args)
        ]
        assert forwarded_images == image_paths

    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)
        await proxy.close()


@pytest.mark.asyncio
async def test_runs_in_provided_working_directory(codex_exec_spy: CodexExecSpyResult) -> None:
    """Test that workingDirectory is passed as --cd argument."""

    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Working directory applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    working_directory = tempfile.mkdtemp(prefix="codex-working-dir-")

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(
            ThreadOptions(working_directory=working_directory, skip_git_repo_check=True)
        )
        await thread.run("use custom working directory")

        # Verify CLI arguments contain --cd
        assert len(codex_exec_spy.args) > 0
        command_args = codex_exec_spy.args[0]

        assert "--cd" in command_args
        cd_index = command_args.index("--cd")
        assert command_args[cd_index + 1] == working_directory

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_throws_if_working_directory_not_git_without_skip() -> None:
    """Test that an error is thrown if workingDirectory is not a git repo without skipGitRepoCheck."""

    proxy = await start_responses_test_proxy(
        [
            sse(
                response_started("response_1"),
                assistant_message("Working directory applied", "item_1"),
                response_completed("response_1"),
            )
        ]
    )

    working_directory = tempfile.mkdtemp(prefix="codex-working-dir-")

    try:
        from codex_sdk.exec import CodexExecError

        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )

        thread = client.start_thread(ThreadOptions(working_directory=working_directory))

        with pytest.raises(CodexExecError) as exc_info:
            await thread.run("use custom working directory")

        assert "trusted directory" in str(exc_info.value).lower()

    finally:
        await proxy.close()


@pytest.mark.asyncio
async def test_throws_error_on_turn_failures() -> None:
    """Test that run() throws error when turn fails."""

    def infinite_failed_responses() -> Iterator[SseResponseBody]:
        """Generate infinite failed responses after initial start."""
        yield sse(response_started("response_1"))
        while True:
            yield sse(response_failed("rate limit exceeded"))

    proxy = await start_responses_test_proxy(infinite_failed_responses())

    try:
        client = Codex(
            CodexOptions(codex_path_override=CODEX_EXEC_PATH, base_url=proxy.url, api_key="test")
        )
        thread = client.start_thread()

        with pytest.raises(RuntimeError) as exc_info:
            await thread.run("fail")

        # Verify error message contains expected text
        error_message = str(exc_info.value)
        assert "stream disconnected before completion:" in error_message

    finally:
        await proxy.close()
