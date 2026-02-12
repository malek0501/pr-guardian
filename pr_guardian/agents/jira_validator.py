"""
Agent 4 — Jira Criteria Validator (LLM-powered).

Récupère la tâche Jira liée, extrait les acceptance criteria et
la definition of done, puis utilise Cohere LLM pour évaluer
sémantiquement si le code implémente chaque critère.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import cohere

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.integrations.jira_client import JiraClient
from pr_guardian.models import (
    AcceptanceCriterion,
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    JiraValidationResult,
    PRContext,
    UMLCheckResult,
    Verdict,
)

logger = logging.getLogger("pr_guardian.agent.JiraValidator")

# ── Prompt système pour la validation Jira ──

JIRA_VALIDATOR_SYSTEM_PROMPT = """\
Tu es un QA Lead expert. Tu reçois :
1. Les acceptance criteria et definition of done d'une tâche Jira
2. Les résultats d'analyse du code d'une Pull Request (classes, méthodes, endpoints, tests)
3. Le statut de vérification UML et Figma

Ton rôle : évaluer sémantiquement si chaque critère d'acceptation est satisfait par le code.

RÈGLES :
- Un critère est PASS si le code contient clairement des éléments qui l'implémentent
- Un critère est FAIL si aucune preuve d'implémentation n'est trouvée
- Un critère est PARTIAL si l'implémentation semble incomplète
- Ne pas halluciner : se baser UNIQUEMENT sur les preuves fournies
- Être strict mais juste dans l'évaluation

