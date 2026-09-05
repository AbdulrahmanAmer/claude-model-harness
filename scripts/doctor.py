#!/usr/bin/env python3
"""Repo-level shim: `scripts/doctor.py [--project P] [--profile X] [--json] [--apply] [--mode delete|move]`
Works outside Claude Code. See plugin/scripts/harness/doctor.py."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin", "scripts"))
from harness_cli import main  # noqa: E402
sys.exit(main(["doctor"] + sys.argv[1:]))
