"""Tests de l'Agent 1 — Code Analyst."""

import pytest
from unittest.mock import MagicMock

from pr_guardian.agents.code_analyst import CodeAnalystAgent
from pr_guardian.models import ModifiedFile


def _make_agent_no_llm(**kwargs):
    """Create a CodeAnalystAgent with LLM disabled."""
    agent = CodeAnalystAgent(**kwargs)
    mock_settings = MagicMock()
    mock_settings.llm_configured = False
    agent._settings = mock_settings
    return agent


class TestCodeAnalystAgent:
    """Tests pour CodeAnalystAgent."""

    @pytest.mark.asyncio
    async def test_run_extracts_features(self, sample_pr_context):
        """Vérifie l'extraction des fonctionnalités depuis le diff."""
        mock_gh = MagicMock()
        mock_gh.get_modified_files.return_value = [
            ModifiedFile(
                filename="src/auth/login.py",
                status="added",
                additions=50,
                deletions=0,
                patch="""
@@ -0,0 +1,10 @@
+from fastapi import APIRouter
+router = APIRouter()
+
+@router.post("/api/auth/login")
+async def login():
+    pass
+
+class LoginController:
+    def authenticate(self):
+        pass
""",
            ),
        ]

        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context)

        assert len(result.files_modified) == 1
        assert "/api/auth/login" in result.endpoints
        assert "LoginController" in result.classes_touched
        assert "authenticate" in result.methods_touched

    @pytest.mark.asyncio
    async def test_run_detects_tests(self, sample_pr_context):
        """Vérifie la détection des fichiers de test."""
        mock_gh = MagicMock()
        mock_gh.get_modified_files.return_value = [
            ModifiedFile(filename="src/main.py", status="modified", additions=10, deletions=5, patch=""),
            ModifiedFile(filename="tests/test_main.py", status="added", additions=20, deletions=0, patch=""),
        ]

        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context)

        assert "tests/test_main.py" in result.tests_added
        assert "tests/test_main.py" not in result.tests_modified

    @pytest.mark.asyncio
    async def test_run_detects_sensitive_files(self, sample_pr_context):
        """Vérifie la détection des fichiers sensibles."""
        mock_gh = MagicMock()
        mock_gh.get_modified_files.return_value = [
            ModifiedFile(filename="src/auth/password_manager.py", status="modified", additions=10, deletions=5, patch=""),
            ModifiedFile(filename="src/utils/helpers.py", status="modified", additions=5, deletions=2, patch=""),
        ]

        agent = _make_agent_no_llm(github_client=mock_gh)
        result = await agent.run(sample_pr_context)

        assert any("sensible" in s for s in result.sensitive_points)
        assert any("password_manager" in s for s in result.sensitive_points)

    def test_build_summary(self, sample_code_analysis):
        """Vérifie la construction du résumé."""
        summary = CodeAnalystAgent._build_summary(sample_code_analysis)

        assert "5" in summary  # nombre de fichiers
        assert "+120" in summary  # additions
        assert "-30" in summary  # deletions

    def test_assess_test_coverage_no_tests(self):
        """Vérifie l'évaluation de couverture sans tests."""
        from pr_guardian.models import CodeAnalysisResult, ModifiedFile
        
        result = CodeAnalysisResult(
            files_modified=[ModifiedFile(filename="src/main.py", status="modified")],
        )
        
        coverage = CodeAnalystAgent._assess_test_coverage(result)
        assert "Aucun test" in coverage
