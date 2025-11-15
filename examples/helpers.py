import os

from codex_sdk.utils import find_codex_binary


def codex_path_override() -> str | None:
    """
    Get codex executable path from environment or default location.
    Returns the path to the codex binary for development/testing.
    """
    if env_path := os.environ.get("CODEX_EXECUTABLE"):
        return env_path

    # find_codex_binary() will raise RuntimeError if not found
    try:
        return find_codex_binary()
    except RuntimeError:
        return None
