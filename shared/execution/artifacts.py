#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared/execution/artifacts.py
------------------------------
Run artifact persistence and bundle loader for ScholarFlow execution-depth runs.

Manages the standard run bundle under ``runs/<run_id>/``:
  - execution_profile.json    (canonical RunExecutionConfig, schema-validated)
  - protocol_snapshot.md
  - execution_receipt.json
  - pending_work.json
  - usage_ledger.jsonl

Writes are atomic (temp file + ``os.replace``) so a crash cannot leave a
half-written configuration behind, and every saved configuration is validated
before a single byte reaches disk (R04).

Pure Python standard library (zero external runtime dependencies).
"""

import json
import os
from typing import Any, Dict, List, Optional, Union

from .budget import ExecutionReceipt
from .config import RUN_CONFIG_SCHEMA_VERSION, RunExecutionConfig
from .profiles import ExecutionProfile

#: Files that make up one coherent run bundle. Recovery must only accept a
#: consistent set, so a stale receipt cannot be paired with a fresh profile.
RUN_BUNDLE_FILES = (
    "execution_profile.json",
    "protocol_snapshot.md",
    "execution_receipt.json",
    "pending_work.json",
)


def _atomic_write_text(path: str, text: str) -> str:
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp_path, path)
    return path


def _atomic_write_json(path: str, payload: Any) -> str:
    return _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))


def _as_run_config(
    profile: Union[Dict[str, Any], ExecutionProfile, RunExecutionConfig],
    run_id: Optional[str] = None,
) -> RunExecutionConfig:
    """Normalise any accepted profile input into a canonical run configuration.

    A bare :class:`ExecutionProfile` preset is *not* a confirmed configuration,
    so it is wrapped with a ``pending`` selection record instead of being
    silently presented as authorised (R04).
    """
    if isinstance(profile, RunExecutionConfig):
        return profile
    if isinstance(profile, ExecutionProfile):
        return RunExecutionConfig.from_profile(profile, run_id=run_id)
    if isinstance(profile, dict):
        if "selection" in profile or "profile_version" in profile:
            config = RunExecutionConfig.from_dict(profile)
            if run_id:
                config.run_id = run_id
            return config
        # Backward compatibility: an old flat preset payload is converted
        # explicitly and marked pending, never promoted to confirmed.
        depth = profile.get("depth", profile.get("execution_depth"))
        if depth is None:
            raise ValueError("Execution profile payload has no depth field")
        from shared.execution.profiles import get_profile

        config = RunExecutionConfig.from_profile(get_profile(depth), run_id=run_id)
        return config
    raise TypeError("Unsupported execution profile type: %r" % (type(profile).__name__,))


def save_run_artifacts(
    run_dir: str,
    profile: Union[Dict[str, Any], ExecutionProfile, RunExecutionConfig],
    snapshot_md: Optional[str] = None,
    receipt: Optional[Union[Dict[str, Any], ExecutionReceipt]] = None,
    pending_work: Optional[List[Any]] = None,
    validate: bool = True,
) -> Dict[str, str]:
    """Persist the standard run artifacts to ``runs/<run_id>/``.

    Returns a dictionary of generated file paths. Raises ``ValueError`` if the
    configuration does not satisfy its canonical schema contract.
    """
    config = _as_run_config(profile)
    problems = config.validate() if validate else []
    if problems:
        raise ValueError("Refusing to save an invalid run configuration: %s" % "; ".join(problems))

    os.makedirs(run_dir, exist_ok=True)
    saved_files: Dict[str, str] = {}

    saved_files["execution_profile"] = _atomic_write_json(
        os.path.join(run_dir, "execution_profile.json"), config.to_dict()
    )

    if snapshot_md:
        saved_files["protocol_snapshot"] = _atomic_write_text(
            os.path.join(run_dir, "protocol_snapshot.md"), snapshot_md
        )

    if receipt:
        receipt_data = receipt.to_dict() if isinstance(receipt, ExecutionReceipt) else receipt
        saved_files["execution_receipt"] = _atomic_write_json(
            os.path.join(run_dir, "execution_receipt.json"), receipt_data
        )

    if pending_work is not None:
        saved_files["pending_work"] = _atomic_write_json(
            os.path.join(run_dir, "pending_work.json"), pending_work
        )

    return saved_files


def load_run_artifacts(run_dir: str) -> Dict[str, Any]:
    """Load a coherent run bundle, validating the configuration on the way in."""
    if not os.path.isdir(run_dir):
        raise FileNotFoundError("Run directory not found: %s" % run_dir)

    bundle: Dict[str, Any] = {"run_dir": run_dir}
    bundle["execution_profile"] = RunExecutionConfig.load(run_dir)

    snapshot_path = os.path.join(run_dir, "protocol_snapshot.md")
    if os.path.exists(snapshot_path):
        with open(snapshot_path, "r", encoding="utf-8") as handle:
            bundle["protocol_snapshot"] = handle.read()

    receipt_path = os.path.join(run_dir, "execution_receipt.json")
    if os.path.exists(receipt_path):
        with open(receipt_path, "r", encoding="utf-8") as handle:
            bundle["execution_receipt"] = json.load(handle)

    pending_path = os.path.join(run_dir, "pending_work.json")
    if os.path.exists(pending_path):
        with open(pending_path, "r", encoding="utf-8") as handle:
            bundle["pending_work"] = json.load(handle)

    # A run_id echoed by the receipt must agree with the configuration, so that
    # recovery can never resume one run with another run's receipt.
    receipt = bundle.get("execution_receipt")
    if isinstance(receipt, dict):
        receipt_run_id = receipt.get("run_id")
        if receipt_run_id and receipt_run_id != bundle["execution_profile"].run_id:
            raise ValueError(
                "Run bundle is inconsistent: receipt run_id %r does not match profile run_id %r"
                % (receipt_run_id, bundle["execution_profile"].run_id)
            )

    return bundle


def load_run_profile(run_dir_or_file: str) -> Dict[str, Any]:
    """Load and validate ``execution_profile.json`` from a run directory or path."""
    return RunExecutionConfig.load(run_dir_or_file).to_dict()
