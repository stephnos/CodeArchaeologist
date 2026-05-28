from __future__ import annotations

import os
import sys


def launch_gui() -> None:
    """Open the UI. Uses a browser form (reliable on macOS); tk is optional fallback."""
    backend = os.environ.get("RETRO_GIT_GUI", "").lower()
    if backend == "tk":
        from retro_git.gui_tk import launch_tk_gui

        launch_tk_gui()
        return
    from retro_git.gui_web import launch_web_gui

    launch_web_gui()


if __name__ == "__main__":
    launch_gui()
