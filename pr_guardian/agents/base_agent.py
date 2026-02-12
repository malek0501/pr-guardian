"""
Agent de base (abstrait) — PR-Guardian Orchestrator.

Chaque agent hérite de BaseAgent et implémente sa logique métier.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from pr_guardian.models import PRContext


class BaseAgent(ABC):
    """Classe abstraite pour tous les agents PR-Guardian."""

    name: str = "BaseAgent"

    def __init__(self):
        self.logger = logging.getLogger(f"pr_guardian.agent.{self.name}")

    @abstractmethod
    async def run(self, context: PRContext, **kwargs: Any) -> Any:
        """Exécute la logique de l'agent et retourne son résultat typé."""
        ...

    def _log_start(self, context: PRContext) -> None:
        self.logger.info(f"[{self.name}] Démarrage — PR {context.repo}#{context.pr_number}")

    def _log_done(self, context: PRContext) -> None:
        self.logger.info(f"[{self.name}] Terminé — PR {context.repo}#{context.pr_number}")

    def _log_blocked(self, reason: str) -> None:
        self.logger.warning(f"[{self.name}] BLOQUÉ — {reason}")
