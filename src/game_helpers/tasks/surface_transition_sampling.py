"""Surface transition sampling orchestration.

The public probe entry remains compatible while transition workflow is moved
into this module.
"""
from __future__ import annotations

from .surface_transition_sampling_capture import sample_transition


__all__ = ["sample_transition", "run_transition_sampling"]


def run_transition_sampling(*args, **kwargs):
    """Run transition sampling with explicit runtime dependencies.

    The old probe entrypoint historically received capture/manager/window
    context from its CLI workflow. Do not invoke the low-level sampler without
    those dependencies.
    """
    if not args and not kwargs:
        raise RuntimeError(
            "surface transition sampling requires runtime context; "
            "use the original probe CLI arguments or call sample_transition "
            "with cap, manager, parent_hwnd, target_index and output_dir."
        )
    return sample_transition(*args, **kwargs)
