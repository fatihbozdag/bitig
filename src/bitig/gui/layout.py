"""Shared header + left-drawer navigation shell for all GUI pages."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from nicegui import ui

from bitig._version import __version__

BRAND_NAVY = "#0F1A2B"
BRAND_BRASS = "#C9A34A"

NAV = [
    ("Ingest", "/ingest", "folder_open"),
    ("Study", "/study", "tune"),
    ("Run", "/run", "play_arrow"),
    ("Results", "/results", "insights"),
    ("Forensic", "/forensic", "gavel"),
    # New Forensic Lab Case workflow (spec §5). The legacy pages above
    # remain reachable; the new flow lives under /case.
    ("Forensic Lab →", "/case", "biotech"),
]


@contextmanager
def page_shell(title: str) -> Iterator[None]:
    """Render the bitig top bar + left drawer, then yield to the page body.

    Each ``@ui.page`` function calls ``with page_shell("Page Title"): ...``
    and fills the main column from inside the block.
    """
    ui.colors(primary=BRAND_NAVY, secondary=BRAND_BRASS)
    with ui.header().style(f"background-color: {BRAND_NAVY}; color: white;"):
        ui.label("bitig").classes("text-2xl font-bold").style(f"color: {BRAND_BRASS}")
        ui.label(title).classes("text-lg ml-4 opacity-90")
        ui.space()
        ui.label(f"v{__version__}").classes("text-xs opacity-60")
    with ui.left_drawer(value=True, fixed=False).classes("bg-slate-100"):
        for label, route, icon in NAV:
            with (
                ui.row()
                .classes("items-center gap-2 p-3 hover:bg-slate-200 cursor-pointer")
                .on("click", lambda r=route: ui.navigate.to(r))
            ):
                ui.icon(icon).classes("text-lg").style(f"color: {BRAND_NAVY}")
                ui.label(label).classes("text-base")
    with ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-4"):
        yield
