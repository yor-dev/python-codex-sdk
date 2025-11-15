"""
Mock HTTP server for testing Codex SDK.

Simulates the Codex API by returning SSE (Server-Sent Events) responses.
"""

import json
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any

from aiohttp import web


@dataclass
class RecordedRequest:
    """A recorded HTTP request."""

    body: str
    json_data: dict[str, Any]
    headers: dict[str, str]


@dataclass
class SseEvent:
    """A single SSE event."""

    type: str
    data: dict[str, Any]


@dataclass
class SseResponseBody:
    """Container for SSE events."""

    kind: str
    events: list[SseEvent]


@dataclass
class ResponsesProxy:
    """Mock HTTP server proxy."""

    url: str
    close: Callable[[], Awaitable[None]]
    requests: list[RecordedRequest]


DEFAULT_RESPONSE_ID = "resp_mock"
DEFAULT_MESSAGE_ID = "msg_mock"

DEFAULT_COMPLETED_USAGE = {
    "input_tokens": 42,
    "input_tokens_details": {"cached_tokens": 12},
    "output_tokens": 5,
    "output_tokens_details": None,
    "total_tokens": 47,
}


def format_sse_event(event: SseEvent) -> str:
    """Format an SSE event as a string."""
    event_data = {"type": event.type, **event.data}
    return f"event: {event.type}\ndata: {json.dumps(event_data)}\n\n"


async def start_responses_test_proxy(
    response_bodies: list[SseResponseBody] | Iterator[SseResponseBody], status_code: int = 200
) -> ResponsesProxy:
    """
    Start a mock HTTP server that returns SSE responses.

    Args:
        response_bodies: List or Iterator of SSE response bodies to return.
        status_code: HTTP status code to return (default: 200).

    Returns:
        ResponsesProxy with server URL and close function.
    """
    requests: list[RecordedRequest] = []

    # Convert list to iterator if needed
    response_iter = iter(response_bodies) if isinstance(response_bodies, list) else response_bodies

    async def handle_responses(request: web.Request) -> web.StreamResponse:
        """Handle POST /responses endpoint."""
        # Read and record request
        body = await request.text()
        json_data = json.loads(body)
        requests.append(
            RecordedRequest(body=body, json_data=json_data, headers=dict(request.headers))
        )

        # Get next response body
        try:
            response_body = next(response_iter)
        except StopIteration:
            return web.Response(status=500, text="Not enough responses provided")

        # Create SSE response
        response = web.StreamResponse(
            status=status_code,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)

        # Write SSE events
        for event in response_body.events:
            sse_text = format_sse_event(event)
            await response.write(sse_text.encode("utf-8"))

        await response.write_eof()
        return response

    # Create application
    app = web.Application()
    app.router.add_post("/responses", handle_responses)

    # Start server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)  # Random port
    await site.start()

    # Get the actual URL
    assert site._server is not None
    # _server.sockets is not in the type definition but exists at runtime
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{port}"

    async def close_server() -> None:
        """Close the server."""
        await runner.cleanup()

    return ResponsesProxy(url=url, close=close_server, requests=requests)


# Helper functions to create SSE events


def sse(*events: SseEvent) -> SseResponseBody:
    """Create an SSE response body from events."""
    return SseResponseBody(kind="sse", events=list(events))


def response_started(response_id: str = DEFAULT_RESPONSE_ID) -> SseEvent:
    """Create a response.created event."""
    return SseEvent(type="response.created", data={"response": {"id": response_id}})


def assistant_message(text: str, item_id: str = DEFAULT_MESSAGE_ID) -> SseEvent:
    """Create a response.output_item.done event with an assistant message."""
    return SseEvent(
        type="response.output_item.done",
        data={
            "item": {
                "type": "message",
                "role": "assistant",
                "id": item_id,
                "content": [{"type": "output_text", "text": text}],
            }
        },
    )


def shell_call() -> SseEvent:
    """Create a response.output_item.done event with a shell function call."""
    import random
    import string

    call_id = "call_id" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    command = ["bash", "-lc", "echo 'Hello, world!'"]

    return SseEvent(
        type="response.output_item.done",
        data={
            "item": {
                "type": "function_call",
                "call_id": call_id,
                "name": "shell",
                "arguments": json.dumps({"command": command, "timeout_ms": 100}),
            }
        },
    )


def response_completed(
    response_id: str = DEFAULT_RESPONSE_ID, usage: dict[str, Any] | None = None
) -> SseEvent:
    """Create a response.completed event."""
    if usage is None:
        usage = DEFAULT_COMPLETED_USAGE

    return SseEvent(
        type="response.completed",
        data={
            "response": {
                "id": response_id,
                "usage": {
                    "input_tokens": usage["input_tokens"],
                    "input_tokens_details": usage["input_tokens_details"],
                    "output_tokens": usage["output_tokens"],
                    "output_tokens_details": usage["output_tokens_details"],
                    "total_tokens": usage["total_tokens"],
                },
            }
        },
    )


def response_failed(error_message: str) -> SseEvent:
    """Create an error event."""
    return SseEvent(
        type="error",
        data={"error": {"code": "rate_limit_exceeded", "message": error_message}},
    )
