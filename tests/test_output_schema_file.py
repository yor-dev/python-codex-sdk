"""
Tests for output_schema_file module.
"""

import json
from pathlib import Path

import pytest

from codex_sdk.output_schema_file import (
    OutputSchemaFile,
    _is_json_object,
    create_output_schema_file,
)


@pytest.mark.asyncio
async def test_create_output_schema_file_with_none() -> None:
    """Test that None schema returns OutputSchemaFile with no path."""
    result = await create_output_schema_file(None)

    assert result.schema_path is None
    assert result._temp_dir is None

    # Cleanup should not raise
    await result.cleanup()


@pytest.mark.asyncio
async def test_create_output_schema_file_with_dict() -> None:
    """Test that dict schema creates a temporary file with JSON content."""
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}

    result = await create_output_schema_file(schema)

    try:
        # Verify schema_path is set
        assert result.schema_path is not None
        assert result._temp_dir is not None

        # Verify file exists
        path = Path(result.schema_path)
        assert path.exists()
        assert path.name == "schema.json"

        # Verify JSON content
        with open(result.schema_path, encoding="utf-8") as f:
            loaded_schema = json.load(f)
        assert loaded_schema == schema
    finally:
        # Cleanup
        await result.cleanup()

    # Verify cleanup removed the file
    assert not Path(result.schema_path).exists()


@pytest.mark.asyncio
async def test_create_output_schema_file_with_list_raises_error() -> None:
    """Test that list schema raises ValueError."""
    with pytest.raises(ValueError, match="outputSchema must be a plain JSON object"):
        await create_output_schema_file([1, 2, 3])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_create_output_schema_file_with_string_raises_error() -> None:
    """Test that string schema raises ValueError."""
    with pytest.raises(ValueError, match="outputSchema must be a plain JSON object"):
        await create_output_schema_file("not a dict")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cleanup_is_idempotent() -> None:
    """Test that cleanup can be called multiple times without error."""
    schema = {"type": "string"}
    result = await create_output_schema_file(schema)

    await result.cleanup()
    # Should not raise even if already cleaned up
    await result.cleanup()


@pytest.mark.asyncio
async def test_cleanup_on_empty_output_schema_file() -> None:
    """Test that cleanup works on OutputSchemaFile with no temp_dir."""
    result = OutputSchemaFile()
    # Should not raise
    await result.cleanup()


def test_is_json_object_with_dict() -> None:
    """Test that _is_json_object returns True for dict."""
    assert _is_json_object({"key": "value"}) is True
    assert _is_json_object({}) is True


def test_is_json_object_with_non_dict() -> None:
    """Test that _is_json_object returns False for non-dict values."""
    assert _is_json_object([1, 2, 3]) is False
    assert _is_json_object("string") is False
    assert _is_json_object(123) is False
    assert _is_json_object(None) is False
    assert _is_json_object(True) is False
