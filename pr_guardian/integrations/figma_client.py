"""
Client Figma — PR-Guardian Orchestrator.

Fournit l'accès à l'API Figma pour :
- Récupérer les métadonnées d'un fichier Figma (pages, frames)
- Extraire les composants, textes, annotations, descriptions
- Identifier les écrans / variantes / states pour vérification UI
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import requests

from pr_guardian.config import get_settings
from pr_guardian.models import FigmaRequirement

logger = logging.getLogger("pr_guardian.figma")


class FigmaClient:
    """Client REST API Figma."""

    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, token: str | None = None):
        settings = get_settings()
        self._token = token or settings.figma_access_token
        if not self._token:
            raise ValueError("FIGMA_ACCESS_TOKEN non configuré.")
        self._headers = {"X-Figma-Token": self._token}

    # ── Helpers ─────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE_URL}/{path}"
        resp = requests.get(url, headers=self._headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Parse Figma URL ─────────────────────

    @staticmethod
    def parse_figma_url(url: str) -> dict[str, str]:
        """
        Extrait le file_key (et optionnellement le node_id) d'une URL Figma.
        Formats supportés :
          https://www.figma.com/file/XXXXX/Nom?node-id=0-1
          https://www.figma.com/design/XXXXX/Nom?node-id=0-1
        """
        pattern = r"figma\.com/(?:file|design)/([A-Za-z0-9]+)"
        match = re.search(pattern, url)
        if not match:
            raise ValueError(f"URL Figma invalide : {url}")
        file_key = match.group(1)

        node_id = None
        node_match = re.search(r"node-id=([^&]+)", url)
        if node_match:
            node_id = node_match.group(1).replace("%3A", ":")

        return {"file_key": file_key, "node_id": node_id}

    # ── Fichier Figma ───────────────────────

    def get_file(self, file_key: str) -> dict:
        """Récupère le fichier Figma complet (arbre de nœuds)."""
        return self._get(f"files/{file_key}")

    def get_file_metadata(self, file_key: str) -> dict:
        """Récupère uniquement les métadonnées (nom, pages…)."""
        data = self.get_file(file_key)
        document = data.get("document", {})
        pages: list[dict] = []
        for child in document.get("children", []):
            if child.get("type") == "CANVAS":
                pages.append({
                    "id": child.get("id"),
                    "name": child.get("name"),
                    "frame_count": len(child.get("children", [])),
                })
        return {
            "name": data.get("name", ""),
            "last_modified": data.get("lastModified", ""),
            "version": data.get("version", ""),
            "pages": pages,
        }

    # ── Nœuds spécifiques ──────────────────

    def get_nodes(self, file_key: str, node_ids: list[str]) -> dict:
        """Récupère des nœuds spécifiques par ID."""
        ids_str = ",".join(node_ids)
        return self._get(f"files/{file_key}/nodes", params={"ids": ids_str})

    # ── Extraction des exigences UI ─────────

    def extract_requirements(
        self, file_key: str, node_id: str | None = None
    ) -> list[FigmaRequirement]:
        """
        Parcourt l'arbre Figma et extrait les frames/composants comme exigences UI.
        Si node_id est fourni, se concentre sur ce sous-arbre.
        """
        if node_id:
            data = self.get_nodes(file_key, [node_id])
            nodes = data.get("nodes", {})
            root = list(nodes.values())[0].get("document", {}) if nodes else {}
            return self._walk_node(root, page_name="(node)")
        else:
            file_data = self.get_file(file_key)
            document = file_data.get("document", {})
            requirements: list[FigmaRequirement] = []
            for page in document.get("children", []):
                if page.get("type") == "CANVAS":
                    requirements.extend(
                        self._walk_node(page, page_name=page.get("name", ""))
                    )
            return requirements

    def _walk_node(
        self, node: dict, page_name: str = "", depth: int = 0
    ) -> list[FigmaRequirement]:
        """Parcourt récursivement l'arbre de nœuds Figma."""
        results: list[FigmaRequirement] = []
        node_type = node.get("type", "")

        # On s'intéresse aux FRAME, COMPONENT, COMPONENT_SET (= variantes)
        if node_type in ("FRAME", "COMPONENT", "COMPONENT_SET") and depth > 0:
            texts = self._collect_texts(node)
            components = self._collect_component_names(node)
            states = self._detect_states(node)

            req = FigmaRequirement(
                frame_id=node.get("id", ""),
                frame_name=node.get("name", ""),
                page_name=page_name,
                description=node.get("description", "") or "",
                components=components,
                texts=texts,
                states=states,
            )
            results.append(req)

        # Récursion sur les enfants (max depth 5 pour perf)
        if depth < 5:
            for child in node.get("children", []):
                results.extend(self._walk_node(child, page_name, depth + 1))

        return results

    @staticmethod
    def _collect_texts(node: dict) -> list[str]:
        """Collecte tous les textes dans un sous-arbre."""
        texts: list[str] = []

        def walk(n: dict) -> None:
            if n.get("type") == "TEXT":
                chars = n.get("characters", "")
                if chars.strip():
                    texts.append(chars.strip())
            for child in n.get("children", []):
                walk(child)

        walk(node)
        return texts

    @staticmethod
    def _collect_component_names(node: dict) -> list[str]:
        """Collecte les noms de composants utilisés."""
        names: list[str] = []

        def walk(n: dict) -> None:
            if n.get("type") in ("INSTANCE", "COMPONENT"):
                name = n.get("name", "")
                if name:
                    names.append(name)
            for child in n.get("children", []):
                walk(child)

        walk(node)
        return list(set(names))

    @staticmethod
    def _detect_states(node: dict) -> list[str]:
        """Détecte les states/variantes dans le nom ou les enfants."""
        state_keywords = [
            "hover", "active", "disabled", "error", "success",
            "loading", "empty", "default", "focused", "selected",
        ]
        states: list[str] = []

        def walk(n: dict) -> None:
            name_lower = n.get("name", "").lower()
            for kw in state_keywords:
                if kw in name_lower and kw not in states:
                    states.append(kw)
            for child in n.get("children", []):
                walk(child)

        walk(node)
        return states
