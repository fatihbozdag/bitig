"""Native OS file / folder pickers via PyWebView, with browser-mode fallback.

When ``bitig gui`` runs with ``--native`` (the default), NiceGUI makes the
PyWebView window available as ``app.native.main_window``, which exposes
``create_file_dialog(...)`` — the OS's standard Open / Save dialog. In
browser mode (``--no-native``) no native window exists and these helpers
return ``None``; callers should keep the plain path text input visible in
that case so users can still type a path.
"""

from __future__ import annotations

from collections.abc import Sequence

import webview
from nicegui import app
from webview import FileDialog


def _main_window() -> webview.Window | None:
    native = getattr(app, "native", None)
    return getattr(native, "main_window", None) if native is not None else None


def is_native_available() -> bool:
    return _main_window() is not None


async def pick_folder(title: str = "Select folder") -> str | None:
    window = _main_window()
    if window is None:
        return None
    result = await window.create_file_dialog(  # type: ignore[misc]  # nicegui stub mistypes this async pywebview API (awaitable at runtime)
        FileDialog.FOLDER,
        directory="",
        allow_multiple=False,
    )
    if not result:
        return None
    return str(result[0])


async def pick_file(
    title: str = "Select file",
    file_types: Sequence[str] = ("All files (*.*)",),
) -> str | None:
    window = _main_window()
    if window is None:
        return None
    result = await window.create_file_dialog(  # type: ignore[misc]  # nicegui stub mistypes this async pywebview API (awaitable at runtime)
        FileDialog.OPEN,
        allow_multiple=False,
        file_types=tuple(file_types),
    )
    if not result:
        return None
    return str(result[0])


async def pick_save_path(
    title: str = "Save as",
    default_filename: str = "",
    file_types: Sequence[str] = ("All files (*.*)",),
) -> str | None:
    window = _main_window()
    if window is None:
        return None
    result = await window.create_file_dialog(  # type: ignore[misc]  # nicegui stub mistypes this async pywebview API (awaitable at runtime)
        FileDialog.SAVE,
        save_filename=default_filename,
        file_types=tuple(file_types),
    )
    if not result:
        return None
    # SAVE_DIALOG returns a single string on most platforms, list on some.
    if isinstance(result, (list, tuple)):
        return str(result[0])
    return str(result)
