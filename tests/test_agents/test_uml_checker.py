"""Tests de l'Agent 2 — UML Checker."""

import pytest
from unittest.mock import MagicMock

from pr_guardian.agents.uml_checker import UMLCheckerAgent
from pr_guardian.models import CheckStatus, CodeAnalysisResult
from pr_guardian.parsers.plantuml_parser import PlantUMLParser


def _make_agent_no_llm(**kwargs):
    """Create a UMLCheckerAgent with LLM disabled."""
    agent = UMLCheckerAgent(**kwargs)
    mock_settings = MagicMock()
    mock_settings.llm_configured = False
    agent._settings = mock_settings
    return agent


class TestUMLCheckerAgent:
    """Tests pour UMLCheckerAgent."""

    @pytest.mark.asyncio
    async def test_run_blocked_no_uml(self, sample_pr_context):
        """Vérifie le statut BLOCKED quand aucun UML n'est trouvé."""
        mock_gh = MagicMock()
        mock_gh.find_uml_files.return_value = []

        sample_pr_context.uml_files = []

        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context)

        assert result.status == CheckStatus.BLOCKED
        assert "Aucun fichier PlantUML" in result.summary

    @pytest.mark.asyncio
    async def test_run_parses_uml(self, sample_pr_context, sample_puml_content):
        """Vérifie le parsing des fichiers UML."""
        mock_gh = MagicMock()
        mock_gh.find_uml_files.return_value = ["docs/auth.puml"]
        mock_gh.get_file_content.return_value = sample_puml_content

        sample_pr_context.uml_files = []

        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context)

        assert len(result.diagrams_found) == 1
        assert result.diagrams_found[0].diagram_type == "class"

        # Vérifier les entités parsées
        entity_names = [e.name for e in result.diagrams_found[0].entities]
        assert "AuthService" in entity_names
        assert "User" in entity_names

    @pytest.mark.asyncio
    async def test_run_detects_mismatch(self, sample_pr_context, sample_puml_content, sample_code_analysis):
        """Vérifie la détection des écarts code/UML."""
        mock_gh = MagicMock()
        mock_gh.find_uml_files.return_value = ["docs/auth.puml"]
        mock_gh.get_file_content.return_value = """
@startuml
class OldClass {
    +oldMethod()
}
@enduml
"""
        sample_pr_context.uml_files = []

        # Le code touche des classes qui ne sont pas dans l'UML
        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context, code_analysis=sample_code_analysis)

        # Il devrait y avoir des mismatches car les classes du code ne sont pas dans l'UML
        assert len(result.mismatches) > 0
        mismatch_elements = [m.element.lower() for m in result.mismatches]
        assert any("logincontroller" in e or "signupcontroller" in e or "authservice" in e 
                   for e in mismatch_elements)


class TestPlantUMLParser:
    """Tests pour le parseur PlantUML."""

    def test_parse_class_diagram(self, sample_puml_content):
        """Vérifie le parsing d'un diagramme de classes."""
        diagram = PlantUMLParser.parse(sample_puml_content, "test.puml")

        assert diagram.diagram_type == "class"
        assert len(diagram.entities) >= 4  # AuthService, User, LoginController, SignupController

    def test_parse_extracts_methods(self, sample_puml_content):
        """Vérifie l'extraction des méthodes."""
        diagram = PlantUMLParser.parse(sample_puml_content, "test.puml")

        auth_service = next((e for e in diagram.entities if e.name == "AuthService"), None)
        assert auth_service is not None
        assert len(auth_service.methods) >= 2

    def test_parse_extracts_relations(self, sample_puml_content):
        """Vérifie l'extraction des relations."""
        diagram = PlantUMLParser.parse(sample_puml_content, "test.puml")

        assert len(diagram.relations) >= 1
        relation_sources = [r.source for r in diagram.relations]
        assert "AuthService" in relation_sources or "LoginController" in relation_sources

    def test_detect_sequence_diagram(self):
        """Vérifie la détection d'un diagramme de séquence."""
        content = """
@startuml
participant User
participant Server
User -> Server: login
Server --> User: token
@enduml
"""
        diagram = PlantUMLParser.parse(content, "seq.puml")
        assert diagram.diagram_type == "sequence"

    def test_classify_relation_inheritance(self):
        """Vérifie la classification des relations d'héritage."""
        assert PlantUMLParser._classify_relation("--|>") == "inheritance"
        assert PlantUMLParser._classify_relation("<|--") == "inheritance"

    def test_classify_relation_composition(self):
        """Vérifie la classification des relations de composition."""
        assert PlantUMLParser._classify_relation("--*") == "composition"
        assert PlantUMLParser._classify_relation("*--") == "composition"
