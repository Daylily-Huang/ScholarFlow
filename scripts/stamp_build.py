#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-stamp ``shared/build_stamp.py`` from the current git HEAD (2026-09-15).

H-36 embedded a build stamp so deployment drift becomes user-visible through the
four skill CLIs' ``--version``. That only works while the stamped commit still
exists in history: a rebase, squash, or amended commit leaves the stamp pointing
at an object git can no longer resolve, and ``--version`` keeps printing a hash
that proves nothing (measured 2026-09-15: ``BUILD_COMMIT`` pointed at
``cb343aa...``, which ``git cat-file -e`` could not read).

This tool is the release step that keeps the stamp honest:

    python scripts/stamp_build.py            # re-stamp from HEAD
    python scripts/stamp_build.py --check    # verify the stamped commit is reachable (rc 1 if not)

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP_PATH = os.path.join(REPO_ROOT, "shared", "build_stamp.py")

_COMMIT_RE = re.compile(r'^BUILD_COMMIT = "([^"]*)"$', re.M)
_TIMESTAMP_RE = re.compile(r'^BUILD_TIMESTAMP = "([^"]*)"$', re.M)


def _git(*args):
    """Run git in the repo root; returns CompletedProcess (never raises)."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def current_commit():
    proc = _git("rev-parse", "HEAD")
    if proc.returncode != 0:
        raise SystemExit("[ERROR] git rev-parse HEAD failed: %s"
                         % ((proc.stderr or "").strip() or proc.returncode))
    return proc.stdout.strip()


def commit_is_reachable(sha):
    """Whether ``sha`` names a commit object this repository can still read."""
    sha = (sha or "").strip()
    if not sha:
        return False
    return _git("cat-file", "-e", sha + "^{commit}").returncode == 0


def read_stamp():
    src = io.open(STAMP_PATH, encoding="utf-8").read()
    commit = _COMMIT_RE.search(src)
    timestamp = _TIMESTAMP_RE.search(src)
    return (commit.group(1) if commit else None,
            timestamp.group(1) if timestamp else None)


def restamp(commit=None, timestamp=None):
    """Rewrite BUILD_COMMIT / BUILD_TIMESTAMP in place; returns the new pair."""
    commit = commit or current_commit()
    if not commit_is_reachable(commit):
        raise SystemExit("[ERROR] refusing to stamp an unreachable commit: %s" % commit)
    timestamp = timestamp or datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    src = io.open(STAMP_PATH, encoding="utf-8").read()
    updated, commit_hits = _COMMIT_RE.subn('BUILD_COMMIT = "%s"' % commit, src)
    updated, ts_hits = _TIMESTAMP_RE.subn('BUILD_TIMESTAMP = "%s"' % timestamp, updated)
    if commit_hits != 1 or ts_hits != 1:
        raise SystemExit(
            "[ERROR] expected exactly one BUILD_COMMIT / BUILD_TIMESTAMP line, "
            "found %d / %d -- refusing to guess" % (commit_hits, ts_hits))
    io.open(STAMP_PATH, "w", encoding="utf-8", newline="\n").write(updated)
    return commit, timestamp


def check():
    """Verify the stamped commit is still reachable. rc 0 = ok, 1 = dangling."""
    commit, timestamp = read_stamp()
    if commit is None or timestamp is None:
        print("[FAIL] shared/build_stamp.py has no BUILD_COMMIT / BUILD_TIMESTAMP line")
        return 1
    if not commit_is_reachable(commit):
        head = _git("rev-parse", "HEAD").stdout.strip()
        print("[FAIL] the stamped commit is no longer reachable: %s" % commit)
        print("       current HEAD: %s" % head)
        print("       `--version` on all four skill CLIs prints a hash that proves nothing.")
        print("       Fix: python scripts/stamp_build.py")
        return 1
    print("[PASS] build stamp is reachable: %s (%s)" % (commit[:12], timestamp))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="only verify the stamped commit is reachable (rc 1 if dangling)")
    parser.add_argument("--commit", default=None,
                        help="commit to stamp (default: current HEAD); must be reachable")
    parser.add_argument("--timestamp", default=None,
                        help="UTC ISO-8601 stamp, e.g. 2026-09-15T00:00:00Z")
    args = parser.parse_args(argv)

    if args.check:
        return check()

    old_commit, old_timestamp = read_stamp()
    commit, timestamp = restamp(args.commit, args.timestamp)
    print("build stamp updated")
    print("  commit    : %s -> %s" % (old_commit, commit))
    print("  timestamp : %s -> %s" % (old_timestamp, timestamp))
    print("  file      : %s" % STAMP_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
