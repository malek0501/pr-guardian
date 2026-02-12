"""Tests de l'Agent 3 — Figma Checker."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from pr_guardian.agents.figma_checker import FigmaCheckerAgent, _similarity
from pr_guardian.integrations.figma_client import FigmaClient
from pr_guardian.models import CheckStatus, FigmaRequirement


def _make_agent_no_llm(**kwargs):
    """Create a FigmaCheckerAgent with LLM disabled."""
    agent = FigmaCheckerAgent(**kwargs)
    mock_settings = MagicMock()
    mock_settings.llm_configured = False
    agent._settings = mock_settings
    return agent


class TestFigmaCheckerAgent:
    """Tests pour FigmaCheckerAgent."""

    @pytest.mark.asyncio
    async def test_run_blocked_no_figma_link(self, sample_pr_context):
        """Vérifie le statut BLOCKED quand aucun lien Figma n'est fourni."""
        sample_pr_context.figma_link = None

        agent = _make_agent_no_llm()
        result = await agent.run(sample_pr_context)

        assert result.status == CheckStatus.BLOCKED
        assert "Aucun lien Figma" in result.summary

    @pytest.mark.asyncio
    async def test_run_extracts_requirements(self, sample_pr_context, sample_code_analysis):
        """Vérifie l'extraction des exigences Figma."""
        mock_figma = MagicMock()
        mock_figma.extract_requirements.return_value = [
            FigmaRequirement(
                frame_id="1:100",
                frame_name="LoginForm",
                page_name="Auth",
                components=["Button", "TextInput"],
                texts=["Email", "Password", "Login"],
            ),
        ]
        mock_figma.get_file_metadata.return_value = {"pages": [{"name": "Auth"}]}

        agent = _make_agent_no_llm(figma_client=mock_figma)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.requirements) == 1
        assert result.requirements[0].frame_name == "LoginForm"
        assert len(result.mappings) == 1

    @pytest.mark.asyncio
    async def test_run_detects_mapping_ok(self, sample_pr_context, sample_code_analysis):
        """Vérifie la correspondance OK quand le code matche le Figma."""
        mock_figma = MagicMock()
        mock_figma.extract_requirements.return_value = [
            FigmaRequirement(
                frame_id="1:100",
                frame_name="LoginController",  # Même nom que la classe dans le code
                page_name="Auth",
            ),
        ]
        mock_figma.get_file_metadata.return_value = {"pages": [{"name": "Auth"}]}

        agent = _make_agent_no_llm(figma_client=mock_figma)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.mappings) == 1
        assert result.mappings[0].implementation_status == CheckStatus.OK

    @pytest.mark.asyncio
    async def test_run_detects_mapping_fail(self, sample_pr_context, sample_code_analysis):
        """Vérifie la détection d'un écart Figma."""
        mock_figma = MagicMock()
        mock_figma.extract_requirements.return_value = [
            FigmaRequirement(
                frame_id="1:200",
                frame_name="DashboardWidget",  # N'existe pas dans le code
                page_name="Dashboard",
                components=["ChartComponent", "DataTable"],
            ),
        ]
        mock_figma.get_file_metadata.return_value = {"pages": [{"name": "Dashboard"}]}

        agent = _make_agent_no_llm(figma_client=mock_figma)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        assert len(result.mappings) == 1
        assert result.mappings[0].implementation_status == CheckStatus.FAIL
        assert "DashboardWidget" in result.mappings[0].gap


class TestFigmaClient:
    """Tests pour le client Figma."""

    def test_parse_figma_url_file(self):
        """Vérifie le parsing d'une URL Figma /file/."""
        url = "https://www.figma.com/file/ABC123/Design-System?node-id=0%3A1"
        result = FigmaClient.parse_figma_url(url)

        assert result["file_key"] == "ABC123"
        assert result["node_id"] == "0:1"

    def test_parse_figma_url_design(self):
        """Vérifie le parsing d'une URL Figma /design/."""
        url = "https://www.figma.com/design/XYZ789/My-Project"
        result = FigmaClient.parse_figma_url(url)

        assert result["file_key"] == "XYZ789"
        assert result["node_id"] is None

    def test_parse_figma_url_invalid(self):
        """Vérifie l'erreur pour une URL invalide."""
        with pytest.raises(ValueError, match="URL Figma invalide"):
            FigmaClient.parse_figma_url("https://example.com/not-figma")


class TestSimilarity:
    """Tests pour la fonction de similarité."""

    def test_similarity_identical(self):
        """Vérifie la similarité pour des chaînes identiques."""
        assert _similarity("hello", "hello") == 1.0

    def test_similarity_similar(self):
        """Vérifie la similarité pour des chaînes proches."""
        sim = _similarity("loginform", "logincontroller")
        assert sim > 0.1  # Partagent des trigrammes autour de "login"
        # Vérifier aussi que des chaînes très proches ont un score élevé
        sim2 = _similarity("loginform", "loginforms")
        assert sim2 > 0.7

    def test_similarity_different(self):
        """Vérifie la similarité pour des chaînes différentes."""
        sim = _similarity("apple", "orange")
        assert sim < 0.3

    def test_similarity_empty(self):
        """Vérifie la similarité avec chaînes vides."""
        assert _similarity("", "test") == 0.0
        assert _similarity("test", "") == 0.0
