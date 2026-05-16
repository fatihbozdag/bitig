"""Smoke test: importing the Case page package registers every route.

This exercises the page-decorator side effects (each ``@ui.page`` call) so
import-time bugs in the new layout / pages get caught even though the
visual rendering itself isn't unit-tested.
"""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")


def test_case_pages_package_imports() -> None:
    from bitig.gui.pages import case  # noqa: F401


def test_case_layout_imports() -> None:
    from bitig.gui.case_layout import STEPS, TOKENS, case_shell  # noqa: F401

    # Sanity: spec §5 locks exactly five steps in this order.
    assert [k for k, _ in STEPS] == ["evidence", "method", "run", "findings", "report"]


def test_legacy_layout_includes_forensic_lab_link() -> None:
    from bitig.gui.layout import NAV

    labels = [label for label, _route, _icon in NAV]
    assert "Forensic Lab →" in labels
    forensic_lab = next(item for item in NAV if item[0] == "Forensic Lab →")
    assert forensic_lab[1] == "/case"
