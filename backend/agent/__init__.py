"""Compatibility package for agent APIs (singular) re-exporting
and providing minimal platform tooling used by tests.
"""

from . import tools  # expose tools subpackage

__all__ = ["tools"]
