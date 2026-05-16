"""Shared GUI widgets — reusable across Case step pages.

Currently:
* :mod:`bitig.gui.widgets.recipe_drawer` — side drawer that surfaces a
  recipe's ParamField schema for editing (spec §5.2).
"""

from __future__ import annotations

from bitig.gui.widgets.recipe_drawer import open_recipe_drawer

__all__ = ["open_recipe_drawer"]
