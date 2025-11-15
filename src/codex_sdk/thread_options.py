"""
Thread creation options.
"""

from dataclasses import dataclass
from typing import Literal

ApprovalMode = Literal["never", "on-request", "on-failure", "untrusted"]

SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]

ModelReasoningEffort = Literal["minimal", "low", "medium", "high"]


@dataclass
class ThreadOptions:
    """Options for creating a thread."""

    model: str | None = None  # Model identifier to use
    sandbox_mode: SandboxMode | None = None  # Sandbox mode for file operations
    working_directory: str | None = None  # Working directory for the thread
    skip_git_repo_check: bool | None = None  # Skip git repository check
    model_reasoning_effort: ModelReasoningEffort | None = None  # Reasoning effort level
    network_access_enabled: bool | None = None  # Enable network access
    web_search_enabled: bool | None = None  # Enable web search
    approval_policy: ApprovalMode | None = None  # Approval policy for operations
    additional_directories: list[str] | None = None  # Additional directories to include
