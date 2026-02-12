"""
Parseur de diff Git — PR-Guardian Orchestrator.

Analyse les patches/diffs pour en extraire des informations structurées :
- Lignes ajoutées / supprimées
- Fonctions / classes modifiées
- Endpoints détectés
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DiffHunk:
    """Un bloc de diff (hunk)."""
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    header: str = ""
    lines_added: list[str] = field(default_factory=list)
    lines_removed: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    """Diff d'un fichier."""
    filename: str = ""
    hunks: list[DiffHunk] = field(default_factory=list)
    functions_modified: list[str] = field(default_factory=list)
    classes_modified: list[str] = field(default_factory=list)
    endpoints_detected: list[str] = field(default_factory=list)


class DiffParser:
    """Parse un patch/diff Git et extrait les informations utiles."""

    # Hunk header: @@ -old_start,old_count +new_start,new_count @@ context
    _HUNK_RE = re.compile(
        r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\s*(.*)"
    )

    # Détection de fonctions / méthodes (multi-langage)
    _FUNC_PATTERNS = [
        re.compile(r"(?:def|function|func|fn)\s+(\w+)"),                 # Python, JS, Go, Rust
        re.compile(r"(?:public|private|protected)\s+\w+\s+(\w+)\s*\("),  # Java, C#
        re.compile(r"(?:async\s+)?(\w+)\s*\(.*\)\s*[:{]"),              # Generic
    ]

    # Détection de classes
    _CLASS_RE = re.compile(r"class\s+(\w+)")

    # Détection d'endpoints REST
    _ENDPOINT_PATTERNS = [
        re.compile(r"@(?:Get|Post|Put|Delete|Patch)Mapping\s*\(\s*[\"']([^\"']+)", re.IGNORECASE),
        re.compile(r"@(?:RequestMapping|api_view)\s*\(\s*[\"']([^\"']+)", re.IGNORECASE),
        re.compile(r"router\.\s*(?:get|post|put|delete|patch)\s*\(\s*[\"']([^\"']+)"),
        re.compile(r"app\.\s*(?:get|post|put|delete|patch|route)\s*\(\s*[\"']([^\"']+)"),
        re.compile(r"path\(\s*[\"']([^\"']+)"),  # Django urls
    ]

    @classmethod
    def parse_patch(cls, patch: str, filename: str = "") -> FileDiff:
        """Parse un patch unique (contenu du champ `patch` GitHub)."""
        diff = FileDiff(filename=filename)
        current_hunk: DiffHunk | None = None

        for line in patch.splitlines():
            hunk_match = cls._HUNK_RE.match(line)
            if hunk_match:
                current_hunk = DiffHunk(
                    old_start=int(hunk_match.group(1)),
                    old_count=int(hunk_match.group(2) or 1),
                    new_start=int(hunk_match.group(3)),
                    new_count=int(hunk_match.group(4) or 1),
                    header=hunk_match.group(5),
                )
                diff.hunks.append(current_hunk)
                continue

            if current_hunk is None:
                continue

            if line.startswith("+") and not line.startswith("+++"):
                added = line[1:]
                current_hunk.lines_added.append(added)
                cls._detect_symbols(added, diff)
            elif line.startswith("-") and not line.startswith("---"):
                current_hunk.lines_removed.append(line[1:])

        return diff

    @classmethod
    def _detect_symbols(cls, line: str, diff: FileDiff) -> None:
        """Détecte les symboles (fonctions, classes, endpoints) dans une ligne ajoutée."""
        for pattern in cls._FUNC_PATTERNS:
            match = pattern.search(line)
            if match and match.group(1) not in diff.functions_modified:
                diff.functions_modified.append(match.group(1))

        class_match = cls._CLASS_RE.search(line)
        if class_match and class_match.group(1) not in diff.classes_modified:
            diff.classes_modified.append(class_match.group(1))

        for pattern in cls._ENDPOINT_PATTERNS:
            match = pattern.search(line)
            if match and match.group(1) not in diff.endpoints_detected:
                diff.endpoints_detected.append(match.group(1))
