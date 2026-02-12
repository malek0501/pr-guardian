"""
Agent 1 — GitHub Code Analyst (LLM-powered).

Analyse le diff de la PR via Cohere LLM pour :
- Lister les fichiers modifiés et leur nature
- Détecter les fonctionnalités implémentées
- Identifier endpoints, classes, méthodes, migrations
- Évaluer la couverture de tests
- Repérer les points sensibles (sécurité, perf, DB)
- Analyser qualité, sécurité, bugs, architecture (via IA)

Phase 1 : extraction statique (regex, parsing)
Phase 2 : analyse LLM sémantique (Cohere)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import cohere

from pr_guardian.agents.base_agent import BaseAgent
from pr_guardian.config import get_settings
from pr_guardian.integrations.github_client import GitHubClient
from pr_guardian.models import CodeAnalysisResult, ModifiedFile, PRContext
from pr_guardian.parsers.diff_parser import DiffParser
from pr_guardian.utils.helpers import extract_language

logger = logging.getLogger("pr_guardian.agent.CodeAnalyst")

# ── Prompt système pour l'analyse de code ──

CODE_ANALYST_SYSTEM_PROMPT = """\
Tu es un expert en revue de code. Tu reçois le diff d'une Pull Request.

Ton rôle : analyser le code en profondeur et fournir une évaluation experte.

ANALYSE REQUISE :
1. **Qualité du code** : lisibilité, respect des conventions, DRY, SOLID
2. **Sécurité** : failles potentielles (injection, XSS, auth bypass, secrets exposés)
3. **Performance** : requêtes N+1, boucles coûteuses, mémoire, concurrence
4. **Architecture** : patterns utilisés, couplage, responsabilités
5. **Tests** : couverture suffisante, cas limites testés, tests fragiles
6. **Bugs potentiels** : race conditions, null pointers, edge cases, typos logiques

