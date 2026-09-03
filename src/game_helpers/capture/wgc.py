"""Windows Graphics Capture backend using an explicit HWND target."""

from __future__ import annotations

import sys
import threading
import time

from .models import Frame


class WindowsGraphicsCapture:
    """Capture one HWND through the Windows Graphics Capture API."""

    backend_name = "windows-graphics-capture"

    def capture(
        self,
        window,
        *,
        timeout: float = 5.0,
        retries: int = 2,
        retry_delay: float = 0.15,
    ) -> Frame:
        """Return the first available BGRA frame for a WindowInfo-like object or HWND.

        WGC can occasionally close or fail to deliver the first frame while a
        hosted window is being rebound. Retry the complete capture session a
        small number of times; this does not change the target HWND or bring it
        to the foreground.
        """
        if sys.platform != "win32":
            raise RuntimeError("Windows Graphics Capture is only available on Windows")

        try:
            from windows_capture import WindowsCapture
        except ImportError as exc:
            raise RuntimeError(
                "Windows Graphics Capture requires the optional 'windows-capture' package; "
                "install the Windows extras with: pip install -e '.[windows]'"
            ) from exc

        # Keep the capture API tolerant of callers that naturally have an HWND.
        # Frame.window still needs a WindowInfo, so resolve an integer HWND first.
        if isinstance(window, int):
            from game_helpers.core.window import list_windows

            hwnd = int(window)
            resolved = next((item for item in list_windows() if item.hwnd == hwnd), None)
            if resolved is None:
                raise ValueError(f"could not resolve WindowInfo for hwnd={hwnd}")
            window = resolved
        hwnd = int(window.hwnd)

        if retries < 0:
            raise ValueError("retries must be non-negative")

        last_error: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                return self._capture_once(window, hwnd, WindowsCapture, timeout)
            except TimeoutError as exc:
                last_error = exc
                if attempt >= retries:
                    raise
                time.sleep(retry_delay)

        raise RuntimeError(f"Windows Graphics Capture failed for hwnd={hwnd}") from last_error

    def _capture_once(self, window, hwnd: int, windows_capture_type, timeout: float) -> Frame:
        result: dict[str, object] = {}
        ready = threading.Event()

        capture = windows_capture_type(
            cursor_capture=False,
            draw_border=False,
            monitor_index=None,
            window_hwnd=hwnd,
        )

        @capture.event
        def on_frame_arrived(native_frame, capture_control) -> None:
            try:
                buffer = native_frame.frame_buffer
                result["frame"] = Frame(
                    window=window,
                    width=int(native_frame.width),
                    height=int(native_frame.height),
                    data=buffer.tobytes(),
                    captured_at=time.time(),
                    backend=self.backend_name,
                )
            except BaseException as exc:
                result["error"] = exc
            finally:
                ready.set()
                capture_control.stop()

        @capture.event
        def on_closed() -> None:
            ready.set()

        control = capture.start_free_threaded()
        if not ready.wait(timeout):
            control.stop()
            control.wait()
            raise TimeoutError(
                f"timed out waiting for Windows Graphics Capture frame from hwnd={hwnd}"
            )

        control.wait()
        error = result.get("error")
        if error is not None:
            raise RuntimeError(f"Windows Graphics Capture callback failed: {error}") from error
        frame = result.get("frame")
        if frame is None:
            raise TimeoutError(
                f"Windows Graphics Capture closed before producing a frame for hwnd={hwnd}"
            )
        return frame  # type: ignore[return-value]
