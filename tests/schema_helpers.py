#!/usr/bin/env python3
"""ScholarFlow JSON Schema Validation Helpers (P0-03).

Provides robust local schema validation with $ref resolution using jsonschema
and referencing.Registry without making network calls.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    ValidationError = Exception

DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def build_schema_registry(schemas_dir: Optional[Path] = None) -> Any:
    """Build a referencing.Registry containing all canonical schemas in schemas/."""
    if not JSONSCHEMA_AVAILABLE:
        raise RuntimeError("jsonschema and referencing are required for real schema validation")

    sdir = schemas_dir or DEFAULT_SCHEMAS_DIR
    registry = Registry()

    for path in sdir.glob("*.schema.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        res = Resource.from_contents(data, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, res)
        registry = registry.with_resource(f"./{path.name}", res)
        if "$id" in data:
            registry = registry.with_resource(data["$id"], res)

    return registry


def get_validator(schema_name: str, schemas_dir: Optional[Path] = None) -> Any:
    """Instantiate a Draft202012Validator for the given schema filename."""
    if not JSONSCHEMA_AVAILABLE:
        raise RuntimeError("jsonschema is required for schema validation")

    sdir = schemas_dir or DEFAULT_SCHEMAS_DIR
    schema_path = sdir / schema_name
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = build_schema_registry(sdir)
    return Draft202012Validator(schema_data, registry=registry)


def validate_payload(payload: Dict[str, Any], schema_name: str, schemas_dir: Optional[Path] = None) -> None:
    """Validate a JSON payload against a canonical schema. Raises ValidationError on failure."""
    validator = get_validator(schema_name, schemas_dir)
    validator.validate(payload)

