"""
LLM-as-a-Judge — PR-Guardian Orchestrator.

Arbitre final : reçoit les preuves des 4 agents, produit un verdict
PASS / FAIL / BLOCKED avec un score de confiance et une justification.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import cohere

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.models import (
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    JiraValidationResult,
    JudgeVerdict,
    MustFixItem,
    PRContext,
    Severity,
    UMLCheckResult,
    Verdict,
)

logger = logging.getLogger("pr_guardian.judge")


# ── Prompt système ──────────────────────────

SYSTEM_PROMPT = """\
Tu es le LLM-as-a-Judge du système PR-Guardian. Tu reçois un dossier de preuves
provenant de 4 agents spécialisés ayant analysé une Pull Request.

Ton rôle : juger la cohérence des preuves et produire un verdict.

RÈGLES STRICTES :
1. PASS uniquement si :
   (a) Tous les AC critiques = PASS
   (b) UML cohérent ou mis à jour dans la PR
   (c) Figma conforme sur les éléments exigés
   (d) Tests/qualité minimum respectés ou justifiés
2. FAIL si au moins un AC critique est en échec ou un mismatch important
3. BLOCKED si des informations critiques sont manquantes (Jira inaccessible, Figma introuvable, etc.)
4. Ne jamais halluciner — se baser UNIQUEMENT sur les preuves fournies
5. Score de confiance [0..100] basé sur la complétude et la qualité des preuves