Réponds UNIQUEMENT en JSON valide :
{
  "overall_score": <int 0-100>,
  "criteria_evaluations": [
    {
      "id": "AC-1 ou DoD-1",
      "description": "texte du critère",
      "status": "PASS|FAIL|PARTIAL",
      "evidence": "preuves trouvées dans le code",
      "reasoning": "raisonnement détaillé"
    }
  ],
  "recommended_verdict": "PASS|FAIL|BLOCKED",
  "summary": "résumé en 2-3 phrases"
}
"""


class JiraValidatorAgent(BaseAgent):
    """Agent 4 : valide les critères Jira (statique + LLM)."""

    name = "JiraValidator"

    def __init__(self, jira_client: JiraClient | None = None):
        super().__init__()
        self._jira = jira_client
        self._settings = get_settings()

    def _get_jira(self) -> JiraClient:
        if self._jira is None:
            self._jira = JiraClient()
        return self._jira

    async def run(
        self,
        context: PRContext,
        code_analysis: CodeAnalysisResult | None = None,
        uml_check: UMLCheckResult | None = None,
        figma_check: FigmaCheckResult | None = None,
        **kwargs: Any,
    ) -> JiraValidationResult:
        self._log_start(context)
        result = JiraValidationResult()

        # ── Vérifier la clé Jira ────────────
        jira_key = context.jira_key
        if not jira_key:
            self._log_blocked("Aucune clé Jira trouvée dans le contexte.")
            result.status = CheckStatus.BLOCKED
            result.summary = "Aucune clé Jira associée à cette PR."
            result.recommended_verdict = Verdict.BLOCKED
            return result

        result.jira_key = jira_key

        # ── Récupérer l'issue Jira ──────────
        try:
            jira = self._get_jira()
            fields = jira.get_issue_fields(jira_key)
        except Exception as exc:
            self._log_blocked(f"Impossible de récupérer l'issue Jira {jira_key}: {exc}")
            result.status = CheckStatus.BLOCKED
            result.summary = f"Erreur d'accès à Jira pour {jira_key}: {exc}"
            result.recommended_verdict = Verdict.BLOCKED
            return result

        result.jira_summary = fields.get("summary", "")
        result.jira_description = fields.get("description", "")
        result.jira_status = fields.get("status", "")

        # ── Extraire les Acceptance Criteria ──
        ac_texts = fields.get("acceptance_criteria", [])
        dod_texts = fields.get("definition_of_done", [])

        if not ac_texts and not dod_texts:
            result.status = CheckStatus.PARTIAL
            result.summary = (
                f"Issue {jira_key} trouvée, mais aucun acceptance criteria "
                "ni definition of done détecté."
            )
            result.recommended_verdict = Verdict.BLOCKED
            return result

        # ── Tenter l'évaluation LLM ────────
        llm_result = None
        if self._settings.llm_configured and code_analysis:
            llm_result = self._llm_evaluate_criteria(
                ac_texts, dod_texts, code_analysis, uml_check, figma_check, context
            )

        if llm_result:
            # Appliquer les résultats LLM
            self._apply_llm_result(result, llm_result, ac_texts, dod_texts)
        else:
            # Fallback statique
            self._evaluate_static(result, ac_texts, dod_texts, code_analysis, uml_check, figma_check)

        self._log_done(context)
        return result

    def _llm_evaluate_criteria(
        self,
        ac_texts: list[str],
        dod_texts: list[str],
        code: CodeAnalysisResult,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
        context: PRContext,
    ) -> dict | None:
        """Appelle Cohere pour évaluer sémantiquement chaque critère."""
        try:
            # Formater les critères
            criteria_text = ""
            for i, ac in enumerate(ac_texts, 1):
                criteria_text += f"AC-{i}: {ac}\n"
            for i, dod in enumerate(dod_texts, 1):
                criteria_text += f"DoD-{i}: {dod}\n"

            # Formater les preuves
            code_info = (
                f"Classes : {', '.join(code.classes_touched) or 'aucune'}\n"
                f"Méthodes : {', '.join(code.methods_touched) or 'aucune'}\n"
                f"Endpoints : {', '.join(code.endpoints) or 'aucun'}\n"
                f"Fichiers modifiés : {', '.join(f.filename for f in code.files_modified[:20])}\n"
                f"Features : {', '.join(code.features_detected) or 'aucune'}\n"
                f"Tests ajoutés : {', '.join(code.tests_added) or 'aucun'}\n"
                f"Tests modifiés : {', '.join(code.tests_modified) or 'aucun'}\n"
                f"Couverture : {code.test_coverage_info}"
            )

            extra_info = ""
            if uml:
                extra_info += f"\nUML : statut={uml.status.value}, {len(uml.mismatches)} écart(s)"
            if figma:
                extra_info += f"\nFigma : statut={figma.status.value}, {len(figma.mappings)} mapping(s)"

            user_message = (
                f"PR: {context.repo} #{context.pr_number} — {context.pr_title}\n\n"
                f"## CRITÈRES À ÉVALUER\n{criteria_text}\n"
                f"## CODE DE LA PR\n{code_info}\n"
                f"## CONTEXTE SUPPLÉMENTAIRE{extra_info}"
            )

            client = cohere.ClientV2(api_key=self._settings.cohere_api_key)
            response = client.chat(
                model=self._settings.cohere_model,
                messages=[
                    {"role": "system", "content": JIRA_VALIDATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.message.content[0].text if response.message.content else "{}"
            analysis = json.loads(raw)
            logger.info("[JiraValidator] LLM evaluation OK — score: %s/100",
                        analysis.get("overall_score", "?"))
            return analysis

        except Exception as exc:
            logger.warning("[JiraValidator] LLM evaluation failed: %s", exc)
            return None

    def _apply_llm_result(
        self,
        result: JiraValidationResult,
        llm: dict,
        ac_texts: list[str],
        dod_texts: list[str],
    ) -> None:
        """Convertit la réponse LLM en AcceptanceCriterion + verdict."""
        status_map = {
            "PASS": CheckStatus.PASS,
            "OK": CheckStatus.PASS,
            "FAIL": CheckStatus.FAIL,
            "PARTIAL": CheckStatus.PARTIAL,
        }

        evaluations = {e.get("id", ""): e for e in llm.get("criteria_evaluations", [])}

        # AC
        for i, ac_text in enumerate(ac_texts, 1):
            cid = f"AC-{i}"
            llm_eval = evaluations.get(cid, {})
            criterion = AcceptanceCriterion(
                id=cid,
                description=ac_text,
                status=status_map.get(llm_eval.get("status", "FAIL"), CheckStatus.FAIL),
                evidence=llm_eval.get("evidence", llm_eval.get("reasoning", "")),
            )
            result.acceptance_criteria.append(criterion)

        # DoD
        for i, dod_text in enumerate(dod_texts, 1):
            cid = f"DoD-{i}"
            llm_eval = evaluations.get(cid, {})
            criterion = AcceptanceCriterion(
                id=cid,
                description=dod_text,
                status=status_map.get(llm_eval.get("status", "FAIL"), CheckStatus.FAIL),
                evidence=llm_eval.get("evidence", llm_eval.get("reasoning", "")),
            )
            result.definition_of_done.append(criterion)

        # Verdict
        all_criteria = result.acceptance_criteria + result.definition_of_done
        fail_count = sum(1 for c in all_criteria if c.status == CheckStatus.FAIL)
        pass_count = sum(1 for c in all_criteria if c.status in (CheckStatus.PASS, CheckStatus.OK))
        partial_count = sum(1 for c in all_criteria if c.status == CheckStatus.PARTIAL)

        verdict_map = {"PASS": Verdict.PASS, "FAIL": Verdict.FAIL, "BLOCKED": Verdict.BLOCKED}
        llm_verdict = verdict_map.get(llm.get("recommended_verdict", ""), None)

        if llm_verdict:
            result.recommended_verdict = llm_verdict
        elif fail_count > 0:
            result.recommended_verdict = Verdict.FAIL
        elif partial_count > 0:
            result.recommended_verdict = Verdict.FAIL
        else:
            result.recommended_verdict = Verdict.PASS

        if fail_count > 0:
            result.status = CheckStatus.FAIL
        elif partial_count > 0:
            result.status = CheckStatus.PARTIAL
        else:
            result.status = CheckStatus.OK

        result.summary = (
            f"🤖 Issue {result.jira_key} — {len(all_criteria)} critère(s) évalué(s) par IA : "
            f"{pass_count} PASS, {fail_count} FAIL, {partial_count} PARTIAL."
        )
        if llm.get("summary"):
            result.summary += f"\n{llm['summary']}"

    def _evaluate_static(
        self,
        result: JiraValidationResult,
        ac_texts: list[str],
        dod_texts: list[str],
        code: CodeAnalysisResult | None,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
    ) -> None:
        """Fallback statique : évaluation par mots-clés."""
        for i, ac_text in enumerate(ac_texts, 1):
            criterion = AcceptanceCriterion(
                id=f"AC-{i}",
                description=ac_text,
            )
            criterion.status, criterion.evidence = self._evaluate_criterion(
                ac_text, code, uml, figma
            )
            result.acceptance_criteria.append(criterion)

        for i, dod_text in enumerate(dod_texts, 1):
            criterion = AcceptanceCriterion(
                id=f"DoD-{i}",
                description=dod_text,
            )
            criterion.status, criterion.evidence = self._evaluate_criterion(
                dod_text, code, uml, figma
            )
            result.definition_of_done.append(criterion)

        # Verdict
        all_criteria = result.acceptance_criteria + result.definition_of_done
        fail_count = sum(1 for c in all_criteria if c.status == CheckStatus.FAIL)
        pass_count = sum(1 for c in all_criteria if c.status in (CheckStatus.PASS, CheckStatus.OK))
        partial_count = sum(1 for c in all_criteria if c.status == CheckStatus.PARTIAL)

        if fail_count > 0:
            result.status = CheckStatus.FAIL
            result.recommended_verdict = Verdict.FAIL
        elif partial_count > 0:
            result.status = CheckStatus.PARTIAL
            result.recommended_verdict = Verdict.FAIL
        else:
            result.status = CheckStatus.OK
            result.recommended_verdict = Verdict.PASS

        result.summary = (
            f"Issue {result.jira_key} — {len(all_criteria)} critère(s) évalué(s) : "
            f"{pass_count} PASS, {fail_count} FAIL, {partial_count} PARTIAL."
        )

    @staticmethod
    def _evaluate_criterion(
        criterion_text: str,
        code: CodeAnalysisResult | None,
        uml: UMLCheckResult | None,
        figma: FigmaCheckResult | None,
    ) -> tuple[CheckStatus, str]:
        """
        Fallback statique : évalue un critère via recherche de mots-clés.
        """
        if not code:
            return CheckStatus.BLOCKED, "Pas d'analyse de code disponible."

        criterion_lower = criterion_text.lower()
        evidence_parts: list[str] = []
        matched = False

        for ep in code.endpoints:
            if _keyword_overlap(criterion_lower, ep.lower()):
                evidence_parts.append(f"Endpoint trouvé : {ep}")
                matched = True

        for cls in code.classes_touched:
            if _keyword_overlap(criterion_lower, cls.lower()):
                evidence_parts.append(f"Classe touchée : {cls}")
                matched = True

        for feat in code.features_detected:
            if _keyword_overlap(criterion_lower, feat.lower()):
                evidence_parts.append(f"Fonctionnalité : {feat}")
                matched = True

        if any(kw in criterion_lower for kw in ("test", "couverture", "coverage")):
            if code.tests_added or code.tests_modified:
                evidence_parts.append(
                    f"Tests : {len(code.tests_added)} ajouté(s), "
                    f"{len(code.tests_modified)} modifié(s)"
                )
                matched = True

        if uml and any(kw in criterion_lower for kw in ("diagramme", "uml", "architecture")):
            if uml.status == CheckStatus.OK:
                evidence_parts.append("UML cohérent.")
                matched = True
            elif uml.mismatches:
                evidence_parts.append(f"UML : {len(uml.mismatches)} écart(s)")

        if figma and any(kw in criterion_lower for kw in ("ui", "interface", "design", "figma",
                                                            "écran", "composant", "maquette")):
            if figma.status == CheckStatus.OK:
                evidence_parts.append("Figma conforme.")
                matched = True
            elif figma.mappings:
                fail_maps = [m for m in figma.mappings if m.implementation_status == CheckStatus.FAIL]
                if fail_maps:
                    evidence_parts.append(f"Figma : {len(fail_maps)} écart(s)")

        if matched:
            return CheckStatus.PASS, " | ".join(evidence_parts)
        elif evidence_parts:
            return CheckStatus.PARTIAL, " | ".join(evidence_parts)
        else:
            return CheckStatus.FAIL, "Aucune preuve trouvée dans le code pour ce critère."


def _keyword_overlap(text_a: str, text_b: str) -> bool:
    """Vérifie s'il y a un chevauchement significatif de mots-clés."""
    words_a = {w for w in text_a.split() if len(w) >= 4}
    words_b = {w for w in text_b.split() if len(w) >= 4}
    if not words_a or not words_b:
        return False
    overlap = words_a & words_b
    return len(overlap) >= 1
