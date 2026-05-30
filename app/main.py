"""Application entry point for HandBrakePlus."""

from __future__ import annotations

import ctypes

from .ui import HandBrakePlusApp


def main() -> None:
    _enable_high_dpi_mode()
    app = HandBrakePlusApp()
    app.protocol("WM_DELETE_WINDOW", lambda: _close_app(app))
    app.mainloop()


def _close_app(app: HandBrakePlusApp) -> None:
    app.save_state()
    app.destroy()


def _enable_high_dpi_mode() -> None:
    try:
        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore
    except AttributeError:
        return

    try:
        # PER_MONITOR_AWARE_V2 keeps Tk from being bitmap-scaled by Windows.
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass

    try:
        shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        return


if __name__ == "__main__":
    main()
