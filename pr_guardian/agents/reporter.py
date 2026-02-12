"""
Agent 5 — Reporter & Notifier.

Génère les rapports finaux, prépare les emails et les actions Jira.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.models import (
    CheckStatus,
    EmailPayload,
    FinalReport,
    JudgeVerdict,
    PRContext,
    ValidationRow,
    Verdict,
    CodeAnalysisResult,
    UMLCheckResult,
    FigmaCheckResult,
    JiraValidationResult,
)


class ReporterAgent(BaseAgent):
    """Agent 5 : génère les rapports, emails, et actions Jira."""

    name = "Reporter"

    async def run(
        self,
        context: PRContext,
        verdict: JudgeVerdict | None = None,
        code_analysis: CodeAnalysisResult | None = None,
        uml_check: UMLCheckResult | None = None,
        figma_check: FigmaCheckResult | None = None,
        jira_validation: JiraValidationResult | None = None,
        **kwargs: Any,
    ) -> FinalReport:
        self._log_start(context)

        if verdict is None:
            verdict = JudgeVerdict(
                verdict=Verdict.BLOCKED,
                confidence_score=0,
                justification=["Aucun verdict du Judge disponible."],
            )

        # ── Table de validation ─────────────
        validation_table = self._build_validation_table(
            jira_validation, uml_check, figma_check
        )

        # ── Emails ──────────────────────────
        if verdict.verdict == Verdict.PASS:
            sm_email = self._build_scrum_master_email(context, verdict, validation_table)
            dev_email = ""
        else:
            sm_email = ""
            dev_email = self._build_dev_email(context, verdict, validation_table)

        # ── Jira action ─────────────────────
        jira_payload, jira_comment = self._build_jira_action(context, verdict)

        report = FinalReport(
            timestamp=datetime.now(UTC),
            pr_context=context,
            verdict=verdict,
            validation_table=validation_table,
            code_analysis=code_analysis,
            uml_check=uml_check,
            figma_check=figma_check,
            jira_validation=jira_validation,
            scrum_master_email_draft=sm_email,
            dev_email_draft=dev_email,
            jira_transition_payload=jira_payload,
            jira_comment=jira_comment,
        )

        self._log_done(context)
        return report

    # ── Table de validation ─────────────────

    @staticmethod
    def _build_validation_table(
        jira: JiraValidationResult | None,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
    ) -> list[ValidationRow]:
        rows: list[ValidationRow] = []

        # Jira AC
        if jira:
            for ac in jira.acceptance_criteria:
                rows.append(ValidationRow(
                    category="Jira AC",
                    item=f"[{ac.id}] {ac.description[:80]}",
                    status=ac.status,
                    evidence=ac.evidence,
                ))
            for dod in jira.definition_of_done:
                rows.append(ValidationRow(
                    category="Jira DoD",
                    item=f"[{dod.id}] {dod.description[:80]}",
                    status=dod.status,
                    evidence=dod.evidence,
                ))
        else:
            rows.append(ValidationRow(
                category="Jira AC",
                item="Non disponible",
                status=CheckStatus.BLOCKED,
                evidence="Aucun accès Jira.",
            ))

        # UML
        if uml:
            rows.append(ValidationRow(
                category="UML",
                item=uml.summary or "Vérification UML",
                status=uml.status,
                evidence=f"{len(uml.mismatches)} écart(s)" if uml.mismatches else "OK",
            ))
        else:
            rows.append(ValidationRow(
                category="UML",
                item="Non disponible",
                status=CheckStatus.BLOCKED,
                evidence="Aucun fichier UML.",
            ))

        # Figma
        if figma:
            rows.append(ValidationRow(
                category="Figma",
                item=figma.summary or "Vérification Figma",
                status=figma.status,
                evidence=f"{len(figma.mappings)} mapping(s)" if figma.mappings else "OK",
            ))
        else:
            rows.append(ValidationRow(
                category="Figma",
                item="Non disponible",
                status=CheckStatus.BLOCKED,
                evidence="Aucun lien Figma.",
            ))

        return rows

    # ── Email Scrum Master (PASS) ───────────

    @staticmethod
    def _build_scrum_master_email(
        ctx: PRContext, verdict: JudgeVerdict, table: list[ValidationRow]
    ) -> str:
        lines = [
            f"<h2>✅ PR #{ctx.pr_number} — PASS (score: {verdict.confidence_score}/100)</h2>",
            f"<p><strong>Repo :</strong> {ctx.repo}<br/>",
            f"<strong>Branche :</strong> {ctx.branch}<br/>",
            f"<strong>Auteur :</strong> {ctx.pr_author}<br/>",
            f"<strong>Jira :</strong> {ctx.jira_key or 'N/A'}</p>",
            "<h3>Justification</h3><ul>",
        ]
        for j in verdict.justification:
            lines.append(f"  <li>{j}</li>")
        lines.append("</ul>")

        lines.append("<h3>Table de validation</h3>")
        lines.append("<table border='1' cellpadding='4'><tr>"
                     "<th>Catégorie</th><th>Item</th><th>Statut</th><th>Preuve</th></tr>")
        for row in table:
            lines.append(
                f"<tr><td>{row.category}</td><td>{row.item}</td>"
                f"<td>{row.status.value}</td><td>{row.evidence}</td></tr>"
            )
        lines.append("</table>")
        lines.append("<p><em>— PR-Guardian Orchestrator</em></p>")
        return "\n".join(lines)

    # ── Email Dev (FAIL/BLOCKED) ────────────

    @staticmethod
    def _build_dev_email(
        ctx: PRContext, verdict: JudgeVerdict, table: list[ValidationRow]
    ) -> str:
        emoji = "❌" if verdict.verdict == Verdict.FAIL else "🚫"
        lines = [
            f"<h2>{emoji} PR #{ctx.pr_number} — {verdict.verdict.value} "
            f"(score: {verdict.confidence_score}/100)</h2>",
            f"<p><strong>Repo :</strong> {ctx.repo}<br/>",
            f"<strong>Branche :</strong> {ctx.branch}<br/>",
            f"<strong>Jira :</strong> {ctx.jira_key or 'N/A'}</p>",
            "<h3>Justification</h3><ul>",
        ]
        for j in verdict.justification:
            lines.append(f"  <li>{j}</li>")
        lines.append("</ul>")

        if verdict.must_fix:
            lines.append("<h3>🔧 MUST-FIX (priorisé)</h3><ol>")
            for item in verdict.must_fix:
                lines.append(
                    f"  <li><strong>[{item.severity.value}]</strong> {item.description}<br/>"
                    f"  📍 {item.location}<br/>"
                    f"  💡 {item.suggestion}</li>"
                )
            lines.append("</ol>")

        lines.append("<h3>Table de validation</h3>")
        lines.append("<table border='1' cellpadding='4'><tr>"
                     "<th>Catégorie</th><th>Item</th><th>Statut</th><th>Preuve</th></tr>")
        for row in table:
            lines.append(
                f"<tr><td>{row.category}</td><td>{row.item}</td>"
                f"<td>{row.status.value}</td><td>{row.evidence}</td></tr>"
            )
        lines.append("</table>")
        lines.append("<p><em>— PR-Guardian Orchestrator</em></p>")
        return "\n".join(lines)

    # ── Action Jira ─────────────────────────

    @staticmethod
    def _build_jira_action(
        ctx: PRContext, verdict: JudgeVerdict
    ) -> tuple[dict[str, Any], str]:
        settings = get_settings()

        if not ctx.jira_key:
            return {}, ""

        if verdict.verdict == Verdict.PASS:
            transition_id = settings.jira_done_transition_id
            comment = (
                f"✅ PR #{ctx.pr_number} validée par PR-Guardian "
                f"(score: {verdict.confidence_score}/100).\n"
                f"Tous les critères d'acceptation sont satisfaits."
            )
        else:
            transition_id = settings.jira_needs_fix_transition_id
            must_fix_text = "\n".join(
                f"- [{mf.severity.value}] {mf.description}" for mf in verdict.must_fix
            )
            comment = (
                f"❌ PR #{ctx.pr_number} — {verdict.verdict.value} "
                f"(score: {verdict.confidence_score}/100).\n"
                f"Items à corriger :\n{must_fix_text}"
            )

        payload = {
            "issue_key": ctx.jira_key,
            "transition_id": transition_id,
            "comment": comment,
        }
        return payload, comment
