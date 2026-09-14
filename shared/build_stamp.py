#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ScholarFlow build stamp (H-36 version visibility, panel decision B6).

Embeds the build provenance -- git commit, build timestamp, version -- as
module constants instead of a data file, so the stamp ships inside the
``shared`` package itself: ``setuptools.packages.find include = ["shared*"]``
already packages every module under ``shared/``, no packaging-config change is
needed, and an installed copy exposes exactly the same constants as the repo
copy. Any of the four skill CLIs answers ``--version`` with this stamp, which
makes deployment drift (e.g. an outdated copy under ``.agents\\skills``)
user-visible instead of silent.

Source-only checkouts that predate stamping (empty ``BUILD_COMMIT``) degrade
honestly to the ``<version>+dev`` fallback rather than pretending to carry a
build identity.

Pure Python standard library (zero external runtime dependencies).
"""

from __future__ import annotations

from typing import Any, Dict

try:  # Keep a single source of truth for the version number.
    from shared.version import PROJECT_VERSION as _PROJECT_VERSION
except ImportError:  # pragma: no cover - only when imported outside the package
    _PROJECT_VERSION = "0.6.6"

#: Semantic version of this build (mirrors shared/version.py).
STAMP_VERSION = _PROJECT_VERSION

#: Full git commit hash this build was stamped from. Empty or "dev" means the
#: checkout has not been stamped -> dev fallback.
BUILD_COMMIT = "19efaead37eb6260bfb977c77587902890c8b874"

#: UTC build timestamp, ISO-8601 with seconds and an explicit "Z" suffix.
BUILD_TIMESTAMP = "2026-09-13T23:49:11Z"

#: Marker constant for unstamped source checkouts.
_DEV_MARKER = "dev"

#: Length of the short commit hash shown in the user-visible line.
SHORT_COMMIT_LEN = 12


def is_stamp_available() -> bool:
    """Whether this module carries a real build stamp (not the dev fallback)."""
    commit = (BUILD_COMMIT or "").strip().lower()
    return bool(commit) and commit != _DEV_MARKER


def get_build_stamp() -> Dict[str, Any]:
    """Return the build stamp as a structured dict.

    Keys: ``version``, ``commit``, ``commit_short``, ``timestamp`` and
    ``source`` (``"embedded"`` for stamped builds, ``"dev"`` for unstamped
    source checkouts).
    """
    if is_stamp_available():
        return {
            "version": STAMP_VERSION,
            "commit": BUILD_COMMIT,
            "commit_short": BUILD_COMMIT[:SHORT_COMMIT_LEN],
            "timestamp": BUILD_TIMESTAMP,
            "source": "embedded",
        }
    return {
        "version": STAMP_VERSION + "+dev",
        "commit": "",
        "commit_short": "",
        "timestamp": "",
        "source": "dev",
    }


def format_version_line() -> str:
    """The one-line stamp printed by the skill CLIs' ``--version`` flag.

    Format: ``scholarflow <version> (build <short-hash> <timestamp>)``; the
    dev fallback is ``scholarflow <version>+dev``.
    """
    stamp = get_build_stamp()
    if stamp["source"] == "embedded":
        return "scholarflow %s (build %s %s)" % (
            stamp["version"],
            stamp["commit_short"],
            stamp["timestamp"],
        )
    return "scholarflow %s" % stamp["version"]


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    print(format_version_line())
