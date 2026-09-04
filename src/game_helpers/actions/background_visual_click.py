"""Background click followed by reusable visual-state verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .background_input import BackgroundClickVerification, BackgroundInput
from ..capture.models import Frame
from ..tasks.visual_state import VisualStateObservation, VisualStateProfile, make_visual_state_verifier


@dataclass(frozen=True)
class BackgroundVisualClickResult:
    click: BackgroundClickVerification[VisualStateObservation]

    @property
    def success(self) -> bool:
        return self.click.verified

    @property
    def timed_out(self) -> bool:
        return self.click.timed_out


def click_and_verify_visual_state(
    hwnd: int,
    x: int,
    y: int,
    capture: Callable[[], Frame],
    profile: VisualStateProfile,
    *,
    timeout: float = 5.0,
    poll_interval: float = 0.10,
) -> BackgroundVisualClickResult:
    """Click a background window and wait for a declared visual state.

    The click uses the existing ordinary Win32 PostMessage path. The verifier
    repeatedly captures the complete target frame and searches for the visual
    state profile's required anchors. The target state therefore need not stay
    at a fixed screen/client coordinate.
    """
    verifier = make_visual_state_verifier(capture, profile)
    result = BackgroundInput(hwnd).click_and_verify(
        x,
        y,
        verifier,
        timeout=timeout,
        poll_interval=poll_interval,
    )
    return BackgroundVisualClickResult(result)
