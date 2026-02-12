"""
Modèles de données — PR-Guardian Orchestrator.

Tous les objets échangés entre agents, orchestrateur et Judge
sont définis ici pour garantir typage et sérialisation cohérents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ════════════════════════════════════════════
#  Enums
# ════════════════════════════════════════════

class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class CheckStatus(str, Enum):
    OK = "OK"
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    MISMATCH = "MISMATCH"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "N/A"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


# ════════════════════════════════════════════
#  Contexte PR (entrée)
# ════════════════════════════════════════════

class PRContext(BaseModel):
    """Contexte d'une Pull Request à analyser."""
    repo: str = Field(..., description="owner/repo")
    pr_number: int = Field(..., description="Numéro de la PR")
    branch: str = Field(default="", description="Branche source")
    pr_title: str = Field(default="")
    pr_description: str = Field(default="")
    pr_author: str = Field(default="")
    pr_author_email: str = Field(default="")
    jira_key: Optional[str] = Field(default=None, description="Ex: PROJ-123")
    figma_link: Optional[str] = Field(default=None)
    uml_files: list[str] = Field(default_factory=list)


# ════════════════════════════════════════════
#  Fichier modifié
# ════════════════════════════════════════════

class ModifiedFile(BaseModel):
    filename: str
    status: str = ""  # added / modified / removed / renamed
    additions: int = 0
    deletions: int = 0
    patch: str = ""
    language: str = ""


# ════════════════════════════════════════════
#  Agent 1 — Code Analyst Output
# ════════════════════════════════════════════

class CodeAnalysisResult(BaseModel):
    """Résultat de l'Agent 1 — GitHub Code Analyst."""
    summary: str = ""
    files_modified: list[ModifiedFile] = Field(default_factory=list)
    features_detected: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    classes_touched: list[str] = Field(default_factory=list)
    methods_touched: list[str] = Field(default_factory=list)
    migrations_detected: list[str] = Field(default_factory=list)
    tests_added: list[str] = Field(default_factory=list)
    tests_modified: list[str] = Field(default_factory=list)
    test_coverage_info: str = ""
    sensitive_points: list[str] = Field(default_factory=list)
    raw_diff_stats: dict[str, Any] = Field(default_factory=dict)


# ════════════════════════════════════════════
#  Agent 2 — UML Checker Output
# ════════════════════════════════════════════

class UMLEntity(BaseModel):
    name: str
    entity_type: str = ""  # class, interface, actor, component…
    attributes: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class UMLRelation(BaseModel):
    source: str
    target: str
    relation_type: str = ""  # inheritance, composition, association, dependency…
    label: str = ""


class UMLDiagram(BaseModel):
    filepath: str
    diagram_type: str = ""  # class, sequence, activity, usecase…
    entities: list[UMLEntity] = Field(default_factory=list)
    relations: list[UMLRelation] = Field(default_factory=list)
    raw_content: str = ""


class UMLMismatch(BaseModel):
    diagram_file: str
    element: str
    issue: str  # "classe manquante", "relation absente"…
    severity: Severity = Severity.MEDIUM
    suggestion: str = ""


class UMLCheckResult(BaseModel):
    """Résultat de l'Agent 2 — PlantUML Consistency Checker."""
    diagrams_found: list[UMLDiagram] = Field(default_factory=list)
    mismatches: list[UMLMismatch] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.OK
    summary: str = ""


# ════════════════════════════════════════════
#  Agent 3 — Figma Checker Output
# ════════════════════════════════════════════

class FigmaRequirement(BaseModel):
    frame_id: str = ""
    frame_name: str = ""
    page_name: str = ""
    description: str = ""
    components: list[str] = Field(default_factory=list)
    texts: list[str] = Field(default_factory=list)
    states: list[str] = Field(default_factory=list)  # hover, error, disabled…


class FigmaMapping(BaseModel):
    requirement: FigmaRequirement
    implementation_status: CheckStatus = CheckStatus.FAIL
    evidence: str = ""
    gap: str = ""


class FigmaCheckResult(BaseModel):
    """Résultat de l'Agent 3 — Figma Requirements & UI Checker."""
    figma_link: str = ""
    pages_analyzed: list[str] = Field(default_factory=list)
    requirements: list[FigmaRequirement] = Field(default_factory=list)
    mappings: list[FigmaMapping] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.OK
    summary: str = ""


# ════════════════════════════════════════════
#  Agent 4 — Jira Validator Output
# ════════════════════════════════════════════

class AcceptanceCriterion(BaseModel):
    id: str = ""
    description: str
    status: CheckStatus = CheckStatus.FAIL
    evidence: str = ""
    notes: str = ""


class JiraValidationResult(BaseModel):
    """Résultat de l'Agent 4 — Jira Criteria Validator."""
    jira_key: str = ""
    jira_summary: str = ""
    jira_description: str = ""
    jira_status: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    definition_of_done: list[AcceptanceCriterion] = Field(default_factory=list)
    status: CheckStatus = CheckStatus.OK
    summary: str = ""
    recommended_verdict: Verdict = Verdict.BLOCKED


# ════════════════════════════════════════════
#  LLM-as-a-Judge Output
# ════════════════════════════════════════════

class MustFixItem(BaseModel):
    description: str
    location: str = ""  # fichier / classe / diagram / frame
    suggestion: str = ""
    severity: Severity = Severity.HIGH


class JudgeVerdict(BaseModel):
    """Verdict final du LLM-as-a-Judge."""
    verdict: Verdict = Verdict.BLOCKED
    confidence_score: int = Field(default=0, ge=0, le=100)
    justification: list[str] = Field(default_factory=list)  # 5-10 bullet points
    must_fix: list[MustFixItem] = Field(default_factory=list)


# ════════════════════════════════════════════
#  Validation Table Row (rapport final)
# ════════════════════════════════════════════

class ValidationRow(BaseModel):
    category: str  # "Jira AC", "UML", "Figma"
    item: str
    status: CheckStatus
    evidence: str = ""


# ════════════════════════════════════════════
#  Rapport final consolidé
# ════════════════════════════════════════════

class FinalReport(BaseModel):
    """Rapport final généré par l'Agent 5 / Orchestrateur."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pr_context: PRContext
    verdict: JudgeVerdict
    validation_table: list[ValidationRow] = Field(default_factory=list)
    code_analysis: Optional[CodeAnalysisResult] = None
    uml_check: Optional[UMLCheckResult] = None
    figma_check: Optional[FigmaCheckResult] = None
    jira_validation: Optional[JiraValidationResult] = None
    scrum_master_email_draft: str = ""
    dev_email_draft: str = ""
    jira_transition_payload: dict[str, Any] = Field(default_factory=dict)
    jira_comment: str = ""


# ════════════════════════════════════════════
#  Email payload
# ════════════════════════════════════════════

class EmailPayload(BaseModel):
    to: list[str]
    subject: str
    body_html: str
    body_text: str = ""
    attachments: list[str] = Field(default_factory=list)
