"""
Agent 2 — PlantUML Consistency Checker (LLM-powered).

Localise les fichiers PlantUML pertinents, les parse, et utilise Cohere LLM
pour vérifier la cohérence sémantique avec l'implémentation dans la PR :
- Classes / interfaces mentionnées dans l'UML vs code
- Relations (héritage, composition…) vs code
- Séquences attendues vs endpoints/flows
- Patterns de conception, cohérence architecturale
"""

from __future__ import annotations

import json
import logging
from typing import Any

import cohere

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.integrations.github_client import GitHubClient
from pr_guardian.models import (
    CheckStatus,
    CodeAnalysisResult,
    PRContext,
    Severity,
    UMLCheckResult,
    UMLMismatch,
)
from pr_guardian.parsers.plantuml_parser import PlantUMLParser

logger = logging.getLogger("pr_guardian.agent.UMLChecker")

# ── Prompt système pour l'analyse UML ──

UML_CHECKER_SYSTEM_PROMPT = """\
Tu es un architecte logiciel expert. Tu reçois :
1. Le contenu de diagrammes PlantUML (classes, séquences, etc.)
2. La liste des classes, méthodes et endpoints détectés dans le code d'une PR

Ton rôle : analyser la cohérence sémantique entre les diagrammes UML et le code.

VÉRIFICATIONS :
1. **Classes** : Les classes du code sont-elles représentées dans les diagrammes ?
2. **Relations** : Les relations du code (héritage, composition, dépendance) correspondent-elles à l'UML ?
3. **Méthodes** : Les méthodes importantes sont-elles documentées dans l'UML ?
4. **Séquences** : Les endpoints/flows ont-ils des diagrammes de séquence ?
5. **Patterns** : Les design patterns utilisés sont-ils correctement modélisés ?
6. **Complétude** : L'UML est-il à jour par rapport aux changements de la PR ?

Tu dois répondre UNIQUEMENT en JSON valide :
{
  "consistency_score": <int 0-100>,
  "mismatches": [
    {
      "element": "nom de l'élément",
      "issue": "description du problème",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
      "suggestion": "suggestion de correction"
    }
  ],
  "positive_points": ["ce qui est bien modélisé"],
  "summary": "résumé en 2-3 phrases"
}
"""


