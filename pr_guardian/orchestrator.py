"""
Orchestrateur principal — PR-Guardian.

Coordonne les 5 agents + le Judge selon le workflow défini :
  Étape 0 — Récupération contextuelle (Jira key, Figma link, UML files)
  Étape 1 — Exécution parallèle Agents 1→4
  Étape 2 — Envoi au Judge (dossier de preuves consolidé)
  Étape 3 — Actions (email, Jira transition, commentaire PR)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pr_guardian.agents.code_analyst import CodeAnalystAgent
from pr_guardian.agents.figma_checker import FigmaCheckerAgent
from pr_guardian.agents.jira_validator import JiraValidatorAgent
from pr_guardian.agents.judge import JudgeAgent
from pr_guardian.agents.reporter import ReporterAgent
from pr_guardian.agents.uml_checker import UMLCheckerAgent
from pr_guardian.config import get_settings
from pr_guardian.integrations.email_client import EmailClient
from pr_guardian.integrations.github_client import GitHubClient
from pr_guardian.integrations.jira_client import JiraClient
from pr_guardian.integrations.figma_client import FigmaClient
from pr_guardian.models import (
    CodeAnalysisResult,
    EmailPayload,
    FigmaCheckResult,
    FinalReport,
    JiraValidationResult,
    PRContext,
    UMLCheckResult,
    Verdict,
)

logger = logging.getLogger("pr_guardian.orchestrator")


class Orchestrator:
    """
    Chef d'orchestre PR-Guardian.

    Pilote le workflow complet : de la récupération contextuelle
    jusqu'à la notification finale.
    """

    def __init__(self):
        self._settings = get_settings()
        self._gh: GitHubClient | None = None
        self._jira: JiraClient | None = None
        self._figma: FigmaClient | None = None
        self._email: EmailClient | None = None

    # ── Lazy init des clients ───────────────

    def _get_github(self) -> GitHubClient:
        if self._gh is None:
            self._gh = GitHubClient()
        return self._gh

    def _get_jira(self) -> JiraClient | None:
        if self._jira is None and self._settings.jira_configured:
            try:
                self._jira = JiraClient()
            except Exception as exc:
                logger.warning(f"Jira non disponible : {exc}")
        return self._jira

    def _get_figma(self) -> FigmaClient | None:
        if self._figma is None and self._settings.figma_configured:
            try:
                self._figma = FigmaClient()
            except Exception as exc:
                logger.warning(f"Figma non disponible : {exc}")
        return self._figma

    def _get_email(self) -> EmailClient | None:
        if self._email is None:
            self._email = EmailClient()
        return self._email

    # ════════════════════════════════════════
    #  WORKFLOW PRINCIPAL
    # ════════════════════════════════════════

    async def review_pr(self, repo: str, pr_number: int, branch: str = "") -> FinalReport:
        """
        Point d'entrée principal : exécute le workflow complet de revue.

        Args:
            repo: owner/repo (ex: "Team7/mon-projet")
            pr_number: numéro de la PR
            branch: branche source (optionnel, sera récupérée si vide)

        Returns:
            FinalReport avec verdict, validation table, emails, actions Jira.
        """
        logger.info(f"🛡️ PR-Guardian — Début de la revue : {repo}#{pr_number}")

        # ── ÉTAPE 0 : Récupération contextuelle ──
        context = await self._step0_context(repo, pr_number, branch)
        logger.info(
            f"📋 Contexte : Jira={context.jira_key}, "
            f"Figma={'oui' if context.figma_link else 'non'}, "
            f"UML={len(context.uml_files)} fichier(s)"
        )

        # ── ÉTAPE 1 : Exécution parallèle Agents 1→4 ──
        code_analysis, uml_check, figma_check, jira_validation = (
            await self._step1_parallel_agents(context)
        )

        # ── ÉTAPE 2 : LLM-as-a-Judge ──
        judge = JudgeAgent()
        verdict = await judge.run(
            context,
            code_analysis=code_analysis,
            uml_check=uml_check,
            figma_check=figma_check,
            jira_validation=jira_validation,
        )
        logger.info(
            f"⚖️ Verdict Judge : {verdict.verdict.value} "
            f"(confiance: {verdict.confidence_score}/100)"
        )

        # ── ÉTAPE 3 : Reporter + Actions ──
        report = await self._step3_report_and_act(
            context, verdict,
            code_analysis, uml_check, figma_check, jira_validation,
        )

        logger.info(f"✅ PR-Guardian — Revue terminée : {verdict.verdict.value}")
        return report

    # ════════════════════════════════════════
    #  ÉTAPE 0 — Récupération contextuelle
    # ════════════════════════════════════════

    async def _step0_context(
        self, repo: str, pr_number: int, branch: str
    ) -> PRContext:
        """Construit le PRContext enrichi."""
        gh = self._get_github()

        # Contexte de base depuis GitHub
        context = gh.build_pr_context(repo, pr_number)
        if branch:
            context.branch = branch

        # Extraction Jira key
        jira_key = gh.extract_jira_key(context)
        if jira_key:
            context.jira_key = jira_key
            logger.info(f"🔑 Jira key extraite : {jira_key}")

        # Recherche lien Figma
        figma_links = gh.find_figma_links(repo, context.branch or "main")

        # Aussi chercher dans Jira si disponible
        if jira_key and self._get_jira():
            try:
                jira_fields = self._get_jira().get_issue_fields(jira_key)
                figma_links.extend(jira_fields.get("figma_links", []))
            except Exception:
                pass

        if figma_links:
            context.figma_link = figma_links[0]
            logger.info(f"🎨 Figma trouvé : {context.figma_link}")

        # Recherche fichiers UML
        uml_files = gh.find_uml_files(repo, context.branch or "main")
        context.uml_files = uml_files
        if uml_files:
            logger.info(f"📐 {len(uml_files)} fichier(s) UML trouvé(s)")

        return context

    # ════════════════════════════════════════
    #  ÉTAPE 1 — Agents parallèles
    # ════════════════════════════════════════

    async def _step1_parallel_agents(
        self, context: PRContext
    ) -> tuple[
        CodeAnalysisResult | None,
        UMLCheckResult | None,
        FigmaCheckResult | None,
        JiraValidationResult | None,
    ]:
        """Exécute les agents 1 à 4 en parallèle."""
        logger.info("🚀 Étape 1 — Lancement des agents en parallèle…")

        gh = self._get_github()

        # Agents
        agent1 = CodeAnalystAgent(github_client=gh)
        agent2 = UMLCheckerAgent(github_client=gh)
        agent3 = FigmaCheckerAgent(github_client=gh, figma_client=self._get_figma())
        agent4 = JiraValidatorAgent(jira_client=self._get_jira())

        # Exécution parallèle
        results = await asyncio.gather(
            self._safe_run(agent1, context),
            self._safe_run(agent2, context),
            self._safe_run(agent3, context),
            self._safe_run(agent4, context),
            return_exceptions=True,
        )

        code_analysis = results[0] if isinstance(results[0], CodeAnalysisResult) else None
        uml_check = results[1] if isinstance(results[1], UMLCheckResult) else None
        figma_check = results[2] if isinstance(results[2], FigmaCheckResult) else None
        jira_validation = results[3] if isinstance(results[3], JiraValidationResult) else None

        # Relancer Agent 2, 3, 4 avec le résultat d'analyse de code (si disponible)
        if code_analysis:
            logger.info("🔄 Re-exécution Agents 2-4 avec les résultats du code…")
            results2 = await asyncio.gather(
                self._safe_run(agent2, context, code_analysis=code_analysis),
                self._safe_run(agent3, context, code_analysis=code_analysis),
                self._safe_run(
                    agent4, context,
                    code_analysis=code_analysis,
                    uml_check=uml_check,
                    figma_check=figma_check,
                ),
                return_exceptions=True,
            )
            if isinstance(results2[0], UMLCheckResult):
                uml_check = results2[0]
            if isinstance(results2[1], FigmaCheckResult):
                figma_check = results2[1]
            if isinstance(results2[2], JiraValidationResult):
                jira_validation = results2[2]

        logger.info("✔️ Étape 1 terminée.")
        return code_analysis, uml_check, figma_check, jira_validation

    @staticmethod
    async def _safe_run(agent: Any, context: PRContext, **kwargs: Any) -> Any:
        """Exécute un agent en capturant les exceptions."""
        try:
            return await agent.run(context, **kwargs)
        except Exception as exc:
            logger.error(f"[{agent.name}] Erreur : {exc}")
            return exc

    # ════════════════════════════════════════
    #  ÉTAPE 3 — Rapport + Actions
    # ════════════════════════════════════════

    async def _step3_report_and_act(
        self,
        context: PRContext,
        verdict: Any,
        code_analysis: CodeAnalysisResult | None,
        uml_check: UMLCheckResult | None,
        figma_check: FigmaCheckResult | None,
        jira_validation: JiraValidationResult | None,
    ) -> FinalReport:
        """Génère le rapport final et exécute les actions."""
        logger.info("📝 Étape 3 — Génération du rapport et actions…")

        # Agent 5 : Reporter
        reporter = ReporterAgent()
        report = await reporter.run(
            context,
            verdict=verdict,
            code_analysis=code_analysis,
            uml_check=uml_check,
            figma_check=figma_check,
            jira_validation=jira_validation,
        )

        # ── Actions ─────────────────────────
        await self._execute_actions(context, report)

        return report

    async def _execute_actions(self, context: PRContext, report: FinalReport) -> None:
        """Exécute les actions post-verdict (email, Jira, commentaire PR)."""

        # 1. Email
        email_client = self._get_email()
        if email_client and self._settings.email_configured:
            if report.verdict.verdict == Verdict.PASS and report.scrum_master_email_draft:
                # On aurait besoin de l'email du SM — pour l'instant, log seulement
                logger.info("📧 Email PASS prêt (Scrum Master).")
            elif report.dev_email_draft:
                if context.pr_author_email:
                    payload = EmailPayload(
                        to=[context.pr_author_email],
                        subject=f"PR-Guardian — {report.verdict.verdict.value} — PR #{context.pr_number}",
                        body_html=report.dev_email_draft,
                    )
                    email_client.send(payload)
                else:
                    logger.warning("Email dev non envoyé : adresse auteur inconnue.")

        # 2. Jira transition
        jira = self._get_jira()
        if jira and report.jira_transition_payload:
            try:
                jira.transition_issue(
                    report.jira_transition_payload["issue_key"],
                    report.jira_transition_payload["transition_id"],
                    report.jira_transition_payload.get("comment", ""),
                )
            except Exception as exc:
                logger.error(f"Jira transition échouée : {exc}")

        # 3. Commentaire PR (optionnel)
        try:
            gh = self._get_github()
            comment_body = self._format_pr_comment(report)
            gh.post_pr_comment(context.repo, context.pr_number, comment_body)
        except Exception as exc:
            logger.warning(f"Commentaire PR non posté : {exc}")

    @staticmethod
    def _format_pr_comment(report: FinalReport) -> str:
        """Formate le commentaire à poster sur la PR."""
        v = report.verdict
        emoji = "✅" if v.verdict == Verdict.PASS else ("❌" if v.verdict == Verdict.FAIL else "🚫")

        lines = [
            f"## {emoji} PR-Guardian — {v.verdict.value} (score: {v.confidence_score}/100)",
            "",
        ]

        lines.append("### Justification")
        for j in v.justification:
            lines.append(f"- {j}")
        lines.append("")

        if v.must_fix:
            lines.append("### 🔧 Items à corriger")
            for mf in v.must_fix:
                lines.append(f"- **[{mf.severity.value}]** {mf.description}")
                if mf.location:
                    lines.append(f"  📍 {mf.location}")
                if mf.suggestion:
                    lines.append(f"  💡 {mf.suggestion}")
            lines.append("")

        lines.append("### Table de validation")
        lines.append("| Catégorie | Item | Statut | Preuve |")
        lines.append("|-----------|------|--------|--------|")
        for row in report.validation_table:
            lines.append(f"| {row.category} | {row.item} | {row.status.value} | {row.evidence} |")

        lines.append("")
        lines.append("---")
        lines.append("*PR-Guardian Orchestrator — Team7*")

        return "\n".join(lines)
