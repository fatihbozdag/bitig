"""`bitig gui` — launch the native desktop GUI."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def gui_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the local NiceGUI server."),
    port: int = typer.Option(8080, "--port", "-p", help="Port for the local NiceGUI server."),
    no_native: bool = typer.Option(
        False,
        "--no-native",
        help="Open in the default browser instead of a native PyWebView window.",
    ),
    width: int = typer.Option(1200, "--width", help="Native window width in pixels."),
    height: int = typer.Option(800, "--height", help="Native window height in pixels."),
    dev: bool = typer.Option(False, "--dev", help="Enable hot reload (for GUI development)."),
) -> None:
    r"""Launch the bitig desktop GUI. Requires the `bitig\[gui]` extra."""
    try:
        from bitig.gui import launch
    except ImportError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    try:
        launch(
            host=host,
            port=port,
            native=not no_native,
            window_width=width,
            window_height=height,
            reload=dev,
        )
    except ImportError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
