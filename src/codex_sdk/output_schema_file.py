"""
Output schema file utilities.

Handles writing output schemas to temporary files for CLI consumption.
"""

import contextlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class OutputSchemaFile:
    """Represents a temporary output schema file."""

    schema_path: str | None = None  # Path to the schema file
    _temp_dir: str | None = None  # Internal: temporary directory path

    async def cleanup(self) -> None:
        """Remove the temporary directory and its contents."""
        if self._temp_dir:
            with contextlib.suppress(Exception):
                shutil.rmtree(self._temp_dir)


async def create_output_schema_file(schema: dict[str, Any] | None) -> OutputSchemaFile:
    """
    Create a temporary file containing the output schema.

    Args:
        schema: JSON schema object describing expected agent output (dict or None)

    Returns:
        OutputSchemaFile with schema_path and cleanup method

    Raises:
        ValueError: If schema is not a plain JSON object (dict)
    """
    if schema is None:
        return OutputSchemaFile()

    if not _is_json_object(schema):
        raise ValueError("outputSchema must be a plain JSON object")

    temp_dir = tempfile.mkdtemp(prefix="codex-output-schema-")
    schema_path = str(Path(temp_dir) / "schema.json")

    try:
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(schema, f)
        return OutputSchemaFile(schema_path=schema_path, _temp_dir=temp_dir)
    except Exception as error:
        # Cleanup on error
        with contextlib.suppress(Exception):
            shutil.rmtree(temp_dir)
        raise error


def _is_json_object(value: Any) -> bool:
    """Check if value is a plain JSON object (dict, not list or None)."""
    return isinstance(value, dict)
