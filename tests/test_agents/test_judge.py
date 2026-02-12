"""Tests du LLM-as-a-Judge."""

import pytest
from unittest.mock import MagicMock, patch
import json

from pr_guardian.agents.judge import JudgeAgent
from pr_guardian.models import CheckStatus, Severity, Verdict


class TestJudgeAgent:
    """Tests pour le JudgeAgent."""

    @pytest.mark.asyncio
    async def test_heuristic_verdict_pass(
        self, sample_pr_context, sample_code_analysis, sample_uml_check,
        sample_figma_check, sample_jira_validation
    ):
        """Vérifie le verdict heuristique PASS."""
        verdict = JudgeAgent._heuristic_verdict(
            sample_code_analysis,
            sample_uml_check,
            sample_figma_check,
            sample_jira_validation,
        )

        assert verdict.verdict == Verdict.PASS
        assert verdict.confidence_score >= 60

    @pytest.mark.asyncio
    async def test_heuristic_verdict_blocked_no_data(self, sample_pr_context):
        """Vérifie le verdict heuristique BLOCKED sans données."""
        verdict = JudgeAgent._heuristic_verdict(None, None, None, None)

        assert verdict.verdict == Verdict.BLOCKED
        assert any("BLOQUÉ" in j for j in verdict.justification)

    @pytest.mark.asyncio
    async def test_heuristic_verdict_fail_uml_mismatch(
        self, sample_pr_context, sample_code_analysis, sample_figma_check, sample_jira_validation
    ):
        """Vérifie le verdict heuristique FAIL avec UML mismatch."""
        from pr_guardian.models import UMLCheckResult, UMLMismatch

        uml_fail = UMLCheckResult(
            status=CheckStatus.MISMATCH,
            mismatches=[
                UMLMismatch(
                    diagram_file="test.puml",
                    element="TestClass",
                    issue="Classe manquante",
                    severity=Severity.HIGH,
                )
            ],
        )

        verdict = JudgeAgent._heuristic_verdict(
            sample_code_analysis, uml_fail, sample_figma_check, sample_jira_validation
        )

        assert verdict.verdict == Verdict.FAIL
        assert len(verdict.must_fix) > 0

    @pytest.mark.asyncio
    async def test_heuristic_verdict_no_tests_penalty(self, sample_pr_context):
        """Vérifie la pénalité pour absence de tests."""
        from pr_guardian.models import CodeAnalysisResult, ModifiedFile

        code_no_tests = CodeAnalysisResult(
            files_modified=[ModifiedFile(filename="src/main.py", status="modified")],
            tests_added=[],
            tests_modified=[],
        )

        verdict = JudgeAgent._heuristic_verdict(code_no_tests, None, None, None)

        assert any("test" in j.lower() for j in verdict.justification)
        assert any(mf.description.lower().find("test") >= 0 for mf in verdict.must_fix)

    def test_parse_llm_response_valid(self):
        """Vérifie le parsing d'une réponse LLM valide."""
        raw = json.dumps({
            "verdict": "PASS",
            "confidence_score": 85,
            "justification": ["Point 1", "Point 2"],
            "must_fix": [],
        })

        verdict = JudgeAgent._parse_llm_response(raw)

        assert verdict.verdict == Verdict.PASS
        assert verdict.confidence_score == 85
        assert len(verdict.justification) == 2

    def test_parse_llm_response_with_must_fix(self):
        """Vérifie le parsing d'une réponse LLM avec must-fix."""
        raw = json.dumps({
            "verdict": "FAIL",
            "confidence_score": 30,
            "justification": ["Échec AC-1"],
            "must_fix": [
                {
                    "description": "AC-1 non implémenté",
                    "location": "src/auth.py",
                    "suggestion": "Ajouter la logique",
                    "severity": "CRITICAL",
                }
            ],
        })

        verdict = JudgeAgent._parse_llm_response(raw)

        assert verdict.verdict == Verdict.FAIL
        assert len(verdict.must_fix) == 1
        assert verdict.must_fix[0].severity == Severity.CRITICAL

    def test_parse_llm_response_invalid_json(self):
        """Vérifie le comportement avec JSON invalide."""
        raw = "not valid json"

        verdict = JudgeAgent._parse_llm_response(raw)

        assert verdict.verdict == Verdict.BLOCKED
        assert verdict.confidence_score == 0

    def test_build_evidence_dossier(
        self, sample_pr_context, sample_code_analysis, sample_uml_check,
        sample_figma_check, sample_jira_validation
    ):
        """Vérifie la construction du dossier de preuves."""
        evidence = JudgeAgent._build_evidence_dossier(
            sample_pr_context,
            sample_code_analysis,
            sample_uml_check,
            sample_figma_check,
            sample_jira_validation,
        )

        assert "## CONTEXTE PR" in evidence
        assert "## AGENT 1" in evidence
        assert "## AGENT 2" in evidence
        assert "## AGENT 3" in evidence
        assert "## AGENT 4" in evidence
        assert sample_pr_context.repo in evidence
        assert sample_pr_context.jira_key in evidence
