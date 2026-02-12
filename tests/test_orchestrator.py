"""Tests de l'orchestrateur."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pr_guardian.orchestrator import Orchestrator
from pr_guardian.models import (
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    JiraValidationResult,
    PRContext,
    UMLCheckResult,
    Verdict,
)


class TestOrchestrator:
    """Tests pour l'Orchestrator."""

    @pytest.mark.asyncio
    async def test_step0_context_extracts_jira_key(self, sample_pr_context):
        """Vérifie que le contexte extrait bien la clé Jira."""
        with patch.object(Orchestrator, "_get_github") as mock_gh:
            mock_client = MagicMock()
            mock_client.build_pr_context.return_value = sample_pr_context
            mock_client.extract_jira_key.return_value = "PROJ-123"
            mock_client.find_figma_links.return_value = []
            mock_client.find_uml_files.return_value = []
            mock_gh.return_value = mock_client

            orchestrator = Orchestrator()
            context = await orchestrator._step0_context("Team7/test", 1, "main")

            assert context.jira_key == "PROJ-123"

    @pytest.mark.asyncio
    async def test_safe_run_catches_exceptions(self, sample_pr_context):
        """Vérifie que _safe_run capture les exceptions."""
        class FailingAgent:
            name = "Failing"
            async def run(self, context, **kwargs):
                raise ValueError("Boom!")

        agent = FailingAgent()
        result = await Orchestrator._safe_run(agent, sample_pr_context)
        
        assert isinstance(result, ValueError)
        assert str(result) == "Boom!"

    def test_format_pr_comment_pass(self, sample_pr_context, sample_judge_verdict_pass):
        """Vérifie le formatage du commentaire PR pour un PASS."""
        from pr_guardian.models import FinalReport, ValidationRow

        report = FinalReport(
            pr_context=sample_pr_context,
            verdict=sample_judge_verdict_pass,
            validation_table=[
                ValidationRow(category="Jira AC", item="Test", status=CheckStatus.PASS, evidence="OK"),
            ],
        )

        comment = Orchestrator._format_pr_comment(report)

        assert "## ✅ PR-Guardian — PASS" in comment
        assert "85/100" in comment
        assert "MUST-FIX" not in comment  # Pas de must-fix pour un PASS

    def test_format_pr_comment_fail(self, sample_pr_context, sample_judge_verdict_fail):
        """Vérifie le formatage du commentaire PR pour un FAIL."""
        from pr_guardian.models import FinalReport, ValidationRow

        report = FinalReport(
            pr_context=sample_pr_context,
            verdict=sample_judge_verdict_fail,
            validation_table=[
                ValidationRow(category="Jira AC", item="Test", status=CheckStatus.FAIL, evidence="NOK"),
            ],
        )

        comment = Orchestrator._format_pr_comment(report)

        assert "## ❌ PR-Guardian — FAIL" in comment
        assert "🔧 Items à corriger" in comment
        assert "CRITICAL" in comment
