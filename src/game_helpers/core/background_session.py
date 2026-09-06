"""Compatibility export for the runtime session.

Background session orchestration no longer belongs to Core.
"""

from ..runtime.session import BackgroundGameSession

__all__ = ["BackgroundGameSession"]