Tu dois répondre UNIQUEMENT en JSON valide avec cette structure :
{
  "quality_score": <int 0-100>,
  "security_issues": ["description de chaque problème de sécurité"],
  "performance_issues": ["description de chaque problème de performance"],
  "architecture_notes": ["observation sur l'architecture"],
  "bug_risks": ["description de chaque risque de bug"],
  "suggestions": ["suggestion d'amélioration concrète"],
  "summary": "résumé en 2-3 phrases de l'analyse"
}
"""


class CodeAnalystAgent(BaseAgent):
    """Agent 1 : analyse le code de la PR (statique + LLM)."""

    name = "CodeAnalyst"

    def __init__(self, github_client: GitHubClient | None = None):
        super().__init__()
        self._gh = github_client
        self._settings = get_settings()

    def _get_github(self) -> GitHubClient:
        if self._gh is None:
            self._gh = GitHubClient()
        return self._gh

    async def run(self, context: PRContext, **kwargs: Any) -> CodeAnalysisResult:
        self._log_start(context)

        gh = self._get_github()
        files = gh.get_modified_files(context.repo, context.pr_number)

        result = CodeAnalysisResult(
            files_modified=files,
            raw_diff_stats={
                "total_files": len(files),
                "total_additions": sum(f.additions for f in files),
                "total_deletions": sum(f.deletions for f in files),
            },
        )

        all_classes: list[str] = []
        all_methods: list[str] = []
        all_endpoints: list[str] = []
        features: list[str] = []
        tests_added: list[str] = []
        tests_modified: list[str] = []
        migrations: list[str] = []
        sensitive: list[str] = []
        all_patches: list[str] = []

        for f in files:
            lang = extract_language(f.filename)
            f.language = lang

            # Parser le diff
            if f.patch:
                diff_info = DiffParser.parse_patch(f.patch, f.filename)
                all_classes.extend(diff_info.classes_modified)
                all_methods.extend(diff_info.functions_modified)
                all_endpoints.extend(diff_info.endpoints_detected)
                all_patches.append(f"--- {f.filename} ---\n{f.patch}")

            # Catégoriser le fichier
            lower = f.filename.lower()

            # Tests
            if "test" in lower or "spec" in lower:
                if f.status == "added":
                    tests_added.append(f.filename)
                else:
                    tests_modified.append(f.filename)

            # Migrations
            if "migration" in lower or "alembic" in lower or "flyway" in lower:
                migrations.append(f.filename)

            # Points sensibles
            if any(kw in lower for kw in ("auth", "security", "password", "token", "secret",
                                           "payment", "billing", "crypto")):
                sensitive.append(f"⚠️ Fichier sensible : {f.filename}")

            # Détection de features par nom de fichier / chemin
            if f.status == "added" and lang in ("python", "java", "typescript", "javascript"):
                features.append(f"Nouveau fichier : {f.filename}")

        result.classes_touched = list(set(all_classes))
        result.methods_touched = list(set(all_methods))
        result.endpoints = list(set(all_endpoints))
        result.features_detected = features
        result.tests_added = tests_added
        result.tests_modified = tests_modified
        result.migrations_detected = migrations
        result.sensitive_points = sensitive

        # ── Phase 2 : Analyse LLM sémantique ──
        llm_analysis = None
        if self._settings.llm_configured and all_patches:
            llm_analysis = self._llm_analyze(all_patches, context)

        # Résumé enrichi
        result.summary = self._build_summary(result, llm_analysis)
        result.test_coverage_info = self._assess_test_coverage(result)

        self._log_done(context)
        return result

    def _llm_analyze(self, patches: list[str], context: PRContext) -> dict | None:
        """Appelle Cohere pour une analyse sémantique approfondie du diff."""
        try:
            combined_diff = "\n\n".join(patches)
            if len(combined_diff) > 8000:
                combined_diff = combined_diff[:8000] + "\n\n[... diff tronqué ...]"

            user_message = (
                f"Analyse cette Pull Request :\n"
                f"Repo: {context.repo}, PR #{context.pr_number}\n"
                f"Titre: {context.pr_title}\n\n"
                f"## DIFF\n```\n{combined_diff}\n```"
            )

            client = cohere.ClientV2(api_key=self._settings.cohere_api_key)
            response = client.chat(
                model=self._settings.cohere_model,
                messages=[
                    {"role": "system", "content": CODE_ANALYST_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            raw = response.message.content[0].text if response.message.content else "{}"
            analysis = json.loads(raw)
            logger.info("[CodeAnalyst] LLM analysis OK — quality score: %s/100",
                        analysis.get("quality_score", "?"))
            return analysis

        except Exception as exc:
            logger.warning("[CodeAnalyst] LLM analysis failed: %s", exc)
            return None

    @staticmethod
    def _build_summary(r: CodeAnalysisResult, llm: dict | None = None) -> str:
        lines = [
            f"📊 **{r.raw_diff_stats.get('total_files', 0)}** fichiers modifiés "
            f"(+{r.raw_diff_stats.get('total_additions', 0)} / "
            f"-{r.raw_diff_stats.get('total_deletions', 0)})",
        ]
        if r.endpoints:
            lines.append(f"🔗 Endpoints : {', '.join(r.endpoints)}")
        if r.classes_touched:
            lines.append(f"🏗️ Classes : {', '.join(r.classes_touched)}")
        if r.migrations_detected:
            lines.append(f"🗃️ Migrations : {', '.join(r.migrations_detected)}")
        if r.sensitive_points:
            lines.append(f"🔒 Points sensibles : {len(r.sensitive_points)}")

        # ── Enrichissement LLM ──
        if llm:
            lines.append(f"\n🤖 **Analyse IA (score qualité : {llm.get('quality_score', '?')}/100)**")
            if llm.get("summary"):
                lines.append(f"   {llm['summary']}")
            if llm.get("security_issues"):
                lines.append(f"   🔴 Sécurité : {len(llm['security_issues'])} problème(s)")
                for issue in llm["security_issues"][:3]:
                    lines.append(f"      • {issue}")
            if llm.get("bug_risks"):
                lines.append(f"   🐛 Risques de bugs : {len(llm['bug_risks'])}")
                for bug in llm["bug_risks"][:3]:
                    lines.append(f"      • {bug}")
            if llm.get("performance_issues"):
                lines.append(f"   ⚡ Performance : {len(llm['performance_issues'])} problème(s)")
            if llm.get("suggestions"):
                lines.append("   💡 Suggestions :")
                for sug in llm["suggestions"][:3]:
                    lines.append(f"      • {sug}")

        return "\n".join(lines)

    @staticmethod
    def _assess_test_coverage(r: CodeAnalysisResult) -> str:
        src_files = [f for f in r.files_modified
                     if "test" not in f.filename.lower() and "spec" not in f.filename.lower()]
        test_files = r.tests_added + r.tests_modified
        if not src_files:
            return "Aucun fichier source modifié."
        if not test_files:
            return "⚠️ Aucun test ajouté/modifié pour cette PR."
        ratio = len(test_files) / len(src_files) * 100
        return f"Tests : {len(test_files)} fichier(s) test pour {len(src_files)} source(s) ({ratio:.0f}%)"
