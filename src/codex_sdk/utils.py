"""
Custom utility functions.
"""

import shutil


def find_codex_binary() -> str:
    """
    Find the codex binary in PATH.

    Returns:
        Path to the codex binary

    Raises:
        RuntimeError: If codex binary is not found in PATH
    """
    codex_path = shutil.which("codex")
    if not codex_path:
        raise RuntimeError(
            "codex binary not found in PATH. Please install codex CLI first. "
            "See: https://docs.claude.com/en/docs/claude-code"
        )
    return codex_path
