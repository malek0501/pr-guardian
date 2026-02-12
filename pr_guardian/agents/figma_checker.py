"""
Agent 3 — Figma Requirements & UI Checker (LLM-powered).

Identifie le lien Figma, récupère les pages/frames pertinents,
extrait les exigences UI/UX, et utilise Cohere LLM pour vérifier
sémantiquement l'alignement avec le code de la PR.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import cohere

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.integrations.figma_client import FigmaClient
from pr_guardian.integrations.github_client import GitHubClient
from pr_guardian.models import (
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    FigmaMapping,
    FigmaRequirement,
    PRContext,
)

logger = logging.getLogger("pr_guardian.agent.FigmaChecker")

# ── Prompt système pour l'analyse Figma ──

FIGMA_CHECKER_SYSTEM_PROMPT = """\
Tu es un expert UI/UX qui vérifie la conformité entre des maquettes Figma et le code.

Tu reçois :
1. Les frames/composants Figma avec leurs noms, textes et composants enfants
2. Les classes, méthodes, endpoints et fichiers modifiés dans la PR

Ton rôle : déterminer si le code implémente correctement les exigences du design Figma.

VÉRIFICATIONS :
1. **Mapping composants** : Chaque frame Figma a-t-il un composant/page correspondant dans le code ?
2. **Textes UI** : Les textes, labels et messages de l'UI Figma sont-ils présents dans le code ?
3. **Interactions** : Les boutons et actions dans Figma ont-ils des handlers dans le code ?
4. **Complétude** : Y a-t-il des écrans Figma non implémentés ou du code sans maquette ?
5. **Cohérence** : La structure de navigation correspond-elle au design ?

Pour chaque exigence Figma, tu dois dire si elle est implémentée ou non.

