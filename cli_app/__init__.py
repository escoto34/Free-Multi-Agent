"""Interactive Free-Multi-Agent CLI (slash commands + session context)."""

__all__ = ["run_tui"]


def run_tui() -> None:
    from cli_app.tui import run_app

    run_app()
