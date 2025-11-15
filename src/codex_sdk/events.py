"""
Thread event type definitions.

Based on event types from codex-rs/exec/src/exec_events.rs
"""

from dataclasses import dataclass
from typing import Any, Literal

from .items import ThreadItem, parse_item


@dataclass
class ThreadStartedEvent:
    """Emitted when a new thread is started as the first event."""

    type: Literal["thread.started"]
    thread_id: str  # The identifier of the new thread. Can be used to resume the thread later


@dataclass
class TurnStartedEvent:
    """
    Emitted when a turn is started by sending a new prompt to the model.

    A turn encompasses all events that happen while the agent is processing the prompt.
    """

    type: Literal["turn.started"]


@dataclass
class Usage:
    """Describes the usage of tokens during a turn."""

    input_tokens: int  # The number of input tokens used during the turn
    cached_input_tokens: int  # The number of cached input tokens used during the turn
    output_tokens: int  # The number of output tokens used during the turn


@dataclass
class TurnCompletedEvent:
    """Emitted when a turn is completed. Typically right after the assistant's response."""

    type: Literal["turn.completed"]
    usage: Usage


@dataclass
class ThreadError:
    """Fatal error emitted by the stream."""

    message: str


@dataclass
class TurnFailedEvent:
    """Indicates that a turn failed with an error."""

    type: Literal["turn.failed"]
    error: ThreadError


@dataclass
class ItemStartedEvent:
    """Emitted when a new item is added to the thread. Typically the item is initially "in progress"."""

    type: Literal["item.started"]
    item: ThreadItem


@dataclass
class ItemUpdatedEvent:
    """Emitted when an item is updated."""

    type: Literal["item.updated"]
    item: ThreadItem


@dataclass
class ItemCompletedEvent:
    """Signals that an item has reached a terminal state—either success or failure."""

    type: Literal["item.completed"]
    item: ThreadItem


@dataclass
class ThreadErrorEvent:
    """Represents an unrecoverable error emitted directly by the event stream."""

    type: Literal["error"]
    message: str


# Top-level JSONL events emitted by codex exec

ThreadEvent = (
    ThreadStartedEvent
    | TurnStartedEvent
    | TurnCompletedEvent
    | TurnFailedEvent
    | ItemStartedEvent
    | ItemUpdatedEvent
    | ItemCompletedEvent
    | ThreadErrorEvent
)


def parse_event(data: dict[str, Any]) -> ThreadEvent:
    """
    Parse a dictionary into a ThreadEvent dataclass instance.

    Args:
        data: Dictionary representing a thread event

    Returns:
        Appropriate ThreadEvent dataclass instance

    Raises:
        ValueError: If the event type is unknown or data is invalid
    """

    event_type = data.get("type")

    if event_type == "thread.started":
        return ThreadStartedEvent(
            type="thread.started",
            thread_id=data["thread_id"],
        )
    elif event_type == "turn.started":
        return TurnStartedEvent(type="turn.started")
    elif event_type == "turn.completed":
        usage_data = data.get("usage", {})
        return TurnCompletedEvent(
            type="turn.completed",
            usage=Usage(
                input_tokens=usage_data["input_tokens"],
                cached_input_tokens=usage_data["cached_input_tokens"],
                output_tokens=usage_data["output_tokens"],
            ),
        )
    elif event_type == "turn.failed":
        error_data = data.get("error", {})
        return TurnFailedEvent(
            type="turn.failed",
            error=ThreadError(message=error_data["message"]),
        )
    elif event_type == "item.started":
        item_data = data.get("item", {})
        return ItemStartedEvent(
            type="item.started",
            item=parse_item(item_data),
        )
    elif event_type == "item.updated":
        item_data = data.get("item", {})
        return ItemUpdatedEvent(
            type="item.updated",
            item=parse_item(item_data),
        )
    elif event_type == "item.completed":
        item_data = data.get("item", {})
        return ItemCompletedEvent(
            type="item.completed",
            item=parse_item(item_data),
        )
    elif event_type == "error":
        return ThreadErrorEvent(
            type="error",
            message=data["message"],
        )
    else:
        raise ValueError(f"Unknown event type: {event_type}")
