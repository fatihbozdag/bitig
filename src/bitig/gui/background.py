"""Typed wrapper around NiceGUI's ``run.io_bound``.

NiceGUI 3 annotates ``run.io_bound`` as returning ``T | None``: it yields
``None`` instead of the callable's result when the app is shutting down and
the task is abandoned. Every bitig caller runs a function that returns a
value, so a ``None`` means "no result", never a legitimate return. This
wrapper turns it into an exception the callers' existing error handling
already reports, and gives mypy the non-optional type.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from nicegui import run

T = TypeVar("T")


class BackgroundTaskAbandonedError(RuntimeError):
    """The background task produced no result (the app is shutting down)."""


async def io_bound(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    result = await run.io_bound(func, *args, **kwargs)
    if result is None:
        raise BackgroundTaskAbandonedError(
            f"{getattr(func, '__name__', 'task')} returned no result (the app is shutting down)"
        )
    return result
