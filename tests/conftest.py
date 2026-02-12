"""
Fixtures pytest — PR-Guardian.
"""

import pytest

from pr_guardian.models import (
    AcceptanceCriterion,
    CheckStatus,
    CodeAnalysisResult,
    FigmaCheckResult,
    FigmaMapping,
    FigmaRequirement,
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
    Verdict,
)


@pytest.fixture
def sample_pr_context() -> PRContext:
    """Contexte PR de test."""
    return PRContext(
        repo="Team7/mon-projet",
        pr_number=42,
        branch="feature/user-auth",
        pr_title="[PROJ-123] Ajout authentification utilisateur",
        pr_description="Implémente le login et le signup selon la maquette Figma.",
        pr_author="dev-jean",
        pr_author_email="jean@team7.dev",
        jira_key="PROJ-123",
        figma_link="https://www.figma.com/file/ABC123/Design-System",
        uml_files=["docs/diagrams/auth.puml"],
    )


@pytest.fixture
def sample_code_analysis() -> CodeAnalysisResult:
    """Résultat d'analyse de code de test."""
    return CodeAnalysisResult(
        summary="5 fichiers modifiés (+120 / -30)",
        files_modified=[
            ModifiedFile(
                filename="src/auth/login.py",
                status="added",
                additions=50,
                deletions=0,
                language="python",
            ),
            ModifiedFile(
                filename="src/auth/signup.py",
                status="added",
                additions=40,
                deletions=0,
                language="python",
            ),
            ModifiedFile(
                filename="tests/test_auth.py",
                status="added",
                additions=30,
                deletions=0,
                language="python",
            ),
        ],
        features_detected=["Nouveau fichier : src/auth/login.py", "Nouveau fichier : src/auth/signup.py"],
        endpoints=["/api/auth/login", "/api/auth/signup"],
        classes_touched=["LoginController", "SignupController", "AuthService"],
        methods_touched=["authenticate", "register", "validate_token"],
        tests_added=["tests/test_auth.py"],
        test_coverage_info="Tests : 1 fichier(s) test pour 2 source(s) (50%)",
        sensitive_points=["⚠️ Fichier sensible : src/auth/login.py"],
        raw_diff_stats={"total_files": 5, "total_additions": 120, "total_deletions": 30},
    )


@pytest.fixture
def sample_uml_check() -> UMLCheckResult:
    """Résultat de vérification UML de test."""
    return UMLCheckResult(
        diagrams_found=[
            UMLDiagram(
                filepath="docs/diagrams/auth.puml",
                diagram_type="class",
                entities=[
                    UMLEntity(name="AuthService", entity_type="class", methods=["authenticate", "register"]),
                    UMLEntity(name="User", entity_type="class", attributes=["id", "email", "password"]),
                ],
                relations=[
                    UMLRelation(source="AuthService", target="User", relation_type="association"),
                ],
            )
        ],
        mismatches=[],
        status=CheckStatus.OK,
        summary="1 diagramme(s) analysé(s), 0 écart(s) détecté(s).",
    )


@pytest.fixture
def sample_figma_check() -> FigmaCheckResult:
    """Résultat de vérification Figma de test."""
    return FigmaCheckResult(
        figma_link="https://www.figma.com/file/ABC123/Design-System",
        pages_analyzed=["Auth Screens"],
        requirements=[
            FigmaRequirement(
                frame_id="1:100",
                frame_name="Login Form",
                page_name="Auth Screens",
                components=["TextInput", "Button", "ErrorMessage"],
                texts=["Email", "Mot de passe", "Connexion", "Email invalide"],
                states=["default", "error", "loading"],
            ),
        ],
        mappings=[
            FigmaMapping(
                requirement=FigmaRequirement(
                    frame_id="1:100",
                    frame_name="Login Form",
                    page_name="Auth Screens",
                ),
                implementation_status=CheckStatus.OK,
                evidence="Correspondance(s) trouvée(s) : login, logincontroller",
            ),
        ],
        status=CheckStatus.OK,
        summary="1 exigence(s) Figma identifiée(s) : 1 conforme(s), 0 écart(s).",
    )


