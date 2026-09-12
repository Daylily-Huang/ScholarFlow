#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schema_gate.py — ScholarFlow canonical schema gate (production).

Why this exists
---------------
`SKILL.md` §四 required every extraction JSON to be "strictly validated against
`schemas/extraction_result.schema.json`", and `extraction_pipeline.py`'s
docstring claimed to do exactly that. Measured on 2026-09-11: no production code
path imported `jsonschema` at all, and the builder constructed its dict and
returned it — the claim was documentation only. This module gives the contract a
real execution point.

Design constraints
------------------
* Standard library only as a hard floor: the gate must run wherever the pipeline
  runs, including environments without `jsonschema` (this repo's own CI installs
  it, but a user's machine may not).
* When `jsonschema` + `referencing` are present, it escalates to full Draft 2020-12
  validation with proper `$ref` resolution.
* When they are absent, it falls back to a structural validator that checks the
  parts of the contract that carry meaning (required keys, enums, types, $ref to
  sibling schema files). It is weaker, and it says so in `mode`.

Not in scope: semantic truth. Schema validation cannot tell whether
`extracted_value` is faithful to `verbatim_quote` — `"95.4%"` and `"55.4%"` are
both valid strings. That check lives in `quote_audit.py` (value alignment).
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMAS_DIR = REPO_ROOT / "schemas"

try:  # optional enhancement
    from jsonschema import Draft202012Validator  # type: ignore
    from referencing import Registry, Resource  # type: ignore
    from referencing.jsonschema import DRAFT202012  # type: ignore
    _FULL = True
except Exception:  # noqa: BLE001
    Draft202012Validator = None  # type: ignore
    Registry = Resource = DRAFT202012 = None  # type: ignore
    _FULL = False


class SchemaGateError(Exception):
    """Raised when a payload does not satisfy its canonical schema."""


# --------------------------------------------------------------------------- #
# Full validation (jsonschema available)
# --------------------------------------------------------------------------- #

def _registry(schemas_dir: Path):
    reg = Registry()
    for f in sorted(schemas_dir.glob("*.schema.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        uri = f.name
        reg = reg.with_resource(uri, Resource.from_contents(doc, default_specification=DRAFT202012))
        # allow "$ref": "./name.schema.json" and bare "name.schema.json"
        reg = reg.with_resource("./" + f.name, Resource.from_contents(doc, default_specification=DRAFT202012))
    return reg


def _full_errors(payload: Any, schema_name: str, schemas_dir: Path) -> List[str]:
    schema_path = schemas_dir / schema_name
    if not schema_path.exists():
        raise SchemaGateError("schema not found: %s" % schema_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    reg = _registry(schemas_dir)
    validator = Draft202012Validator(schema, registry=reg)
    errs = []
    for e in sorted(validator.iter_errors(payload), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "<root>"
        errs.append("%s: %s" % (loc, e.message))
    return errs


# --------------------------------------------------------------------------- #
# Structural fallback (no jsonschema) — covers meaning-carrying constraints
# --------------------------------------------------------------------------- #

_TYPE_MAP = {
    "object": dict, "array": list, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "null": type(None),
}


def _type_ok(value: Any, spec: Any) -> bool:
    if spec is None:
        return True
    names = spec if isinstance(spec, list) else [spec]
    for n in names:
        if n == "null" and value is None:
            return True
        py = _TYPE_MAP.get(n)
        if py is None:
            continue
        if n == "integer" and isinstance(value, bool):
            continue
        if n == "number" and isinstance(value, bool):
            continue
        if isinstance(value, py):
            return True
    return False


def _walk(payload: Any, schema: Dict[str, Any], path: str, schemas_dir: Path,
          errs: List[str], depth: int = 0) -> None:
    if depth > 40 or not isinstance(schema, dict):
        return

    ref = schema.get("$ref")
    if isinstance(ref, str):
        target = schemas_dir / Path(ref).name
        if target.exists():
            sub = json.loads(target.read_text(encoding="utf-8"))
            _walk(payload, sub, path, schemas_dir, errs, depth + 1)
        else:
            errs.append("%s: unresolved $ref %s" % (path, ref))
        return

    if "const" in schema and payload != schema["const"]:
        errs.append("%s: expected const %r, got %r" % (path, schema["const"], payload))

    if "enum" in schema and payload not in schema["enum"]:
        errs.append("%s: %r not in enum %s" % (path, payload, schema["enum"]))

    if not _type_ok(payload, schema.get("type")):
        errs.append("%s: type %s does not match %r" % (path, type(payload).__name__, schema.get("type")))
        return

    if isinstance(payload, dict):
        for req in schema.get("required", []) or []:
            if req not in payload:
                errs.append("%s: missing required property '%s'" % (path, req))
        props = schema.get("properties") or {}
        for k, v in payload.items():
            if k in props:
                _walk(v, props[k], "%s/%s" % (path, k), schemas_dir, errs, depth + 1)

    if isinstance(payload, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(payload):
            _walk(item, schema["items"], "%s[%d]" % (path, i), schemas_dir, errs, depth + 1)


def _structural_errors(payload: Any, schema_name: str, schemas_dir: Path) -> List[str]:
    schema_path = schemas_dir / schema_name
    if not schema_path.exists():
        raise SchemaGateError("schema not found: %s" % schema_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errs: List[str] = []
    _walk(payload, schema, "<root>", schemas_dir, errs)
    return errs


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def validate(payload: Any, schema_name: str = "extraction_result.schema.json",
             schemas_dir: Optional[Path] = None) -> Tuple[bool, str, List[str]]:
    """Validate `payload`; return (ok, mode, errors).

    mode is "draft2020-12+$ref" when jsonschema is available, else
    "structural-fallback" (weaker; the caller should surface this).
    """
    schemas_dir = schemas_dir or DEFAULT_SCHEMAS_DIR
    if _FULL:
        errs = _full_errors(payload, schema_name, schemas_dir)
        return (not errs), "draft2020-12+$ref", errs
    errs = _structural_errors(payload, schema_name, schemas_dir)
    return (not errs), "structural-fallback", errs


def require_valid(payload: Any, schema_name: str = "extraction_result.schema.json",
                  schemas_dir: Optional[Path] = None) -> str:
    """Validate or raise SchemaGateError. Returns the mode used."""
    ok, mode, errs = validate(payload, schema_name, schemas_dir)
    if not ok:
        raise SchemaGateError(
            "payload violates %s (%d error(s), mode=%s):\n  - %s"
            % (schema_name, len(errs), mode, "\n  - ".join(errs[:25])))
    return mode


# --------------------------------------------------------------------------- #
# Cross-record referential integrity (handoff contract, F4)
# --------------------------------------------------------------------------- #

def check_evidence_chain(records: List[Dict[str, Any]],
                         verdicts: Optional[List[Dict[str, Any]]] = None,
                         min_overlap: float = 1.0) -> List[str]:
    """Verify every record is covered by the auditor's verdict list.

    Measured failure: specialist used ids like `SF2-A1-C1-E1-abs-en`, the auditor
    reported `'G1 T105'`, and the two sets had ZERO ids in common — so no claim in
    the final report could be traced back to a record. A handoff without a shared
    key is not a handoff.
    """
    problems: List[str] = []
    ids = [r.get("evidence_id") or r.get("record_id") for r in records]
    ids = [i for i in ids if i]
    if not ids:
        return ["no evidence_id/record_id present on any record"]
    if verdicts is None:
        return problems
    vids = set()
    for v in verdicts:
        for key in ("evidence_id", "record_id", "id"):
            if v.get(key):
                vids.add(v[key])
        for key in ("evidence_ids", "record_ids", "reviewed"):
            val = v.get(key)
            if isinstance(val, list):
                vids.update(x for x in val if isinstance(x, str))
    if not vids:
        problems.append("auditor verdicts carry no evidence ids: handoff cannot be traced")
        return problems
    orphans = [i for i in ids if i not in vids]
    if orphans:
        ratio = 1.0 - len(orphans) / len(ids)
        problems.append(
            "auditor covered %.0f%% of records (%d orphan(s), e.g. %s); "
            "required >= %.0f%%" % (ratio * 100, len(orphans), orphans[:5], min_overlap * 100))
    return problems


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Validate a ScholarFlow JSON payload against a canonical schema")
    ap.add_argument("-i", "--input", required=True)
    ap.add_argument("--schema", default="extraction_result.schema.json")
    ap.add_argument("--schemas-dir", default=None)
    a = ap.parse_args()
    data = json.loads(Path(a.input).read_text(encoding="utf-8"))
    sdir = Path(a.schemas_dir) if a.schemas_dir else None
    ok, mode, errs = validate(data, a.schema, sdir)
    print("mode=%s  ok=%s  errors=%d" % (mode, ok, len(errs)))
    for e in errs[:40]:
        print("  -", e)
    raise SystemExit(0 if ok else 1)
