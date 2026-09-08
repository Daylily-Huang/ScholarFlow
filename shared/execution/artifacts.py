#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared/execution/artifacts.py
------------------------------
Run artifact persistence and bundle loader for ScholarFlow execution depth runs.
Manages standard run artifacts under `runs/<run_id>/`:
  - execution_profile.json
  - protocol_snapshot.md
  - execution_receipt.json
  - pending_work.json
  - usage_ledger.jsonl

Pure Python standard library (zero external runtime dependencies).
"""

import json
import os
from typing import Any, Dict, List, Optional, Union

from .profiles import ExecutionProfile
from .budget import ExecutionReceipt


def save_run_artifacts(
    run_dir: str,
    profile: Union[Dict[str, Any], ExecutionProfile],
    snapshot_md: Optional[str] = None,
    receipt: Optional[Union[Dict[str, Any], ExecutionReceipt]] = None,
    pending_work: Optional[List[Any]] = None,
) -> Dict[str, str]:
    """
    Persist standard run artifacts to `runs/<run_id>/`.
    Returns a dictionary of generated file paths.
    """
    os.makedirs(run_dir, exist_ok=True)
    saved_files: Dict[str, str] = {}

    # 1. execution_profile.json
    profile_path = os.path.join(run_dir, "execution_profile.json")
    profile_data = profile.to_dict() if isinstance(profile, ExecutionProfile) else profile
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)
    saved_files["execution_profile"] = profile_path

    # 2. protocol_snapshot.md
    if snapshot_md:
        snapshot_path = os.path.join(run_dir, "protocol_snapshot.md")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(snapshot_md)
        saved_files["protocol_snapshot"] = snapshot_path

    # 3. execution_receipt.json
    if receipt:
        receipt_path = os.path.join(run_dir, "execution_receipt.json")
        receipt_data = receipt.to_dict() if isinstance(receipt, ExecutionReceipt) else receipt
        with open(receipt_path, "w", encoding="utf-8") as f:
            json.dump(receipt_data, f, indent=2, ensure_ascii=False)
        saved_files["execution_receipt"] = receipt_path

    # 4. pending_work.json
    if pending_work is not None:
        pending_path = os.path.join(run_dir, "pending_work.json")
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_work, f, indent=2, ensure_ascii=False)
        saved_files["pending_work"] = pending_path

    return saved_files


def load_run_profile(run_dir_or_file: str) -> Dict[str, Any]:
    """
    Load `execution_profile.json` from a run directory or file path.
    """
    if os.path.isdir(run_dir_or_file):
        profile_path = os.path.join(run_dir_or_file, "execution_profile.json")
    else:
        profile_path = run_dir_or_file

    if not os.path.exists(profile_path):
        raise FileNotFoundError(f"Execution profile not found: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)
