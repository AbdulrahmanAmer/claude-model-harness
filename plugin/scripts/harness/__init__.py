"""claude-model-harness — shared library used by the plugin hooks and the CLI scripts.

Design rules (see README):
  * Every function that a hook calls must never raise to the caller: hooks fail open.
  * No third-party dependencies. Python 3.10+.
  * Anything not backed by an official doc is marked UNVERIFIED in comments.
"""

__version__ = "0.2.0"
