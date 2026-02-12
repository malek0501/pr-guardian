"""
Webhook Server — PR-Guardian Orchestrator.

Reçoit les webhooks GitHub (événement pull_request) et déclenche
le workflow de revue automatiquement.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from pr_guardian.config import get_settings
from pr_guardian.orchestrator import Orchestrator

logger = logging.getLogger("pr_guardian.webhook")


def create_app() -> FastAPI:
    """Crée et configure l'application FastAPI."""
    app = FastAPI(
        title="PR-Guardian Orchestrator",
        description="Webhook receiver for GitHub Pull Request events",
        version="1.0.0",
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "pr-guardian"}

    @app.post("/webhook/github")
    async def github_webhook(request: Request):
        """Endpoint pour les webhooks GitHub."""
        body = await request.body()
        payload = json.loads(body)

        # Vérifier l'événement
        event = request.headers.get("X-GitHub-Event", "")
        if event != "pull_request":
            return JSONResponse(
                {"message": f"Événement ignoré : {event}"},
                status_code=200,
            )

        # Vérifier l'action
        action = payload.get("action", "")
        if action not in ("opened", "synchronize", "reopened"):
            return JSONResponse(
                {"message": f"Action ignorée : {action}"},
                status_code=200,
            )

        # Extraire les infos PR
        pr = payload.get("pull_request", {})
        repo_name = payload.get("repository", {}).get("full_name", "")
        pr_number = pr.get("number", 0)
        branch = pr.get("head", {}).get("ref", "")

        if not repo_name or not pr_number:
            raise HTTPException(status_code=400, detail="Payload incomplet.")

        logger.info(f"Webhook reçu : {repo_name}#{pr_number} ({action})")

        # Lancer la revue en arrière-plan
        asyncio.create_task(_run_review_bg(repo_name, pr_number, branch))

        return JSONResponse({
            "message": "Revue déclenchée.",
            "repo": repo_name,
            "pr": pr_number,
            "branch": branch,
        })

    return app


async def _run_review_bg(repo: str, pr_number: int, branch: str) -> None:
    """Exécute la revue en tâche de fond."""
    try:
        orchestrator = Orchestrator()
        report = await orchestrator.review_pr(repo, pr_number, branch)
        logger.info(
            f"Revue terminée : {repo}#{pr_number} → "
            f"{report.verdict.verdict.value} ({report.verdict.confidence_score}/100)"
        )
    except Exception as exc:
        logger.error(f"Erreur revue {repo}#{pr_number} : {exc}", exc_info=True)
