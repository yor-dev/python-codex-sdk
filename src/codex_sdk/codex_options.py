"""
Codex instance creation options.
"""

from dataclasses import dataclass


@dataclass
class CodexOptions:
    """Options for creating a Codex instance."""

    codex_path_override: str | None = None  # Override path to the codex binary
    base_url: str | None = None  # Base URL for the Codex API
    api_key: str | None = None  # API key for authentication
    env: dict[str, str] | None = (
        None  # Environment variables passed to the Codex CLI process. When provided, the SDK will not inherit variables from os.environ
    )
