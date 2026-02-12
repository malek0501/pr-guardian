"""
Configuration centralisée — PR-Guardian Orchestrator.

Charge les variables d'environnement depuis .env et expose
un objet Settings validé via Pydantic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

# ── Racine du projet ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Charger .env ────────────────────────────
_env_path = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Paramètres globaux chargés depuis les variables d'environnement."""

    # GitHub
    github_token: str = Field(default="", description="GitHub personal access token")
    github_api_url: str = Field(default="https://api.github.com")

    # Jira
    jira_base_url: str = Field(default="")
    jira_user_email: str = Field(default="")
    jira_api_token: str = Field(default="")
    jira_done_transition_id: str = Field(default="31")
    jira_needs_fix_transition_id: str = Field(default="21")

    # Figma
    figma_access_token: str = Field(default="")

    # LLM / Cohere
    cohere_api_key: str = Field(default="")
    cohere_model: str = Field(default="command-a-03-2025")
    cohere_max_tokens: int = Field(default=4096)

    # Email
    email_provider: Literal["smtp", "sendgrid"] = Field(default="smtp")
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    email_from: str = Field(default="PR-Guardian <bot@example.com>")
    sendgrid_api_key: str = Field(default="")

    # Général
    log_level: str = Field(default="INFO")
    language: str = Field(default="fr")

    model_config = {
        "env_file": str(_env_path),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    # ── Helpers ──────────────────────────────

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token)

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_api_token)

    @property
    def figma_configured(self) -> bool:
        return bool(self.figma_access_token)

    @property
    def llm_configured(self) -> bool:
        return bool(self.cohere_api_key)

    @property
    def email_configured(self) -> bool:
        if self.email_provider == "sendgrid":
            return bool(self.sendgrid_api_key)
        return bool(self.smtp_user and self.smtp_password)


def get_settings() -> Settings:
    """Retourne l'instance Settings (singleton fonctionnel via cache)."""
    return Settings()
