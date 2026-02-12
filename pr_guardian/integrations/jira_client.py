"""
Client Jira — PR-Guardian Orchestrator.

Fournit l'accès à l'API Jira pour :
- Récupérer une issue (description, acceptance criteria, definition of done)
- Extraire les liens Figma depuis les champs custom
- Transitionner une issue (Done, Needs Fix…)
- Ajouter un commentaire
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

import requests

from pr_guardian.config import get_settings

logger = logging.getLogger("pr_guardian.jira")


class JiraClient:
    """Client REST Jira Cloud (Atlassian)."""

    def __init__(self):
        settings = get_settings()
        if not settings.jira_configured:
            raise ValueError("Jira non configuré (JIRA_BASE_URL / JIRA_API_TOKEN manquant).")
        self._base_url = settings.jira_base_url.rstrip("/")
        self._auth = (settings.jira_user_email, settings.jira_api_token)
        self._headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # ── Helpers HTTP ────────────────────────

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base_url}/rest/api/3/{path}"
        resp = requests.get(url, auth=self._auth, headers=self._headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_data: dict) -> dict:
        url = f"{self._base_url}/rest/api/3/{path}"
        resp = requests.post(
            url, auth=self._auth, headers=self._headers, json=json_data, timeout=30
        )
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    # ── Issue ───────────────────────────────

    def get_issue(self, issue_key: str) -> dict:
        """Récupère les détails complets d'une issue Jira."""
        return self._get(f"issue/{issue_key}")

    def get_issue_fields(self, issue_key: str) -> dict[str, Any]:
        """Extrait les champs utiles d'une issue."""
        data = self.get_issue(issue_key)
        fields = data.get("fields", {})
        return {
            "key": issue_key,
            "summary": fields.get("summary", ""),
            "description": self._extract_text(fields.get("description")),
            "status": fields.get("status", {}).get("name", ""),
            "acceptance_criteria": self._extract_acceptance_criteria(fields),
            "definition_of_done": self._extract_definition_of_done(fields),
            "labels": fields.get("labels", []),
            "components": [c.get("name", "") for c in fields.get("components", [])],
            "figma_links": self._extract_figma_links(fields),
        }

    # ── Extraction texte Jira (ADF → plain text) ──

    @staticmethod
    def _extract_text(adf: Any) -> str:
        """Convertit un document ADF (Atlassian Document Format) en texte brut."""
        if adf is None:
            return ""
        if isinstance(adf, str):
            return adf
        lines: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text":
                    lines.append(node.get("text", ""))
                for child in node.get("content", []):
                    walk(child)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(adf)
        return "\n".join(lines)

    # ── Extraction Acceptance Criteria ──────

    def _extract_acceptance_criteria(self, fields: dict) -> list[str]:
        """Tente d'extraire les acceptance criteria depuis la description ou un champ custom."""
        # Chercher dans les champs custom contenant "acceptance"
        for key, value in fields.items():
            if "acceptance" in key.lower() or "critère" in str(value).lower():
                text = self._extract_text(value)
                if text:
                    return self._split_criteria(text)

        # Fallback : section dans la description
        desc = self._extract_text(fields.get("description"))
        return self._parse_section(desc, ["acceptance criteria", "critères d'acceptation", "ac:"])

    def _extract_definition_of_done(self, fields: dict) -> list[str]:
        """Tente d'extraire la Definition of Done."""
        for key, value in fields.items():
            if "definition" in key.lower() and "done" in key.lower():
                text = self._extract_text(value)
                if text:
                    return self._split_criteria(text)
        desc = self._extract_text(fields.get("description"))
        return self._parse_section(desc, ["definition of done", "dod:", "done quand"])

    @staticmethod
    def _parse_section(text: str, headers: list[str]) -> list[str]:
        """Parse une section commençant par un header donné."""
        lower = text.lower()
        for header in headers:
            idx = lower.find(header)
            if idx >= 0:
                after = text[idx + len(header):]
                # Prendre jusqu'à la prochaine section ou fin
                end_idx = len(after)
                for marker in ["\n#", "\n---", "\n==", "\n**"]:
                    pos = after.find(marker)
                    if pos > 0:
                        end_idx = min(end_idx, pos)
                section = after[:end_idx]
                return JiraClient._split_criteria(section)
        return []

    @staticmethod
    def _split_criteria(text: str) -> list[str]:
        """Découpe du texte en liste de critères."""
        lines = re.split(r"\n[-*•]\s*|\n\d+[.)]\s*", text)
        return [line.strip() for line in lines if line.strip()]

    # ── Extraction Figma links ──────────────

    def _extract_figma_links(self, fields: dict) -> list[str]:
        """Cherche des liens Figma dans tous les champs texte de l'issue."""
        figma_re = re.compile(r"https?://(?:www\.)?figma\.com/(?:file|design)/[^\s\)\"'>]+")
        links: list[str] = []
        for _key, value in fields.items():
            text = self._extract_text(value) if not isinstance(value, str) else value
            links.extend(figma_re.findall(str(text)))
        return list(set(links))

    # ── Transitions ─────────────────────────

    def transition_issue(self, issue_key: str, transition_id: str, comment: str = "") -> None:
        """Transitionne une issue Jira (ex: vers Done ou Needs Fix)."""
        payload: dict[str, Any] = {"transition": {"id": transition_id}}
        if comment:
            payload["update"] = {
                "comment": [
                    {
                        "add": {
                            "body": {
                                "version": 1,
                                "type": "doc",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": comment}],
                                    }
                                ],
                            }
                        }
                    }
                ]
            }
        url = f"{self._base_url}/rest/api/3/issue/{issue_key}/transitions"
        resp = requests.post(
            url, auth=self._auth, headers=self._headers, json=payload, timeout=30
        )
        resp.raise_for_status()
        logger.info(f"Issue {issue_key} transitionnée (id={transition_id})")

    # ── Commentaire ─────────────────────────

    def add_comment(self, issue_key: str, text: str) -> None:
        """Ajoute un commentaire ADF sur une issue Jira."""
        payload = {
            "body": {
                "version": 1,
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        }
        self._post(f"issue/{issue_key}/comment", payload)
        logger.info(f"Commentaire ajouté sur {issue_key}")
