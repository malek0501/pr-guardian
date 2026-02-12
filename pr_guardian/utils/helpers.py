"""
Utilitaires divers — PR-Guardian Orchestrator.
"""

from __future__ import annotations

import re
from typing import Any


def truncate(text: str, max_len: int = 500) -> str:
    """Tronque un texte en gardant le début et la fin."""
    if len(text) <= max_len:
        return text
    half = max_len // 2
    return text[:half] + "\n…[tronqué]…\n" + text[-half:]


def sanitize_for_markdown(text: str) -> str:
    """Échappe les caractères spéciaux Markdown."""
    for char in ("*", "_", "`", "[", "]", "(", ")", "#", ">"):
        text = text.replace(char, f"\\{char}")
    return text


def extract_language(filename: str) -> str:
    """Détermine le langage à partir de l'extension."""
    ext_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "tsx": "typescript", "jsx": "javascript", "java": "java",
        "kt": "kotlin", "swift": "swift", "go": "go", "rs": "rust",
        "rb": "ruby", "php": "php", "cs": "csharp", "cpp": "cpp",
        "c": "c", "html": "html", "css": "css", "scss": "scss",
        "sql": "sql", "yaml": "yaml", "yml": "yaml", "json": "json",
        "xml": "xml", "md": "markdown", "puml": "plantuml",
        "plantuml": "plantuml",
    }
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext_map.get(ext, ext)


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Aplatit un dict imbriqué."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def percentage(part: int, total: int) -> str:
    """Calcule un pourcentage formaté."""
    if total == 0:
        return "N/A"
    return f"{(part / total) * 100:.0f}%"
