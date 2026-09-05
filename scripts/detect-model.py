#!/usr/bin/env python3
"""Repo-level shim: `scripts/detect-model.py [--json] < hook.json` -> plugin/scripts/harness_cli.py detect"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "plugin", "scripts"))
from harness_cli import main  # noqa: E402
sys.exit(main(["detect"] + sys.argv[1:]))
