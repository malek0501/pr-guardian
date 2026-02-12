"""
Point d'entrée CLI & Webhook — PR-Guardian Orchestrator.

Modes :
  - CLI    : python -m pr_guardian --repo owner/repo --pr 42
  - Server : python -m pr_guardian --server --port 8080
"""

from __future__ import annotations

import asyncio
import json
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pr_guardian.config import get_settings
from pr_guardian.models import FinalReport, Verdict
from pr_guardian.orchestrator import Orchestrator
from pr_guardian.utils.logger import setup_logging

console = Console()


# ════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════

@click.group(invoke_without_command=True)
@click.option("--repo", "-r", help="Repository (owner/repo)", required=False)
@click.option("--pr", "-p", "pr_number", type=int, help="Numéro de la PR", required=False)
@click.option("--branch", "-b", default="", help="Branche source (optionnel)")
@click.option("--server", is_flag=True, help="Lancer le serveur webhook")
@click.option("--port", default=8080, type=int, help="Port du serveur webhook")
@click.option("--json-output", is_flag=True, help="Sortie JSON brute")
@click.pass_context
def main(ctx: click.Context, repo: str | None, pr_number: int | None,
         branch: str, server: bool, port: int, json_output: bool) -> None:
    """🛡️ PR-Guardian Orchestrator — Revue automatique de Pull Requests."""
    setup_logging()

    if server:
        _run_server(port)
        return

    if not repo or not pr_number:
        console.print(
            Panel(
                "[bold red]Paramètres manquants.[/]\n\n"
                "Usage :\n"
                "  python -m pr_guardian --repo owner/repo --pr 42\n"
                "  python -m pr_guardian --server --port 8080",
                title="🛡️ PR-Guardian",
            )
        )
        sys.exit(1)

    # Exécuter la revue
    report = asyncio.run(_run_review(repo, pr_number, branch))

    if json_output:
        console.print_json(report.model_dump_json(indent=2))
    else:
        _display_report(report)


async def _run_review(repo: str, pr_number: int, branch: str) -> FinalReport:
    """Lance la revue complète."""
    console.print(Panel(
        f"[bold cyan]Revue de PR : {repo} #{pr_number}[/]\n"
        f"Branche : {branch or '(auto-détectée)'}",
        title="🛡️ PR-Guardian",
    ))

    orchestrator = Orchestrator()
    report = await orchestrator.review_pr(repo, pr_number, branch)
    return report


def _display_report(report: FinalReport) -> None:
    """Affiche le rapport final en mode Rich dans le terminal."""
    v = report.verdict
    verdict_color = {
        Verdict.PASS: "green",
        Verdict.FAIL: "red",
        Verdict.BLOCKED: "yellow",
    }
    color = verdict_color.get(v.verdict, "white")
    emoji = "✅" if v.verdict == Verdict.PASS else ("❌" if v.verdict == Verdict.FAIL else "🚫")

    # Verdict
    console.print()
    console.print(Panel(
        f"[bold {color}]{emoji} {v.verdict.value}[/]  —  "
        f"Score de confiance : [bold]{v.confidence_score}/100[/]",
        title="⚖️ Verdict Final",
        border_style=color,
    ))

    # Justification
    console.print("\n[bold]Justification :[/]")
    for j in v.justification:
        console.print(f"  • {j}")

    # Table de validation
    table = Table(title="\n📊 Table de Validation")
    table.add_column("Catégorie", style="cyan")
    table.add_column("Item")
    table.add_column("Statut", justify="center")
    table.add_column("Preuve")

    for row in report.validation_table:
        status_style = "green" if row.status.value in ("OK", "PASS") else (
            "red" if row.status.value in ("FAIL", "MISMATCH") else "yellow"
        )
        table.add_row(
            row.category,
            row.item[:60],
            f"[{status_style}]{row.status.value}[/]",
            row.evidence[:80],
        )
    console.print(table)

    # Must-fix
    if v.must_fix:
        console.print("\n[bold red]🔧 MUST-FIX :[/]")
        for i, mf in enumerate(v.must_fix, 1):
            console.print(f"  {i}. [{mf.severity.value}] {mf.description}")
            if mf.location:
                console.print(f"     📍 {mf.location}")
            if mf.suggestion:
                console.print(f"     💡 {mf.suggestion}")

    console.print()


# ════════════════════════════════════════════
#  WEBHOOK SERVER (FastAPI)
# ════════════════════════════════════════════

def _run_server(port: int) -> None:
    """Lance le serveur FastAPI pour recevoir les webhooks GitHub."""
    try:
        import uvicorn
        from pr_guardian.webhook import create_app

        console.print(Panel(
            f"[bold green]Serveur webhook démarré sur le port {port}[/]\n"
            "En attente d'événements GitHub Pull Request…",
            title="🛡️ PR-Guardian Server",
        ))
        app = create_app()
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    except ImportError:
        console.print("[red]FastAPI/Uvicorn requis pour le mode serveur.[/]")
        console.print("pip install fastapi uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
