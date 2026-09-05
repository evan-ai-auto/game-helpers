"""Compatibility entry point for surface transition sampling.

Keeps the historical module invocation working:

    python -m game_helpers.tasks.surface_transition_sampling_probe

The implementation now lives in ``surface_transition_sampling``.
"""
from __future__ import annotations

from .surface_transition_sampling import run_transition_sampling


def main() -> int:
    """Run the migrated transition sampling workflow."""
    return run_transition_sampling()


if __name__ == "__main__":
    raise SystemExit(main())
