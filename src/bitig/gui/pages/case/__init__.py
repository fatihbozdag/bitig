"""Forensic Lab Case pages (spec §5).

Importing this package registers every ``@ui.page`` route as a side effect.
``bitig.gui.app`` imports it just before ``ui.run()``.
"""

from __future__ import annotations

from bitig.gui.pages.case import (  # noqa: F401
    evidence,
    findings,
    landing,
    method,
    report,
    run,
)
