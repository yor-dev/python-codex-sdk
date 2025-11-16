# Python Codex SDK

Python SDK for OpenAI Codex CLI. This is a port of the official [TypeScript SDK](https://github.com/openai/codex/tree/main/sdk/typescript).

Based on commit [`3f1c4b9`](https://github.com/openai/codex/commit/3f1c4b9add8908936699ce47b17c94f8c9fd8018) (Nov 15, 2025) from the official repository.

## Overview

Embed the Codex agent in your workflows and apps.

The Python SDK wraps the bundled `codex` binary. It spawns the CLI and exchanges JSONL events over stdin/stdout.

## Installation

```bash
pip install python-codex-sdk
```

Requires Python 3.12+ and the [Codex CLI](https://developers.openai.com/codex/cli/).


## Testing

```bash
uv run pytest
```

Currently tested with `codex-cli 0.58.0`.

## License

Apache-2.0
