"""NiceGUI page definitions for the bitig desktop app.

Importing this module registers every ``@ui.page`` route as a side effect;
the launcher imports it just before calling ``ui.run()``. No UI calls happen
at module scope — NiceGUI forbids that when using ``@ui.page``.
"""

from __future__ import annotations

from bitig.gui.pages import case, forensic, ingest, results, run, study  # noqa: F401
