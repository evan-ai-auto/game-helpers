"""Surface transition sampling orchestration.

The public probe entry remains compatible while transition workflow is moved
into this module.
"""
from __future__ import annotations

from pathlib import Path

from .surface_transition_sampling_capture import sample_transition


__all__ = ["sample_transition"]


def run_transition_sampling(*args, **kwargs):
    """Compatibility orchestration wrapper for transition sampling."""
    return sample_transition(*args, **kwargs)
