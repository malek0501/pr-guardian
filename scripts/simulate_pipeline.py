#!/usr/bin/env python3
"""
🧪 Simulation locale du pipeline PR-Guardian.

Simule le workflow complet SANS appeler les APIs externes :
  - Pas besoin de clés GitHub / Jira / Figma / Cohere
  - Données fictives réalistes
  - Tous les agents exécutés avec des mocks
  - Affichage du rapport final comme en production

Usage :
  python scripts/simulate_pipeline.py
  python scripts/simulate_pipeline.py --scenario pass
  python scripts/simulate_pipeline.py --scenario fail
  python scripts/simulate_pipeline.py --scenario blocked
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Ajouter le projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pr_guardian.models import (
    AcceptanceCriterion,
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    FigmaMapping,
    FigmaRequirement,
    FinalReport,
    JiraValidationResult,
    JudgeVerdict,
    ModifiedFile,
    MustFixItem,
    PRContext,
    Severity,
    UMLCheckResult,
    UMLDiagram,
    UMLEntity,
    UMLMismatch,
    UMLRelation,
    ValidationRow,
    Verdict,
)
from pr_guardian.agents.judge import JudgeAgent

console = Console()


# ════════════════════════════════════════════
#  DONNÉES FICTIVES (Scénarios)
# ════════════════════════════════════════════

def make_pr_context() -> PRContext:
    """Crée un contexte PR réaliste fictif."""
    return PRContext(
        repo="Team7/e-commerce-app",
        pr_number=42,
        branch="feature/PROJ-42-login-page",
        pr_title="[PROJ-42] Implement login page with OAuth2",
        pr_description=(
            "## Description\n"
            "Implémentation de la page de connexion avec support OAuth2 (Google, GitHub).\n\n"
            "## Jira\n"
            "Ticket: PROJ-42\n\n"
            "## Figma\n"
            "Maquette: https://www.figma.com/file/ABC123/LoginPage\n\n"
            "## Changes\n"
            "- LoginController avec endpoints /login et /oauth/callback\n"
            "- LoginForm component React\n"
            "- Tests unitaires et d'intégration\n"
            "- Mise à jour du diagramme UML\n"
        ),
        pr_author="malek",
        pr_author_email="malek@team7.dev",
        jira_key="PROJ-42",
        figma_link="https://www.figma.com/file/ABC123/LoginPage",
        uml_files=["docs/diagrams/auth.puml"],
    )


def make_code_analysis_pass() -> CodeAnalysisResult:
    """Agent 1 — Résultat PASS."""
    return CodeAnalysisResult(
        summary="PR bien structurée : 6 fichiers modifiés, 2 endpoints REST, tests couverts.",
        files_modified=[
            ModifiedFile(filename="src/controllers/LoginController.java", status="added", additions=120, deletions=0, language="java"),
            ModifiedFile(filename="src/services/AuthService.java", status="added", additions=85, deletions=0, language="java"),
            ModifiedFile(filename="src/models/User.java", status="modified", additions=15, deletions=3, language="java"),
            ModifiedFile(filename="frontend/src/components/LoginForm.tsx", status="added", additions=95, deletions=0, language="typescript"),
            ModifiedFile(filename="tests/LoginControllerTest.java", status="added", additions=65, deletions=0, language="java"),
            ModifiedFile(filename="tests/AuthServiceTest.java", status="added", additions=40, deletions=0, language="java"),
        ],
        features_detected=["OAuth2 login", "JWT token generation", "Session management"],
        endpoints=["POST /api/login", "GET /api/oauth/callback"],
        classes_touched=["LoginController", "AuthService", "User", "LoginForm"],
        methods_touched=["login()", "handleOAuthCallback()", "generateToken()", "validateCredentials()"],
        tests_added=["tests/LoginControllerTest.java", "tests/AuthServiceTest.java"],
        tests_modified=[],
        test_coverage_info="2 fichiers de tests ajoutés couvrant les 2 endpoints et le service d'auth.",
        sensitive_points=["Gestion des tokens JWT", "Stockage des credentials OAuth"],
        raw_diff_stats={"total_files": 6, "additions": 420, "deletions": 3},
    )


def make_code_analysis_fail() -> CodeAnalysisResult:
    """Agent 1 — Résultat sans tests."""
    return CodeAnalysisResult(
        summary="PR avec 4 fichiers modifiés, 2 endpoints REST, AUCUN test ajouté.",
        files_modified=[
            ModifiedFile(filename="src/controllers/LoginController.java", status="added", additions=120, deletions=0, language="java"),
            ModifiedFile(filename="src/services/AuthService.java", status="added", additions=85, deletions=0, language="java"),
            ModifiedFile(filename="src/models/User.java", status="modified", additions=15, deletions=3, language="java"),
            ModifiedFile(filename="frontend/src/components/LoginForm.tsx", status="added", additions=95, deletions=0, language="typescript"),
        ],
        features_detected=["OAuth2 login", "JWT token generation"],
        endpoints=["POST /api/login", "GET /api/oauth/callback"],
        classes_touched=["LoginController", "AuthService", "User", "LoginForm"],
        methods_touched=["login()", "handleOAuthCallback()"],
        tests_added=[],
        tests_modified=[],
        test_coverage_info="Aucun test détecté.",
        sensitive_points=["Gestion des tokens JWT", "Stockage des credentials OAuth — NON SÉCURISÉ"],
        raw_diff_stats={"total_files": 4, "additions": 315, "deletions": 3},
    )


def make_uml_check_pass() -> UMLCheckResult:
    """Agent 2 — UML cohérent."""
    return UMLCheckResult(
        diagrams_found=[
            UMLDiagram(
                filepath="docs/diagrams/auth.puml",
                diagram_type="class",
                entities=[
                    UMLEntity(name="LoginController", entity_type="class", methods=["login()", "handleOAuthCallback()"]),
                    UMLEntity(name="AuthService", entity_type="class", methods=["generateToken()", "validateCredentials()"]),
                    UMLEntity(name="User", entity_type="class", attributes=["email", "passwordHash", "oauthProvider"]),
                ],
                relations=[
                    UMLRelation(source="LoginController", target="AuthService", relation_type="dependency"),
                    UMLRelation(source="AuthService", target="User", relation_type="association"),
                ],
            )
        ],
        mismatches=[],
        status=CheckStatus.OK,
        summary="Diagramme UML cohérent avec le code : toutes les classes et méthodes sont présentes.",
    )


def make_uml_check_fail() -> UMLCheckResult:
    """Agent 2 — UML avec mismatch."""
    return UMLCheckResult(
        diagrams_found=[
            UMLDiagram(
                filepath="docs/diagrams/auth.puml",
                diagram_type="class",
                entities=[
                    UMLEntity(name="LoginController", entity_type="class", methods=["login()"]),
                    UMLEntity(name="UserService", entity_type="class", methods=["getUser()"]),
                ],
                relations=[],
            )
        ],
        mismatches=[
            UMLMismatch(
                diagram_file="docs/diagrams/auth.puml",
                element="AuthService",
                issue="Classe AuthService présente dans le code mais absente du diagramme UML.",
                severity=Severity.HIGH,
                suggestion="Ajouter AuthService au diagramme de classes.",
            ),
            UMLMismatch(
                diagram_file="docs/diagrams/auth.puml",
                element="handleOAuthCallback",
                issue="Méthode handleOAuthCallback() ajoutée dans LoginController mais absente du diagramme.",
                severity=Severity.MEDIUM,
                suggestion="Mettre à jour le diagramme avec la nouvelle méthode.",
            ),
        ],
        status=CheckStatus.MISMATCH,
        summary="2 écarts détectés entre le diagramme UML et le code.",
    )


def make_figma_check_pass() -> FigmaCheckResult:
    """Agent 3 — Figma conforme."""
    return FigmaCheckResult(
        figma_link="https://www.figma.com/file/ABC123/LoginPage",
        pages_analyzed=["Login", "OAuth Flow"],
        requirements=[
            FigmaRequirement(frame_id="F1", frame_name="LoginForm", page_name="Login",
                             description="Formulaire de connexion", components=["EmailInput", "PasswordInput", "SubmitButton"],
                             texts=["Se connecter", "Mot de passe oublié ?"], states=["default", "error", "loading"]),
            FigmaRequirement(frame_id="F2", frame_name="OAuthButtons", page_name="Login",
                             description="Boutons OAuth", components=["GoogleButton", "GitHubButton"],
                             texts=["Continuer avec Google", "Continuer avec GitHub"]),
        ],
        mappings=[
            FigmaMapping(
                requirement=FigmaRequirement(frame_id="F1", frame_name="LoginForm", page_name="Login",
                                              description="Formulaire de connexion", components=["EmailInput", "PasswordInput", "SubmitButton"]),
                implementation_status=CheckStatus.OK,
                evidence="LoginForm.tsx contient les composants EmailInput, PasswordInput, SubmitButton.",
            ),
            FigmaMapping(
                requirement=FigmaRequirement(frame_id="F2", frame_name="OAuthButtons", page_name="Login",
                                              description="Boutons OAuth", components=["GoogleButton", "GitHubButton"]),
                implementation_status=CheckStatus.OK,
                evidence="LoginForm.tsx contient GoogleOAuthButton et GitHubOAuthButton.",
            ),
        ],
        status=CheckStatus.OK,
        summary="Tous les composants Figma sont implémentés dans le code.",
    )


def make_figma_check_fail() -> FigmaCheckResult:
    """Agent 3 — Figma avec écarts."""
    return FigmaCheckResult(
        figma_link="https://www.figma.com/file/ABC123/LoginPage",
        pages_analyzed=["Login"],
        requirements=[
            FigmaRequirement(frame_id="F1", frame_name="LoginForm", page_name="Login",
                             description="Formulaire de connexion", components=["EmailInput", "PasswordInput", "SubmitButton"]),
            FigmaRequirement(frame_id="F2", frame_name="OAuthButtons", page_name="Login",
                             description="Boutons OAuth", components=["GoogleButton", "GitHubButton"]),
        ],
        mappings=[
            FigmaMapping(
                requirement=FigmaRequirement(frame_id="F1", frame_name="LoginForm", page_name="Login",
                                              description="Formulaire", components=["EmailInput", "PasswordInput", "SubmitButton"]),
                implementation_status=CheckStatus.OK,
                evidence="LoginForm.tsx contient les composants requis.",
            ),
            FigmaMapping(
                requirement=FigmaRequirement(frame_id="F2", frame_name="OAuthButtons", page_name="Login",
                                              description="Boutons OAuth", components=["GoogleButton", "GitHubButton"]),
                implementation_status=CheckStatus.FAIL,
                gap="Composant GitHubButton non trouvé dans le code. Seul GoogleButton est implémenté.",
            ),
        ],
        status=CheckStatus.MISMATCH,
        summary="1 composant Figma manquant : GitHubButton.",
    )


def make_jira_validation_pass() -> JiraValidationResult:
    """Agent 4 — Jira OK."""
    return JiraValidationResult(
        jira_key="PROJ-42",
        jira_summary="Implémenter la page de connexion avec OAuth2",
        jira_description="En tant qu'utilisateur, je veux pouvoir me connecter via email/mot de passe ou OAuth2.",
        jira_status="In Review",
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-1", description="L'utilisateur peut se connecter avec email et mot de passe",
                                status=CheckStatus.PASS, evidence="LoginController.login() implémenté avec validation."),
            AcceptanceCriterion(id="AC-2", description="L'utilisateur peut se connecter via OAuth2 (Google)",
                                status=CheckStatus.PASS, evidence="OAuth2 callback avec Google implémenté."),
            AcceptanceCriterion(id="AC-3", description="L'utilisateur peut se connecter via OAuth2 (GitHub)",
                                status=CheckStatus.PASS, evidence="OAuth2 callback avec GitHub implémenté."),
            AcceptanceCriterion(id="AC-4", description="Les erreurs de connexion affichent un message clair",
                                status=CheckStatus.PASS, evidence="Messages d'erreur dans LoginForm states."),
        ],
        definition_of_done=[
            AcceptanceCriterion(id="DoD-1", description="Tests unitaires écrits", status=CheckStatus.PASS,
                                evidence="2 fichiers de tests ajoutés."),
            AcceptanceCriterion(id="DoD-2", description="Diagramme UML mis à jour", status=CheckStatus.PASS,
                                evidence="auth.puml modifié."),
        ],
        status=CheckStatus.OK,
        summary="Tous les AC et DoD sont satisfaits.",
        recommended_verdict=Verdict.PASS,
    )


def make_jira_validation_fail() -> JiraValidationResult:
    """Agent 4 — Jira avec AC en échec."""
    return JiraValidationResult(
        jira_key="PROJ-42",
        jira_summary="Implémenter la page de connexion avec OAuth2",
        jira_description="En tant qu'utilisateur, je veux pouvoir me connecter via email/mot de passe ou OAuth2.",
        jira_status="In Review",
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-1", description="L'utilisateur peut se connecter avec email et mot de passe",
                                status=CheckStatus.PASS, evidence="LoginController.login() implémenté."),
            AcceptanceCriterion(id="AC-2", description="L'utilisateur peut se connecter via OAuth2 (Google)",
                                status=CheckStatus.PASS, evidence="OAuth2 Google implémenté."),
            AcceptanceCriterion(id="AC-3", description="L'utilisateur peut se connecter via OAuth2 (GitHub)",
                                status=CheckStatus.FAIL, evidence="Callback GitHub non trouvé dans le code."),
            AcceptanceCriterion(id="AC-4", description="Les erreurs de connexion affichent un message clair",
                                status=CheckStatus.FAIL, evidence="Aucun état d'erreur détecté dans LoginForm."),
        ],
        definition_of_done=[
            AcceptanceCriterion(id="DoD-1", description="Tests unitaires écrits", status=CheckStatus.FAIL,
                                evidence="Aucun fichier de test ajouté."),
            AcceptanceCriterion(id="DoD-2", description="Diagramme UML mis à jour", status=CheckStatus.PASS,
                                evidence="auth.puml modifié."),
        ],
        status=CheckStatus.FAIL,
        summary="2 AC en échec + 1 DoD en échec.",
        recommended_verdict=Verdict.FAIL,
    )


# ════════════════════════════════════════════
#  SCÉNARIOS
# ════════════════════════════════════════════

SCENARIOS = {
    "pass": {
        "description": "✅ Scénario PASS — Tout est conforme",
        "code": make_code_analysis_pass,
        "uml": make_uml_check_pass,
        "figma": make_figma_check_pass,
        "jira": make_jira_validation_pass,
    },
    "fail": {
        "description": "❌ Scénario FAIL — AC Jira en échec + UML mismatch + Figma écart + pas de tests",
        "code": make_code_analysis_fail,
        "uml": make_uml_check_fail,
        "figma": make_figma_check_fail,
        "jira": make_jira_validation_fail,
    },
    "blocked": {
        "description": "🟡 Scénario BLOCKED — Agents indisponibles (pas de Jira/Figma/UML)",
        "code": make_code_analysis_pass,
        "uml": lambda: None,
        "figma": lambda: None,
        "jira": lambda: None,
    },
}


# ════════════════════════════════════════════
#  SIMULATION
# ════════════════════════════════════════════

def display_header(scenario_name: str, scenario_desc: str):
    console.print()
    console.print(Panel(
        f"[bold cyan]🧪 SIMULATION LOCALE DU PIPELINE PR-GUARDIAN[/]\n\n"
        f"Scénario : [bold]{scenario_desc}[/]\n"
        f"Date     : {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"Mode     : Simulation (aucun appel API)",
        title="🛡️ PR-Guardian Orchestrator",
        border_style="cyan",
    ))
    console.print()


def display_step(step: str, description: str, status: str = "⏳"):
    console.print(f"  {status} [bold]{step}[/] — {description}")


def display_agent_result(agent_name: str, score: str, status_emoji: str):
    console.print(f"    {status_emoji} {agent_name:<30} {score}")


def build_validation_table(
    jira: JiraValidationResult | None,
    uml: UMLCheckResult | None,
    figma: FigmaCheckResult | None,
) -> list[ValidationRow]:
    """Construit la table de validation à partir des résultats des agents."""
    rows: list[ValidationRow] = []

    if jira:
        for ac in jira.acceptance_criteria:
            rows.append(ValidationRow(
                category="Jira AC", item=f"[{ac.id}] {ac.description[:50]}",
                status=ac.status, evidence=ac.evidence[:60],
            ))
        for dod in jira.definition_of_done:
            rows.append(ValidationRow(
                category="Jira DoD", item=f"[{dod.id}] {dod.description[:50]}",
                status=dod.status, evidence=dod.evidence[:60],
            ))
    else:
        rows.append(ValidationRow(category="Jira", item="Non disponible", status=CheckStatus.BLOCKED))

    if uml:
        if uml.mismatches:
            for m in uml.mismatches:
                rows.append(ValidationRow(
                    category="UML", item=f"{m.element}: {m.issue[:40]}",
                    status=CheckStatus.FAIL, evidence=m.suggestion[:60],
                ))
        else:
            rows.append(ValidationRow(category="UML", item="Diagramme cohérent", status=CheckStatus.OK,
                                       evidence=uml.summary[:60]))
    else:
        rows.append(ValidationRow(category="UML", item="Non disponible", status=CheckStatus.BLOCKED))

    if figma:
        for m in figma.mappings:
            rows.append(ValidationRow(
                category="Figma", item=m.requirement.frame_name,
                status=m.implementation_status, evidence=(m.evidence or m.gap)[:60],
            ))
    else:
        rows.append(ValidationRow(category="Figma", item="Non disponible", status=CheckStatus.BLOCKED))

    return rows


def format_pr_comment(verdict: JudgeVerdict, validation_table: list[ValidationRow]) -> str:
    """Génère le commentaire PR formaté (comme en production)."""
    v = verdict
    emoji = "✅" if v.verdict == Verdict.PASS else ("❌" if v.verdict == Verdict.FAIL else "🚫")

    lines = [
        f"## {emoji} PR-Guardian — {v.verdict.value} (score: {v.confidence_score}/100)",
        "",
        "### Justification",
    ]
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
    for row in validation_table:
        lines.append(f"| {row.category} | {row.item} | {row.status.value} | {row.evidence} |")

    lines.append("")
    lines.append("---")
    lines.append("*PR-Guardian Orchestrator — Team7*")

    return "\n".join(lines)


async def run_simulation(scenario_name: str):
    """Exécute la simulation complète d'un scénario."""

    scenario = SCENARIOS[scenario_name]
    display_header(scenario_name, scenario["description"])

    context = make_pr_context()

    # ── ÉTAPE 0 : Contexte ──
    display_step("Étape 0", "Récupération du contexte PR", "📋")
    console.print(f"    Repo      : [cyan]{context.repo}[/]")
    console.print(f"    PR        : [cyan]#{context.pr_number}[/] — {context.pr_title}")
    console.print(f"    Branche   : [cyan]{context.branch}[/]")
    console.print(f"    Auteur    : [cyan]{context.pr_author}[/] ({context.pr_author_email})")
    console.print(f"    Jira      : [green]{context.jira_key}[/]")
    console.print(f"    Figma     : [green]{context.figma_link}[/]")
    console.print(f"    UML       : [green]{len(context.uml_files)} fichier(s)[/]")
    console.print()

    # ── ÉTAPE 1 : Agents parallèles ──
    display_step("Étape 1", "Exécution parallèle des agents", "⚡")
    console.print()

    code_analysis = scenario["code"]()
    uml_check = scenario["uml"]()
    figma_check = scenario["figma"]()
    jira_validation = scenario["jira"]()

    # Afficher les résultats agent par agent
    if code_analysis:
        n_files = len(code_analysis.files_modified)
        n_tests = len(code_analysis.tests_added) + len(code_analysis.tests_modified)
        has_tests = n_tests > 0
        display_agent_result(
            "Agent 1 — Code Analyst",
            f"({n_files} fichiers, {len(code_analysis.endpoints)} endpoints, {n_tests} tests)",
            "✅" if has_tests else "⚠️",
        )
        for feat in code_analysis.features_detected:
            console.print(f"      • {feat}")
        if code_analysis.sensitive_points:
            for sp in code_analysis.sensitive_points:
                console.print(f"      ⚠️  [yellow]{sp}[/]")
    else:
        display_agent_result("Agent 1 — Code Analyst", "(non disponible)", "🚫")

    console.print()

    if uml_check:
        n_diagrams = len(uml_check.diagrams_found)
        n_mismatches = len(uml_check.mismatches)
        display_agent_result(
            "Agent 2 — UML Checker",
            f"({n_diagrams} diagramme(s), {n_mismatches} écart(s))",
            "✅" if uml_check.status == CheckStatus.OK else "❌",
        )
        if uml_check.mismatches:
            for m in uml_check.mismatches:
                console.print(f"      ❌ [{m.severity.value}] {m.element}: {m.issue}")
    else:
        display_agent_result("Agent 2 — UML Checker", "(non disponible — aucun fichier UML)", "🚫")

    console.print()

    if figma_check:
        n_ok = sum(1 for m in figma_check.mappings if m.implementation_status == CheckStatus.OK)
        n_total = len(figma_check.mappings)
        display_agent_result(
            "Agent 3 — Figma Checker",
            f"({n_ok}/{n_total} composants conformes)",
            "✅" if figma_check.status == CheckStatus.OK else "❌",
        )
        for m in figma_check.mappings:
            emoji = "✅" if m.implementation_status == CheckStatus.OK else "❌"
            detail = m.evidence if m.implementation_status == CheckStatus.OK else m.gap
            console.print(f"      {emoji} {m.requirement.frame_name}: {detail[:70]}")
    else:
        display_agent_result("Agent 3 — Figma Checker", "(non disponible — aucun lien Figma)", "🚫")

    console.print()

    if jira_validation:
        n_ac_pass = sum(1 for ac in jira_validation.acceptance_criteria if ac.status == CheckStatus.PASS)
        n_ac_total = len(jira_validation.acceptance_criteria)
        n_dod_pass = sum(1 for d in jira_validation.definition_of_done if d.status == CheckStatus.PASS)
        n_dod_total = len(jira_validation.definition_of_done)
        display_agent_result(
            "Agent 4 — Jira Validator",
            f"(AC: {n_ac_pass}/{n_ac_total}, DoD: {n_dod_pass}/{n_dod_total})",
            "✅" if jira_validation.status == CheckStatus.OK else "❌",
        )
        for ac in jira_validation.acceptance_criteria:
            emoji = "✅" if ac.status == CheckStatus.PASS else "❌"
            console.print(f"      {emoji} [{ac.id}] {ac.description}")
        for dod in jira_validation.definition_of_done:
            emoji = "✅" if dod.status == CheckStatus.PASS else "❌"
            console.print(f"      {emoji} [{dod.id}] {dod.description}")
    else:
        display_agent_result("Agent 4 — Jira Validator", "(non disponible — aucun ticket Jira)", "🚫")

    console.print()

    # ── ÉTAPE 2 : LLM-as-a-Judge (heuristique en simulation) ──
    display_step("Étape 2", "LLM-as-a-Judge (fallback heuristique)", "⚖️")
    console.print()

    verdict = JudgeAgent._heuristic_verdict(
        code_analysis, uml_check, figma_check, jira_validation
    )

    verdict_color = {"PASS": "green", "FAIL": "red", "BLOCKED": "yellow"}[verdict.verdict.value]
    verdict_emoji = {"PASS": "✅", "FAIL": "❌", "BLOCKED": "🚫"}[verdict.verdict.value]

    console.print(f"    Verdict    : [{verdict_color}][bold]{verdict_emoji} {verdict.verdict.value}[/][/]")
    console.print(f"    Confiance  : [{verdict_color}]{verdict.confidence_score}/100[/]")
    console.print()
    console.print("    [bold]Justification :[/]")
    for j in verdict.justification:
        console.print(f"      • {j}")

    if verdict.must_fix:
        console.print()
        console.print("    [bold red]🔧 Items à corriger :[/]")
        for mf in verdict.must_fix:
            console.print(f"      • [bold][{mf.severity.value}][/] {mf.description}")
            if mf.location:
                console.print(f"        📍 {mf.location}")
            if mf.suggestion:
                console.print(f"        💡 {mf.suggestion}")

    console.print()

    # ── ÉTAPE 3 : Rapport + Actions simulées ──
    display_step("Étape 3", "Génération du rapport et actions", "📝")
    console.print()

    validation_table = build_validation_table(jira_validation, uml_check, figma_check)

    # Table Rich
    table = Table(title="📊 Table de Validation", show_lines=True, border_style="dim")
    table.add_column("Catégorie", style="bold cyan", width=12)
    table.add_column("Item", width=50)
    table.add_column("Statut", justify="center", width=10)
    table.add_column("Preuve", width=60)

    for row in validation_table:
        status_style = {
            "OK": "[green]✅ OK[/]", "PASS": "[green]✅ PASS[/]",
            "FAIL": "[red]❌ FAIL[/]", "MISMATCH": "[red]❌ MISMATCH[/]",
            "BLOCKED": "[yellow]🚫 BLOCKED[/]", "PARTIAL": "[yellow]⚠️ PARTIAL[/]",
        }.get(row.status.value, row.status.value)
        table.add_row(row.category, row.item, status_style, row.evidence)

    console.print(table)
    console.print()

    # Actions simulées
    console.print("  [bold]Actions simulées :[/]")
    if verdict.verdict == Verdict.PASS:
        console.print("    📧 [green]Email PASS → Scrum Master[/] (simulé)")
        console.print(f"    📋 [green]Jira {context.jira_key} → Done (transition #{31})[/] (simulé)")
    elif verdict.verdict == Verdict.FAIL:
        console.print(f"    📧 [red]Email FAIL → {context.pr_author}[/] (simulé)")
        console.print(f"    📋 [red]Jira {context.jira_key} → Needs Fix (transition #{21})[/] (simulé)")
    else:
        console.print("    📧 [yellow]Email BLOCKED → Scrum Master + Dev[/] (simulé)")
        console.print(f"    📋 [yellow]Jira {context.jira_key} → Pas de transition[/] (simulé)")

    console.print("    💬 [cyan]Commentaire PR posté[/] (simulé)")
    console.print()

    # ── Commentaire PR (preview) ──
    pr_comment = format_pr_comment(verdict, validation_table)

    console.print(Panel(
        pr_comment,
        title="💬 Aperçu du commentaire PR (Markdown)",
        border_style="dim",
    ))
    console.print()

    # ── JSON output ──
    report = FinalReport(
        pr_context=context,
        verdict=verdict,
        validation_table=validation_table,
        code_analysis=code_analysis,
        uml_check=uml_check,
        figma_check=figma_check,
        jira_validation=jira_validation,
    )

    # ── Verdict final ──
    console.print(Panel(
        f"[bold {verdict_color}]{verdict_emoji}  VERDICT FINAL : {verdict.verdict.value}[/]\n"
        f"[{verdict_color}]   Confiance : {verdict.confidence_score}/100[/]\n"
        f"   Agents    : {4 if code_analysis else 0} exécuté(s)\n"
        f"   Must-fix  : {len(verdict.must_fix)} item(s)",
        title="🛡️ PR-Guardian — Résultat",
        border_style=verdict_color,
    ))
    console.print()

    # Save JSON report
    output_path = Path(__file__).parent.parent / f"simulation_report_{scenario_name}.json"
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"  💾 Rapport JSON sauvegardé : [cyan]{output_path}[/]")
    console.print()


# ════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════

@click.command()
@click.option(
    "--scenario", "-s",
    type=click.Choice(["pass", "fail", "blocked", "all"]),
    default="all",
    help="Scénario à simuler (pass, fail, blocked, ou all)",
)
def main(scenario: str):
    """🧪 Simule le pipeline PR-Guardian en local sans API."""
    if scenario == "all":
        for s in ["pass", "fail", "blocked"]:
            asyncio.run(run_simulation(s))
            console.print("━" * 80)
            console.print()
    else:
        asyncio.run(run_simulation(scenario))


if __name__ == "__main__":
    main()
