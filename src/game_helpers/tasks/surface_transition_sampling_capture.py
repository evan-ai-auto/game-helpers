"""Capture-side transition helpers.

The original probe remains the compatibility entry point while logic moves here.
"""
from __future__ import annotations


def sample_transition(*args, **kwargs):
    raise NotImplementedError("transition sampler body will be migrated incrementally")