class UMLCheckerAgent(BaseAgent):
    """Agent 2 : vérifie la cohérence UML ↔ code (statique + LLM)."""

    name = "UMLChecker"

    def __init__(self, github_client: GitHubClient | None = None):
        super().__init__()
        self._gh = github_client
        self._settings = get_settings()

    def _get_github(self) -> GitHubClient:
        if self._gh is None:
            self._gh = GitHubClient()
        return self._gh

    async def run(
        self,
        context: PRContext,
        code_analysis: CodeAnalysisResult | None = None,
        **kwargs: Any,
    ) -> UMLCheckResult:
        self._log_start(context)
        result = UMLCheckResult()

        gh = self._get_github()

        # ── Trouver les fichiers UML ────────
        uml_paths = context.uml_files
        if not uml_paths:
            uml_paths = gh.find_uml_files(context.repo, context.branch or "main")

        if not uml_paths:
            self._log_blocked("Aucun fichier PlantUML trouvé dans le repo.")
            result.status = CheckStatus.BLOCKED
            result.summary = "Aucun fichier PlantUML trouvé dans le repository."
            return result

        # ── Parser chaque UML ───────────────
        uml_contents: list[str] = []
        for path in uml_paths:
            try:
                content = gh.get_file_content(context.repo, path, context.branch or "main")
                diagram = PlantUMLParser.parse(content, filepath=path)
                result.diagrams_found.append(diagram)
                uml_contents.append(f"--- {path} ---\n{content}")
            except Exception as exc:
                self.logger.warning(f"Impossible de parser {path}: {exc}")

        if not result.diagrams_found:
            result.status = CheckStatus.BLOCKED
            result.summary = "Fichiers UML trouvés mais impossible de les parser."
            return result

        # ── Vérifier la cohérence avec le code ──
        if code_analysis:
            # Tenter l'analyse LLM
            llm_result = None
            if self._settings.llm_configured and uml_contents:
                llm_result = self._llm_check_consistency(uml_contents, code_analysis, context)

            if llm_result:
                self._apply_llm_result(result, llm_result)
            else:
                # Fallback statique
                self._check_consistency_static(result, code_analysis)
        else:
            result.summary = (
                f"{len(result.diagrams_found)} diagramme(s) parsé(s), "
                "mais pas de résultat d'analyse de code pour comparaison."
            )
            result.status = CheckStatus.PARTIAL

        self._log_done(context)
        return result

    def _llm_check_consistency(
        self,
        uml_contents: list[str],
        code: CodeAnalysisResult,
        context: PRContext,
    ) -> dict | None:
        """Appelle Cohere pour analyser sémantiquement la cohérence UML ↔ code."""
        try:
            uml_text = "\n\n".join(uml_contents)
            if len(uml_text) > 6000:
                uml_text = uml_text[:6000] + "\n\n[... tronqué ...]"

            code_info = (
                f"Classes modifiées : {', '.join(code.classes_touched) or 'aucune'}\n"
                f"Méthodes modifiées : {', '.join(code.methods_touched) or 'aucune'}\n"
                f"Endpoints : {', '.join(code.endpoints) or 'aucun'}\n"
                f"Fichiers : {', '.join(f.filename for f in code.files_modified[:20])}\n"
                f"Features : {', '.join(code.features_detected) or 'aucune'}"
            )

            user_message = (
                f"PR: {context.repo} #{context.pr_number} — {context.pr_title}\n\n"
                f"## DIAGRAMMES UML\n{uml_text}\n\n"
                f"## CODE DE LA PR\n{code_info}"
            )

            client = cohere.ClientV2(api_key=self._settings.cohere_api_key)
            response = client.chat(
                model=self._settings.cohere_model,
                messages=[
                    {"role": "system", "content": UML_CHECKER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.message.content[0].text if response.message.content else "{}"
            analysis = json.loads(raw)
            logger.info("[UMLChecker] LLM analysis OK — consistency score: %s/100",
                        analysis.get("consistency_score", "?"))
            return analysis

        except Exception as exc:
            logger.warning("[UMLChecker] LLM analysis failed: %s", exc)
            return None

    def _apply_llm_result(self, result: UMLCheckResult, llm: dict) -> None:
        """Convertit la réponse LLM en UMLMismatch + verdict."""
        severity_map = {
            "CRITICAL": Severity.CRITICAL,
            "HIGH": Severity.HIGH,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
            "INFO": Severity.INFO,
        }

        for m in llm.get("mismatches", []):
            result.mismatches.append(UMLMismatch(
                diagram_file="(analyse IA)",
                element=m.get("element", "inconnu"),
                issue=m.get("issue", ""),
                severity=severity_map.get(m.get("severity", "MEDIUM"), Severity.MEDIUM),
                suggestion=m.get("suggestion", ""),
            ))

        critical = [m for m in result.mismatches if m.severity in (Severity.CRITICAL, Severity.HIGH)]

        if critical:
            result.status = CheckStatus.MISMATCH
        elif result.mismatches:
            result.status = CheckStatus.PARTIAL
        else:
            result.status = CheckStatus.OK

        score = llm.get("consistency_score", "?")
        positive = llm.get("positive_points", [])
        summary_parts = [
            f"🤖 Analyse IA — Score de cohérence : {score}/100.",
            f"{len(result.diagrams_found)} diagramme(s) analysé(s), "
            f"{len(result.mismatches)} écart(s) détecté(s) "
            f"({len(critical)} critique(s)/élevé(s)).",
        ]
        if llm.get("summary"):
            summary_parts.append(llm["summary"])
        if positive:
            summary_parts.append(f"✅ Points positifs : {', '.join(positive[:3])}")

        result.summary = "\n".join(summary_parts)

    def _check_consistency_static(
        self, result: UMLCheckResult, code: CodeAnalysisResult
    ) -> None:
        """Fallback statique : compare les entités/relations UML avec les classes/méthodes du code."""
        code_classes = set(c.lower() for c in code.classes_touched)
        code_endpoints = set(e.lower() for e in code.endpoints)

        uml_entity_names: set[str] = set()

        for diagram in result.diagrams_found:
            for entity in diagram.entities:
                uml_entity_names.add(entity.name.lower())

        # Classes dans le code mais absentes de l'UML
        for cls in code_classes:
            if cls not in uml_entity_names:
                result.mismatches.append(UMLMismatch(
                    diagram_file="(tous)",
                    element=cls,
                    issue=f"Classe '{cls}' modifiée dans le code mais absente des diagrammes UML.",
                    severity=Severity.MEDIUM,
                    suggestion=f"Ajouter la classe '{cls}' dans le diagramme de classes.",
                ))

        # Endpoints dans le code vs séquences UML
        if code_endpoints:
            has_sequence = any(d.diagram_type == "sequence" for d in result.diagrams_found)
            if not has_sequence:
                result.mismatches.append(UMLMismatch(
                    diagram_file="(aucun)",
                    element="sequence diagram",
                    issue=(
                        f"La PR contient {len(code_endpoints)} endpoint(s) "
                        "mais aucun diagramme de séquence n'est présent."
                    ),
                    severity=Severity.LOW,
                    suggestion="Envisager l'ajout d'un diagramme de séquence pour les flows API.",
                ))

        # Verdict
        critical = [m for m in result.mismatches if m.severity in (Severity.CRITICAL, Severity.HIGH)]
        if critical:
            result.status = CheckStatus.MISMATCH
        elif result.mismatches:
            result.status = CheckStatus.PARTIAL
        else:
            result.status = CheckStatus.OK

        result.summary = (
            f"{len(result.diagrams_found)} diagramme(s) analysé(s), "
            f"{len(result.mismatches)} écart(s) détecté(s) "
            f"({len(critical)} critique(s)/élevé(s))."
        )
