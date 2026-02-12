"""Tests de l'Agent 4 — Jira Validator."""

import pytest
from unittest.mock import MagicMock

from pr_guardian.agents.jira_validator import JiraValidatorAgent, _keyword_overlap
from pr_guardian.models import CheckStatus, Verdict


def _make_agent_no_llm(**kwargs):
    """Create a JiraValidatorAgent with LLM disabled."""
    agent = JiraValidatorAgent(**kwargs)
    mock_settings = MagicMock()
    mock_settings.llm_configured = False
    agent._settings = mock_settings
    return agent


class TestJiraValidatorAgent:
    """Tests pour JiraValidatorAgent."""

    @pytest.mark.asyncio
    async def test_run_blocked_no_jira_key(self, sample_pr_context):
        """Vérifie le statut BLOCKED quand aucune clé Jira n'est fournie."""
        sample_pr_context.jira_key = None

        agent = _make_agent_no_llm()
        result = await agent.run(sample_pr_context)

        assert result.status == CheckStatus.BLOCKED
        assert result.recommended_verdict == Verdict.BLOCKED
        assert "Aucune clé Jira" in result.summary

    @pytest.mark.asyncio
    async def test_run_extracts_acceptance_criteria(self, sample_pr_context, sample_code_analysis):
        """Vérifie l'extraction des acceptance criteria."""
        mock_jira = MagicMock()
        mock_jira.get_issue_fields.return_value = {
            "summary": "Test issue",
            "description": "Description test",
            "status": "In Progress",
            "acceptance_criteria": [
                "L'utilisateur peut se connecter avec email/mot de passe",
                "L'utilisateur reçoit un token après connexion",
            ],
            "definition_of_done": [
                "Tests unitaires ajoutés",
            ],
            "figma_links": [],
        }

        agent = _make_agent_no_llm(jira_client=mock_jira)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.acceptance_criteria) == 2
        assert len(result.definition_of_done) == 1
        assert result.jira_key == "PROJ-123"

    @pytest.mark.asyncio
    async def test_run_validates_ac_pass(self, sample_pr_context, sample_code_analysis):
        """Vérifie la validation des AC quand le code correspond."""
        mock_jira = MagicMock()
        mock_jira.get_issue_fields.return_value = {
            "summary": "Auth feature",
            "description": "",
            "status": "In Progress",
            "acceptance_criteria": [
                "Endpoint /api/auth/login disponible",  # Présent dans sample_code_analysis
            ],
            "definition_of_done": [],
            "figma_links": [],
        }

        agent = _make_agent_no_llm(jira_client=mock_jira)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.acceptance_criteria) == 1
        assert result.acceptance_criteria[0].status == CheckStatus.PASS

    @pytest.mark.asyncio
    async def test_run_validates_ac_fail(self, sample_pr_context, sample_code_analysis):
        """Vérifie la validation des AC quand le code ne correspond pas."""
        mock_jira = MagicMock()
        mock_jira.get_issue_fields.return_value = {
            "summary": "Payment feature",
            "description": "",
            "status": "In Progress",
            "acceptance_criteria": [
                "L'utilisateur peut effectuer un paiement par carte",  # Absent du code
            ],
            "definition_of_done": [],
            "figma_links": [],
        }

        agent = _make_agent_no_llm(jira_client=mock_jira)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.acceptance_criteria) == 1
        assert result.acceptance_criteria[0].status == CheckStatus.FAIL
        assert result.recommended_verdict == Verdict.FAIL

    @pytest.mark.asyncio
    async def test_run_blocked_on_empty_criteria(self, sample_pr_context):
        """Vérifie le statut BLOCKED quand il n'y a pas de critères."""
        mock_jira = MagicMock()
        mock_jira.get_issue_fields.return_value = {
            "summary": "Vague task",
            "description": "No criteria here",
            "status": "To Do",
            "acceptance_criteria": [],
            "definition_of_done": [],
            "figma_links": [],
        }

        agent = _make_agent_no_llm(jira_client=mock_jira)
        result = await agent.run(sample_pr_context)

        assert result.status == CheckStatus.PARTIAL
        assert "aucun acceptance criteria" in result.summary.lower()


class TestKeywordOverlap:
    """Tests pour la fonction _keyword_overlap."""

    def test_overlap_true(self):
        """Vérifie la détection de chevauchement."""
        assert _keyword_overlap("login endpoint test", "login controller") is True

    def test_overlap_false(self):
        """Vérifie l'absence de chevauchement."""
        assert _keyword_overlap("apple banana", "orange grape") is False

    def test_overlap_short_words_ignored(self):
        """Vérifie que les mots courts sont ignorés."""
        # Mots de moins de 4 caractères ne comptent pas
        assert _keyword_overlap("a b c", "a b c") is False

    def test_overlap_empty(self):
        """Vérifie le comportement avec chaînes vides."""
        assert _keyword_overlap("", "test") is False
