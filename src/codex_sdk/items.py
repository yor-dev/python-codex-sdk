"""
Thread item type definitions.

Based on item types from codex-rs/exec/src/exec_events.rs
"""

from dataclasses import dataclass
from typing import Any, Literal

# CommandExecutionItem related types

CommandExecutionStatus = Literal["in_progress", "completed", "failed"]


@dataclass
class CommandExecutionItem:
    """A command executed by the agent."""

    id: str
    type: Literal["command_execution"]
    command: str  # The command line executed by the agent
    aggregated_output: str  # Aggregated stdout and stderr captured while the command was running
    status: CommandExecutionStatus  # Current status of the command execution
    exit_code: int | None = None  # Set when the command exits; omitted while still running


# FileChangeItem related types

PatchChangeKind = Literal["add", "delete", "update"]


@dataclass
class FileUpdateChange:
    """Indicates the type of the file change."""

    path: str
    kind: PatchChangeKind


PatchApplyStatus = Literal["completed", "failed"]


@dataclass
class FileChangeItem:
    """A set of file changes by the agent. Emitted once the patch succeeds or fails."""

    id: str
    type: Literal["file_change"]
    changes: list[FileUpdateChange]  # Individual file changes that comprise the patch
    status: PatchApplyStatus  # Whether the patch ultimately succeeded or failed


# McpToolCallItem related types

McpToolCallStatus = Literal["in_progress", "completed", "failed"]


@dataclass
class McpToolCallResult:
    """Result payload returned by the MCP server for successful calls."""

    content: list[Any]  # List of MCP ContentBlocks. Detailed types will be defined later
    structured_content: Any


@dataclass
class McpToolCallError:
    """Error message reported for failed calls."""

    message: str


@dataclass
class McpToolCallItem:
    """
    Represents a call to an MCP tool.

    The item starts when the invocation is dispatched and completes when the MCP server
    reports success or failure.
    """

    id: str
    type: Literal["mcp_tool_call"]
    server: str  # Name of the MCP server handling the request
    tool: str  # The tool invoked on the MCP server
    arguments: Any  # Arguments forwarded to the tool invocation
    status: McpToolCallStatus  # Current status of the tool invocation
    result: McpToolCallResult | None = (
        None  # Result payload returned by the MCP server for successful calls
    )
    error: McpToolCallError | None = None  # Error message reported for failed calls


# AgentMessageItem


@dataclass
class AgentMessageItem:
    """Response from the agent. Either natural-language text or JSON when structured output is requested."""

    id: str
    type: Literal["agent_message"]
    text: str  # Either natural-language text or JSON when structured output is requested


# ReasoningItem


@dataclass
class ReasoningItem:
    """Agent's reasoning summary."""

    id: str
    type: Literal["reasoning"]
    text: str


# WebSearchItem


@dataclass
class WebSearchItem:
    """Captures a web search request. Completes when results are returned to the agent."""

    id: str
    type: Literal["web_search"]
    query: str


# ErrorItem


@dataclass
class ErrorItem:
    """Describes a non-fatal error surfaced as an item."""

    id: str
    type: Literal["error"]
    message: str


# TodoListItem related types


@dataclass
class TodoItem:
    """An item in the agent's to-do list."""

    text: str
    completed: bool


@dataclass
class TodoListItem:
    """
    Tracks the agent's running to-do list.

    Starts when the plan is issued, updates as steps change, and completes when the turn ends.
    """

    id: str
    type: Literal["todo_list"]
    items: list[TodoItem]


# Canonical union of thread items

ThreadItem = (
    AgentMessageItem
    | ReasoningItem
    | CommandExecutionItem
    | FileChangeItem
    | McpToolCallItem
    | WebSearchItem
    | TodoListItem
    | ErrorItem
)


def parse_item(data: dict[str, Any]) -> ThreadItem:
    """
    Parse a dictionary into a ThreadItem dataclass instance.

    Args:
        data: Dictionary representing a thread item

    Returns:
        Appropriate ThreadItem dataclass instance

    Raises:
        ValueError: If the item type is unknown or data is invalid
    """
    item_type = data.get("type")

    if item_type == "agent_message":
        return AgentMessageItem(
            id=data["id"],
            type="agent_message",
            text=data["text"],
        )
    elif item_type == "reasoning":
        return ReasoningItem(
            id=data["id"],
            type="reasoning",
            text=data["text"],
        )
    elif item_type == "command_execution":
        return CommandExecutionItem(
            id=data["id"],
            type="command_execution",
            command=data["command"],
            aggregated_output=data["aggregated_output"],
            status=data["status"],
            exit_code=data.get("exit_code"),
        )
    elif item_type == "file_change":
        changes = [
            FileUpdateChange(path=c["path"], kind=c["kind"]) for c in data.get("changes", [])
        ]
        return FileChangeItem(
            id=data["id"],
            type="file_change",
            changes=changes,
            status=data["status"],
        )
    elif item_type == "mcp_tool_call":
        result = None
        if "result" in data and data["result"] is not None:
            result = McpToolCallResult(
                content=data["result"]["content"],
                structured_content=data["result"]["structured_content"],
            )
        error = None
        if "error" in data and data["error"] is not None:
            error = McpToolCallError(message=data["error"]["message"])
        return McpToolCallItem(
            id=data["id"],
            type="mcp_tool_call",
            server=data["server"],
            tool=data["tool"],
            arguments=data["arguments"],
            status=data["status"],
            result=result,
            error=error,
        )
    elif item_type == "web_search":
        return WebSearchItem(
            id=data["id"],
            type="web_search",
            query=data["query"],
        )
    elif item_type == "todo_list":
        items = [TodoItem(text=item["text"], completed=item["completed"]) for item in data["items"]]
        return TodoListItem(
            id=data["id"],
            type="todo_list",
            items=items,
        )
    elif item_type == "error":
        return ErrorItem(
            id=data["id"],
            type="error",
            message=data["message"],
        )
    else:
        raise ValueError(f"Unknown item type: {item_type}")
