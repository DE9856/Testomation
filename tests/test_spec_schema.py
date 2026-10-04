"""The spec schema's examples, checked from Python (runner/scripts checks them from TS — D31)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
validator = Draft202012Validator(json.loads((SCHEMAS / "test-spec.schema.json").read_text()))


def examples(kind: str) -> list[Path]:
    return sorted((SCHEMAS / "examples" / kind).glob("*.json"))


def test_schema_is_valid():
    Draft202012Validator.check_schema(validator.schema)


@pytest.mark.parametrize("path", examples("valid"), ids=lambda p: p.name)
def test_valid_examples_pass(path):
    validator.validate(json.loads(path.read_text()))


@pytest.mark.parametrize("path", examples("invalid"), ids=lambda p: p.name)
def test_invalid_examples_fail(path):
    assert not validator.is_valid(json.loads(path.read_text()))
