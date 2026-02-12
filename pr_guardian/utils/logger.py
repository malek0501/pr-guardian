"""
Logger structuré — PR-Guardian Orchestrator.

Configure un logging coloré (via Rich) avec niveaux par module.
"""

from __future__ import annotations

import logging
import sys

from rich.console import Console
from rich.logging import RichHandler

from pr_guardian.config import get_settings


_configured = False


def setup_logging() -> None:
    """Configure le logging global une seule fois."""
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    console = Console(stderr=True)
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        markup=True,
        rich_tracebacks=True,
    )
    handler.setLevel(level)

    fmt = logging.Formatter("%(name)s — %(message)s")
    handler.setFormatter(fmt)

    root = logging.getLogger("pr_guardian")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Réduire le bruit des libs
    for lib in ("urllib3", "httpx", "httpcore", "github", "google"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger enfant de pr_guardian."""
    setup_logging()
    return logging.getLogger(f"pr_guardian.{name}")
