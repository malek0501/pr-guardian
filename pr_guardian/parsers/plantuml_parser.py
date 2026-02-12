"""
Parseur PlantUML — PR-Guardian Orchestrator.

Parse les fichiers .puml/.plantuml pour en extraire :
- Type de diagramme (class, sequence, activity, usecase…)
- Entités (classes, interfaces, acteurs…)
- Relations (héritage, composition, association…)
- Méthodes et attributs (diagrammes de classes)
"""

from __future__ import annotations

import re
from typing import Any

from pr_guardian.models import UMLDiagram, UMLEntity, UMLRelation


class PlantUMLParser:
    """Parseur statique de fichiers PlantUML."""

    # ── Patterns ────────────────────────────

    # Détection du type de diagramme
    _DIAGRAM_TYPE_PATTERNS = {
        "sequence": re.compile(r"->|-->|<-|<--|participant\s", re.IGNORECASE),
        "class": re.compile(r"\bclass\s+\w+|interface\s+\w+|abstract\s+class", re.IGNORECASE),
        "activity": re.compile(r":[\w\s]+;|start\b|stop\b|fork\b", re.IGNORECASE),
        "usecase": re.compile(r"\busecase\s|actor\s|\([\w\s]+\)", re.IGNORECASE),
        "component": re.compile(r"\bcomponent\s|\bpackage\s", re.IGNORECASE),
        "state": re.compile(r"\bstate\s+\w+|\[\*\]\s*-->", re.IGNORECASE),
    }

    # Entités — classes / interfaces
    _CLASS_RE = re.compile(
        r"(?:abstract\s+)?(?:class|interface|enum)\s+"
        r"(?:\"([^\"]+)\"|(\w+))"
        r"(?:\s*(?:<<\w+>>))?"
        r"(?:\s*\{([^}]*)\})?",
        re.IGNORECASE | re.DOTALL,
    )

    # Acteurs (usecase)
    _ACTOR_RE = re.compile(
        r"actor\s+(?:\"([^\"]+)\"|(\w+))", re.IGNORECASE
    )

    # Participants (séquence)
    _PARTICIPANT_RE = re.compile(
        r"participant\s+(?:\"([^\"]+)\"|(\w+))", re.IGNORECASE
    )

    # Relations
    _RELATION_RE = re.compile(
        r"(?:\"?(\w[\w\s]*)\"?)\s*"
        r"([<>|.*o#x}{+\-]+)"
        r"\s*(?:\"?(\w[\w\s]*)\"?)"
        r"(?:\s*:\s*(.+))?",
    )

    # ── API publique ────────────────────────

    @classmethod
    def parse(cls, content: str, filepath: str = "") -> UMLDiagram:
        """Parse du contenu PlantUML et retourne un UMLDiagram."""
        diagram_type = cls._detect_type(content)
        entities = cls._extract_entities(content, diagram_type)
        relations = cls._extract_relations(content)

        return UMLDiagram(
            filepath=filepath,
            diagram_type=diagram_type,
            entities=entities,
            relations=relations,
            raw_content=content,
        )

    @classmethod
    def parse_file(cls, filepath: str) -> UMLDiagram:
        """Lit et parse un fichier PlantUML."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return cls.parse(content, filepath)

    # ── Détection type ──────────────────────

    @classmethod
    def _detect_type(cls, content: str) -> str:
        scores: dict[str, int] = {}
        for dtype, pattern in cls._DIAGRAM_TYPE_PATTERNS.items():
            matches = pattern.findall(content)
            scores[dtype] = len(matches)
        if not scores or max(scores.values()) == 0:
            return "unknown"
        return max(scores, key=scores.get)  # type: ignore

    # ── Extraction entités ──────────────────

    @classmethod
    def _extract_entities(cls, content: str, dtype: str) -> list[UMLEntity]:
        entities: list[UMLEntity] = []

        # Classes / Interfaces / Enums
        for match in cls._CLASS_RE.finditer(content):
            name = match.group(1) or match.group(2)
            body = match.group(3) or ""
            attrs, methods = cls._parse_class_body(body)
            entity_type = "class"
            line = match.group(0).lower()
            if "interface" in line:
                entity_type = "interface"
            elif "enum" in line:
                entity_type = "enum"
            elif "abstract" in line:
                entity_type = "abstract class"
            entities.append(UMLEntity(
                name=name.strip(),
                entity_type=entity_type,
                attributes=attrs,
                methods=methods,
            ))

        # Acteurs
        for match in cls._ACTOR_RE.finditer(content):
            name = match.group(1) or match.group(2)
            entities.append(UMLEntity(name=name.strip(), entity_type="actor"))

        # Participants
        for match in cls._PARTICIPANT_RE.finditer(content):
            name = match.group(1) or match.group(2)
            entities.append(UMLEntity(name=name.strip(), entity_type="participant"))

        return entities

    @staticmethod
    def _parse_class_body(body: str) -> tuple[list[str], list[str]]:
        """Sépare les attributs et méthodes d'un corps de classe."""
        attrs: list[str] = []
        methods: list[str] = []
        for line in body.strip().splitlines():
            line = line.strip()
            if not line or line == "--" or line == "..":
                continue
            if "(" in line:
                methods.append(line)
            else:
                attrs.append(line)
        return attrs, methods

    # ── Extraction relations ────────────────

    @classmethod
    def _extract_relations(cls, content: str) -> list[UMLRelation]:
        relations: list[UMLRelation] = []
        # Patterns de relation simples
        rel_patterns = [
            # A --|> B, A ..> B, A --> B, etc.
            re.compile(
                r"(\w+)\s+([-.<>|*o#}{:]+)\s+(\w+)\s*(?::\s*(.+))?"
            ),
        ]
        for pattern in rel_patterns:
            for match in pattern.finditer(content):
                source = match.group(1).strip()
                arrow = match.group(2).strip()
                target = match.group(3).strip()
                label = (match.group(4) or "").strip()

                # Ignorer les mots-clés PlantUML
                if source.lower() in ("class", "interface", "enum", "abstract", "actor",
                                       "participant", "package", "start", "stop", "end"):
                    continue

                rel_type = cls._classify_relation(arrow)
                relations.append(UMLRelation(
                    source=source,
                    target=target,
                    relation_type=rel_type,
                    label=label,
                ))
        return relations

    @staticmethod
    def _classify_relation(arrow: str) -> str:
        """Classifie le type de relation à partir de la flèche."""
        if "--|>" in arrow or "<|--" in arrow:
            return "inheritance"
        if "..|>" in arrow or "<|.." in arrow:
            return "implementation"
        if "--*" in arrow or "*--" in arrow:
            return "composition"
        if "--o" in arrow or "o--" in arrow:
            return "aggregation"
        if "-->" in arrow or "<--" in arrow:
            return "association"
        if "..>" in arrow or "<.." in arrow:
            return "dependency"
        if "->" in arrow or "<-" in arrow:
            return "message"
        return "unknown"