Réponds UNIQUEMENT en JSON valide :
{
  "conformity_score": <int 0-100>,
  "mappings": [
    {
      "frame_name": "nom du frame Figma",
      "status": "OK|FAIL|PARTIAL",
      "evidence": "explication de la correspondance trouvée ou non",
      "gap": "description de l'écart si FAIL"
    }
  ],
  "missing_in_code": ["éléments Figma non trouvés dans le code"],
  "missing_in_figma": ["éléments du code sans maquette Figma"],
  "summary": "résumé en 2-3 phrases"
}
"""


class FigmaCheckerAgent(BaseAgent):
    """Agent 3 : vérifie la conformité Figma ↔ code (statique + LLM)."""

    name = "FigmaChecker"

    def __init__(
        self,
        github_client: GitHubClient | None = None,
        figma_client: FigmaClient | None = None,
    ):
        super().__init__()
        self._gh = github_client
        self._figma = figma_client
        self._settings = get_settings()

    def _get_github(self) -> GitHubClient:
        if self._gh is None:
            self._gh = GitHubClient()
        return self._gh

    def _get_figma(self) -> FigmaClient:
        if self._figma is None:
            self._figma = FigmaClient()
        return self._figma

    async def run(
        self,
        context: PRContext,
        code_analysis: CodeAnalysisResult | None = None,
        **kwargs: Any,
    ) -> FigmaCheckResult:
        self._log_start(context)
        result = FigmaCheckResult()

        # ── Trouver le lien Figma ───────────
        figma_link = context.figma_link
        if not figma_link:
            self._log_blocked("Aucun lien Figma fourni dans le contexte.")
            result.status = CheckStatus.BLOCKED
            result.summary = (
                "Aucun lien Figma trouvé (ni dans le repo, ni dans Jira, ni dans la PR). "
                "Impossible de vérifier la conformité UI."
            )
            return result

        result.figma_link = figma_link

        # ── Parser l'URL Figma ──────────────
        try:
            figma = self._get_figma()
            parsed = FigmaClient.parse_figma_url(figma_link)
            file_key = parsed["file_key"]
            node_id = parsed.get("node_id")
        except Exception as exc:
            self._log_blocked(f"Impossible de parser l'URL Figma : {exc}")
            result.status = CheckStatus.BLOCKED
            result.summary = f"URL Figma invalide ou inaccessible : {exc}"
            return result

        # ── Récupérer les exigences Figma ───
        try:
            requirements = figma.extract_requirements(file_key, node_id)
            result.requirements = requirements

            # Pages analysées
            metadata = figma.get_file_metadata(file_key)
            result.pages_analyzed = [p["name"] for p in metadata.get("pages", [])]

        except Exception as exc:
            self._log_blocked(f"Erreur API Figma : {exc}")
            result.status = CheckStatus.BLOCKED
            result.summary = f"Erreur lors de l'accès à Figma : {exc}"
            return result

        if not requirements:
            result.status = CheckStatus.PARTIAL
            result.summary = "Fichier Figma accessible mais aucun frame/composant pertinent trouvé."
            return result

        # ── Mapper exigences → implémentation ──
        if code_analysis:
            # Tenter l'analyse LLM
            llm_result = None
            if self._settings.llm_configured:
                llm_result = self._llm_map_requirements(requirements, code_analysis, context)

            if llm_result:
                result.mappings = self._apply_llm_mappings(requirements, llm_result)
            else:
                # Fallback statique
                result.mappings = self._map_requirements(requirements, code_analysis)
        else:
            result.mappings = [
                FigmaMapping(
                    requirement=req,
                    implementation_status=CheckStatus.NOT_APPLICABLE,
                    evidence="Pas d'analyse de code disponible pour comparaison.",
                )
                for req in requirements
            ]

        # ── Verdict ─────────────────────────
        if result.mappings:
            fail_count = sum(
                1 for m in result.mappings if m.implementation_status == CheckStatus.FAIL
            )
            pass_count = sum(
                1 for m in result.mappings if m.implementation_status in (CheckStatus.OK, CheckStatus.PASS)
            )
            total = len(result.mappings)

            if fail_count > 0:
                result.status = CheckStatus.MISMATCH
            elif pass_count == total:
                result.status = CheckStatus.OK
            else:
                result.status = CheckStatus.PARTIAL

            result.summary = (
                f"{total} exigence(s) Figma identifiée(s) : "
                f"{pass_count} conforme(s), {fail_count} écart(s), "
                f"{total - pass_count - fail_count} indéterminé(s)."
            )

            # Enrichir avec le résumé LLM
            if llm_result and llm_result.get("summary"):
                result.summary += f"\n🤖 IA : {llm_result['summary']}"
        else:
            result.status = CheckStatus.PARTIAL
            result.summary = "Aucune exigence Figma à mapper."

        self._log_done(context)
        return result

    def _llm_map_requirements(
        self,
        requirements: list[FigmaRequirement],
        code: CodeAnalysisResult,
        context: PRContext,
    ) -> dict | None:
        """Appelle Cohere pour mapper sémantiquement les exigences Figma au code."""
        try:
            # Formater les exigences Figma
            figma_info = []
            for req in requirements:
                figma_info.append(
                    f"- Frame: '{req.frame_name}' (page: {req.page_name})\n"
                    f"  Composants: {', '.join(req.components) or 'aucun'}\n"
                    f"  Textes: {', '.join(req.texts) or 'aucun'}\n"
                    f"  États: {', '.join(req.states) or 'aucun'}"
                )

            # Formater le code
            code_info = (
                f"Classes : {', '.join(code.classes_touched) or 'aucune'}\n"
                f"Méthodes : {', '.join(code.methods_touched) or 'aucune'}\n"
                f"Endpoints : {', '.join(code.endpoints) or 'aucun'}\n"
                f"Fichiers : {', '.join(f.filename for f in code.files_modified[:20])}\n"
                f"Features : {', '.join(code.features_detected) or 'aucune'}"
            )

            user_message = (
                f"PR: {context.repo} #{context.pr_number} — {context.pr_title}\n\n"
                f"## EXIGENCES FIGMA\n" + "\n".join(figma_info) + "\n\n"
                f"## CODE DE LA PR\n{code_info}"
            )

            client = cohere.ClientV2(api_key=self._settings.cohere_api_key)
            response = client.chat(
                model=self._settings.cohere_model,
                messages=[
                    {"role": "system", "content": FIGMA_CHECKER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.message.content[0].text if response.message.content else "{}"
            analysis = json.loads(raw)
            logger.info("[FigmaChecker] LLM analysis OK — conformity score: %s/100",
                        analysis.get("conformity_score", "?"))
            return analysis

        except Exception as exc:
            logger.warning("[FigmaChecker] LLM analysis failed: %s", exc)
            return None

    @staticmethod
    def _apply_llm_mappings(
        requirements: list[FigmaRequirement],
        llm: dict,
    ) -> list[FigmaMapping]:
        """Convertit la réponse LLM en liste de FigmaMapping."""
        status_map = {
            "OK": CheckStatus.OK,
            "PASS": CheckStatus.OK,
            "FAIL": CheckStatus.FAIL,
            "PARTIAL": CheckStatus.PARTIAL,
        }

        llm_mappings = {m.get("frame_name", "").lower(): m for m in llm.get("mappings", [])}
        mappings: list[FigmaMapping] = []

        for req in requirements:
            llm_match = llm_mappings.get(req.frame_name.lower())
            if llm_match:
                mappings.append(FigmaMapping(
                    requirement=req,
                    implementation_status=status_map.get(llm_match.get("status", "FAIL"), CheckStatus.FAIL),
                    evidence=llm_match.get("evidence", ""),
                    gap=llm_match.get("gap", ""),
                ))
            else:
                mappings.append(FigmaMapping(
                    requirement=req,
                    implementation_status=CheckStatus.PARTIAL,
                    evidence="Frame non évalué par l'IA.",
                ))

        return mappings

    @staticmethod
    def _map_requirements(
        requirements: list[FigmaRequirement],
        code: CodeAnalysisResult,
    ) -> list[FigmaMapping]:
        """
        Fallback statique : mapper chaque exigence Figma via heuristique de noms.
        """
        code_tokens = set()
        for cls in code.classes_touched:
            code_tokens.add(cls.lower())
        for method in code.methods_touched:
            code_tokens.add(method.lower())
        for ep in code.endpoints:
            code_tokens.add(ep.lower())
        for f in code.files_modified:
            name = f.filename.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
            code_tokens.add(name)

        mappings: list[FigmaMapping] = []

        for req in requirements:
            matches: list[str] = []
            search_terms = [req.frame_name.lower()] + [c.lower() for c in req.components]

            for term in search_terms:
                normalized = term.replace("-", "").replace("_", "").replace(" ", "")
                for token in code_tokens:
                    token_norm = token.replace("-", "").replace("_", "").replace(" ", "")
                    if (
                        normalized in token_norm
                        or token_norm in normalized
                        or _similarity(normalized, token_norm) > 0.6
                    ):
                        matches.append(token)

            if matches:
                mappings.append(FigmaMapping(
                    requirement=req,
                    implementation_status=CheckStatus.OK,
                    evidence=f"Correspondance(s) trouvée(s) dans le code : {', '.join(set(matches))}",
                ))
            else:
                mappings.append(FigmaMapping(
                    requirement=req,
                    implementation_status=CheckStatus.FAIL,
                    gap=(
                        f"Frame '{req.frame_name}' / composants {req.components} "
                        "non retrouvés dans le code de la PR."
                    ),
                ))

        return mappings


def _similarity(a: str, b: str) -> float:
    """Calcule une similarité simple (Jaccard sur les trigrammes)."""
    if not a or not b:
        return 0.0
    trigrams_a = {a[i:i+3] for i in range(len(a) - 2)}
    trigrams_b = {b[i:i+3] for i in range(len(b) - 2)}
    if not trigrams_a or not trigrams_b:
        return 0.0
    intersection = trigrams_a & trigrams_b
    union = trigrams_a | trigrams_b
    return len(intersection) / len(union)