Tu dois répondre UNIQUEMENT en JSON valide avec cette structure exacte :
{
  "verdict": "PASS" | "FAIL" | "BLOCKED",
  "confidence_score": <int 0-100>,
  "justification": ["point 1", "point 2", ... max 10],
  "must_fix": [
    {
      "description": "...",
      "location": "fichier/classe/diagram/frame",
      "suggestion": "...",
      "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    }
  ]
}
"""


class JudgeAgent(BaseAgent):
    """LLM-as-a-Judge : arbitre final."""

    name = "Judge"

    def __init__(self):
        super().__init__()
        self._settings = get_settings()

    async def run(
        self,
        context: PRContext,
        code_analysis: CodeAnalysisResult | None = None,
        uml_check: UMLCheckResult | None = None,
        figma_check: FigmaCheckResult | None = None,
        jira_validation: JiraValidationResult | None = None,
        **kwargs: Any,
    ) -> JudgeVerdict:
        self._log_start(context)

        # Si pas de LLM configuré, fallback heuristique
        if not self._settings.llm_configured:
            self.logger.warning("Cohere non configuré — utilisation du verdict heuristique.")
            return self._heuristic_verdict(
                code_analysis, uml_check, figma_check, jira_validation
            )

        # ── Construire le dossier de preuves ──
        evidence = self._build_evidence_dossier(
            context, code_analysis, uml_check, figma_check, jira_validation
        )

        # ── Appeler le LLM ─────────────────
        try:
            client = cohere.ClientV2(api_key=self._settings.cohere_api_key)
            response = client.chat(
                model=self._settings.cohere_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": evidence},
                ],
                max_tokens=self._settings.cohere_max_tokens,
                temperature=0.1,  # Très déterministe
                response_format={"type": "json_object"},
            )

            raw = response.message.content[0].text if response.message.content else "{}"
            return self._parse_llm_response(raw)

        except Exception as exc:
            self.logger.error(f"Erreur LLM Judge : {exc}")
            self.logger.info("Fallback vers verdict heuristique.")
            return self._heuristic_verdict(
                code_analysis, uml_check, figma_check, jira_validation
            )

    # ── Construction du dossier de preuves ──

    @staticmethod
    def _build_evidence_dossier(
        ctx: PRContext,
        code: CodeAnalysisResult | None,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
        jira: JiraValidationResult | None,
    ) -> str:
        sections: list[str] = []

        sections.append(
            f"## CONTEXTE PR\n"
            f"Repo: {ctx.repo}, PR #{ctx.pr_number}, Branche: {ctx.branch}\n"
            f"Titre: {ctx.pr_title}\n"
            f"Jira: {ctx.jira_key or 'NON TROUVÉ'}\n"
            f"Figma: {ctx.figma_link or 'NON TROUVÉ'}"
        )

        if code:
            sections.append(
                f"## AGENT 1 — Analyse Code\n"
                f"{code.summary}\n"
                f"Classes: {', '.join(code.classes_touched) or 'aucune'}\n"
                f"Méthodes: {', '.join(code.methods_touched) or 'aucune'}\n"
                f"Endpoints: {', '.join(code.endpoints) or 'aucun'}\n"
                f"Tests ajoutés: {len(code.tests_added)}, modifiés: {len(code.tests_modified)}\n"
                f"Couverture: {code.test_coverage_info}\n"
                f"Points sensibles: {', '.join(code.sensitive_points) or 'aucun'}"
            )
        else:
            sections.append("## AGENT 1 — Analyse Code\nNON DISPONIBLE")

        if uml:
            mismatches_text = "\n".join(
                f"- [{m.severity.value}] {m.element}: {m.issue}" for m in uml.mismatches
            ) or "Aucun"
            sections.append(
                f"## AGENT 2 — UML\n"
                f"Statut: {uml.status.value}\n"
                f"Diagrammes: {len(uml.diagrams_found)}\n"
                f"Résumé: {uml.summary}\n"
                f"Écarts:\n{mismatches_text}"
            )
        else:
            sections.append("## AGENT 2 — UML\nNON DISPONIBLE")

        if figma:
            mappings_text = "\n".join(
                f"- {m.requirement.frame_name}: {m.implementation_status.value} — "
                f"{m.evidence or m.gap}"
                for m in figma.mappings
            ) or "Aucun"
            sections.append(
                f"## AGENT 3 — Figma\n"
                f"Statut: {figma.status.value}\n"
                f"Lien: {figma.figma_link}\n"
                f"Résumé: {figma.summary}\n"
                f"Mappings:\n{mappings_text}"
            )
        else:
            sections.append("## AGENT 3 — Figma\nNON DISPONIBLE")

        if jira:
            ac_text = "\n".join(
                f"- [{ac.id}] {ac.status.value}: {ac.description[:100]}"
                for ac in jira.acceptance_criteria
            ) or "Aucun"
            dod_text = "\n".join(
                f"- [{d.id}] {d.status.value}: {d.description[:100]}"
                for d in jira.definition_of_done
            ) or "Aucun"
            sections.append(
                f"## AGENT 4 — Jira\n"
                f"Issue: {jira.jira_key} — {jira.jira_summary}\n"
                f"Statut Jira: {jira.jira_status}\n"
                f"Résumé: {jira.summary}\n"
                f"Verdict recommandé: {jira.recommended_verdict.value}\n"
                f"Acceptance Criteria:\n{ac_text}\n"
                f"Definition of Done:\n{dod_text}"
            )
        else:
            sections.append("## AGENT 4 — Jira\nNON DISPONIBLE")

        return "\n\n".join(sections)

    # ── Parsing réponse LLM ─────────────────

    @staticmethod
    def _parse_llm_response(raw: str) -> JudgeVerdict:
        """Parse la réponse JSON du LLM en JudgeVerdict."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return JudgeVerdict(
                verdict=Verdict.BLOCKED,
                confidence_score=0,
                justification=["Erreur : réponse LLM non-JSON."],
            )

        # Verdict
        v = data.get("verdict", "BLOCKED").upper()
        verdict = Verdict.BLOCKED
        if v == "PASS":
            verdict = Verdict.PASS
        elif v == "FAIL":
            verdict = Verdict.FAIL

        # Must-fix
        must_fix: list[MustFixItem] = []
        for item in data.get("must_fix", []):
            sev = item.get("severity", "HIGH").upper()
            severity = Severity.HIGH
            try:
                severity = Severity(sev)
            except ValueError:
                pass
            must_fix.append(MustFixItem(
                description=item.get("description", ""),
                location=item.get("location", ""),
                suggestion=item.get("suggestion", ""),
                severity=severity,
            ))

        return JudgeVerdict(
            verdict=verdict,
            confidence_score=min(100, max(0, int(data.get("confidence_score", 0)))),
            justification=data.get("justification", [])[:10],
            must_fix=must_fix,
        )

    # ── Verdict heuristique (fallback) ──────

    @staticmethod
    def _heuristic_verdict(
        code: CodeAnalysisResult | None,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
        jira: JiraValidationResult | None,
    ) -> JudgeVerdict:
        """Produit un verdict sans LLM, basé sur les statuts des agents."""
        justification: list[str] = []
        must_fix: list[MustFixItem] = []
        blocked_reasons: list[str] = []
        fail_reasons: list[str] = []
        score = 50  # Base

        # Code
        if code:
            justification.append(
                f"Analyse code : {code.raw_diff_stats.get('total_files', 0)} fichier(s), "
                f"{len(code.classes_touched)} classe(s), {len(code.endpoints)} endpoint(s)."
            )
            if code.tests_added or code.tests_modified:
                score += 10
                justification.append("Tests présents ✅")
            else:
                score -= 10
                justification.append("⚠️ Aucun test détecté.")
                must_fix.append(MustFixItem(
                    description="Aucun test ajouté/modifié.",
                    location="(tests/)",
                    suggestion="Ajouter des tests unitaires pour les changements.",
                    severity=Severity.MEDIUM,
                ))
        else:
            blocked_reasons.append("Analyse de code non disponible.")

        # UML
        if uml:
            if uml.status == CheckStatus.OK:
                score += 10
                justification.append("UML cohérent ✅")
            elif uml.status == CheckStatus.MISMATCH:
                score -= 15
                fail_reasons.append("UML incohérent.")
                justification.append(f"UML : {len(uml.mismatches)} écart(s) ❌")
                for m in uml.mismatches:
                    must_fix.append(MustFixItem(
                        description=m.issue,
                        location=m.diagram_file,
                        suggestion=m.suggestion,
                        severity=m.severity,
                    ))
            elif uml.status == CheckStatus.BLOCKED:
                blocked_reasons.append("UML non accessible.")
        else:
            blocked_reasons.append("UML non vérifié.")

        # Figma
        if figma:
            if figma.status == CheckStatus.OK:
                score += 10
                justification.append("Figma conforme ✅")
            elif figma.status == CheckStatus.MISMATCH:
                score -= 15
                fail_reasons.append("Figma non conforme.")
                justification.append(f"Figma : écarts détectés ❌")
                for m in figma.mappings:
                    if m.implementation_status == CheckStatus.FAIL:
                        must_fix.append(MustFixItem(
                            description=f"Figma frame '{m.requirement.frame_name}' non implémenté.",
                            location=f"Figma: {m.requirement.frame_id}",
                            suggestion=f"Implémenter le composant '{m.requirement.frame_name}'.",
                            severity=Severity.HIGH,
                        ))
            elif figma.status == CheckStatus.BLOCKED:
                blocked_reasons.append("Figma non accessible.")
        else:
            blocked_reasons.append("Figma non vérifié.")

        # Jira
        if jira:
            if jira.status == CheckStatus.OK:
                score += 20
                justification.append("Tous les AC Jira satisfaits ✅")
            elif jira.status == CheckStatus.FAIL:
                score -= 20
                fail_reasons.append("AC Jira non satisfaits.")
                for ac in jira.acceptance_criteria:
                    if ac.status == CheckStatus.FAIL:
                        justification.append(f"AC [{ac.id}] FAIL : {ac.description[:60]} ❌")
                        must_fix.append(MustFixItem(
                            description=f"AC [{ac.id}] non satisfait : {ac.description}",
                            location=f"Jira {jira.jira_key}",
                            suggestion="Implémenter ce critère d'acceptation.",
                            severity=Severity.CRITICAL,
                        ))
            elif jira.status == CheckStatus.BLOCKED:
                blocked_reasons.append("Jira non accessible.")
        else:
            blocked_reasons.append("Jira non vérifié.")

        # Déterminer le verdict
        score = max(0, min(100, score))

        if blocked_reasons:
            verdict = Verdict.BLOCKED
            justification.extend([f"🚫 BLOQUÉ : {r}" for r in blocked_reasons])
        elif fail_reasons:
            verdict = Verdict.FAIL
            justification.extend([f"❌ ÉCHEC : {r}" for r in fail_reasons])
        elif score >= 60:
            verdict = Verdict.PASS
        else:
            verdict = Verdict.FAIL
            justification.append("Score global insuffisant.")

        return JudgeVerdict(
            verdict=verdict,
            confidence_score=score,
            justification=justification[:10],
            must_fix=must_fix,
        )