@pytest.fixture
def sample_jira_validation() -> JiraValidationResult:
    """Résultat de validation Jira de test."""
    return JiraValidationResult(
        jira_key="PROJ-123",
        jira_summary="Implémenter l'authentification utilisateur",
        jira_description="En tant qu'utilisateur, je veux pouvoir me connecter...",
        jira_status="In Progress",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-1",
                description="L'utilisateur peut se connecter avec email/mot de passe",
                status=CheckStatus.PASS,
                evidence="Endpoint trouvé : /api/auth/login",
            ),
            AcceptanceCriterion(
                id="AC-2",
                description="L'utilisateur peut s'inscrire avec email/mot de passe",
                status=CheckStatus.PASS,
                evidence="Endpoint trouvé : /api/auth/signup",
            ),
        ],
        definition_of_done=[
            AcceptanceCriterion(
                id="DoD-1",
                description="Tests unitaires ajoutés",
                status=CheckStatus.PASS,
                evidence="Tests : 1 ajouté(s)",
            ),
        ],
        status=CheckStatus.OK,
        summary="Issue PROJ-123 — 3 critère(s) évalué(s) : 3 PASS.",
        recommended_verdict=Verdict.PASS,
    )


@pytest.fixture
def sample_judge_verdict_pass() -> JudgeVerdict:
    """Verdict PASS de test."""
    return JudgeVerdict(
        verdict=Verdict.PASS,
        confidence_score=85,
        justification=[
            "Tous les acceptance criteria sont satisfaits ✅",
            "UML cohérent avec l'implémentation ✅",
            "Figma conforme sur les éléments exigés ✅",
            "Tests unitaires présents ✅",
        ],
        must_fix=[],
    )


@pytest.fixture
def sample_judge_verdict_fail() -> JudgeVerdict:
    """Verdict FAIL de test."""
    return JudgeVerdict(
        verdict=Verdict.FAIL,
        confidence_score=35,
        justification=[
            "AC-2 non satisfait : inscription manquante ❌",
            "UML : classe SignupController absente ❌",
            "Figma : frame 'Signup Form' non implémenté ❌",
        ],
        must_fix=[
            MustFixItem(
                description="AC-2 : L'utilisateur peut s'inscrire — non implémenté",
                location="Jira PROJ-123",
                suggestion="Implémenter le endpoint /api/auth/signup",
                severity=Severity.CRITICAL,
            ),
            MustFixItem(
                description="Classe SignupController absente de l'UML",
                location="docs/diagrams/auth.puml",
                suggestion="Ajouter SignupController au diagramme de classes",
                severity=Severity.MEDIUM,
            ),
        ],
    )


@pytest.fixture
def sample_puml_content() -> str:
    """Contenu PlantUML de test."""
    return """
@startuml
class AuthService {
    +authenticate(email, password)
    +register(email, password)
    -validateToken(token)
}

class User {
    -id: int
    -email: string
    -password: string
    +checkPassword(password): bool
}

class LoginController {
    +login(request)
}

class SignupController {
    +signup(request)
}

AuthService --> User : uses
LoginController --> AuthService : delegates
SignupController --> AuthService : delegates
@enduml
"""


@pytest.fixture
def sample_diff_patch() -> str:
    """Patch Git de test."""
    return """
@@ -0,0 +1,25 @@
+from fastapi import APIRouter, HTTPException
+from .service import AuthService
+
+router = APIRouter()
+auth_service = AuthService()
+
+@router.post("/api/auth/login")
+async def login(request: LoginRequest):
+    user = auth_service.authenticate(request.email, request.password)
+    if not user:
+        raise HTTPException(status_code=401, detail="Invalid credentials")
+    return {"token": user.token}
+
+@router.post("/api/auth/signup")
+async def signup(request: SignupRequest):
+    user = auth_service.register(request.email, request.password)
+    return {"user_id": user.id}
+
+class LoginRequest:
+    email: str
+    password: str
+
+class SignupRequest:
+    email: str
+    password: str
"""
