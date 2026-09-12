#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shared.execution.subprocess_utils
---------------------------------
Cross-platform safe subprocess runner for ScholarFlow.
Prevents Windows GBK UnicodeDecodeError when child processes output scientific unicode symbols.
"""

import os
import sys
import subprocess
from typing import Any, Dict, List, Optional, Union


def run_safe_process(
    args: Union[List[str], str],
    *,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    env: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    """
    Run a subprocess with UTF-8 IO encoding and replacement on error.
    Automatically injects PYTHONIOENCODING=utf-8 into child environment.
    """
    proc_env = dict(os.environ)
    proc_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        proc_env.update(env)

    if text:
        return subprocess.run(
            args,
            capture_output=capture_output,
            text=True,
            encoding=encoding,
            errors=errors,
            env=proc_env,
            **kwargs,
        )
    return subprocess.run(
        args,
        capture_output=capture_output,
        env=proc_env,
        **kwargs,
    )
