# 🛡️ PR-Guardian — Automated Pull Request Review System

> **Système multi-agents de revue automatique de Pull Requests** alimenté par LLM, intégrant GitHub, Jira, Figma et des diagrammes UML pour une validation complète et traçable.

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()
[![Tests](https://img.shields.io/badge/tests-46%20passing-brightgreen.svg)]()

---

## 📑 Table des matières

- [Vue d'ensemble](#-vue-densemble)
- [Architecture](#-architecture)
- [Workflow détaillé](#-workflow-détaillé)
- [Agents](#-agents)
- [Intégrations externes](#-intégrations-externes)
- [Modèles de données](#-modèles-de-données)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [Structure du projet](#-structure-du-projet)
- [Tests](#-tests)
- [Diagrammes UML](#-diagrammes-uml)

---

## 🎯 Vue d'ensemble

**PR-Guardian** est un orchestrateur multi-agents qui automatise la revue de Pull Requests. Il analyse chaque PR sous 4 angles complémentaires, puis un **LLM-as-a-Judge** rend un verdict final (`PASS`, `FAIL` ou `BLOCKED`) accompagné d'une justification détaillée et d'actions automatiques.

### Fonctionnalités clés

| Fonctionnalité | Description |
|---|---|
| 🔍 **Analyse de code** | Détection de features, endpoints, classes, tests, points sensibles |
| 📐 **Cohérence UML ↔ Code** | Vérification que les diagrammes PlantUML reflètent le code réel |
| 🎨 **Conformité Figma ↔ Code** | Comparaison des maquettes Figma avec l'implémentation |
| ✅ **Validation Jira AC/DoD** | Vérification des critères d'acceptation et de la Definition of Done |
| ⚖️ **Verdict LLM-as-a-Judge** | Décision finale basée sur l'ensemble des preuves collectées |
| 📧 **Notifications email** | Email au rapporteur Jira (PASS) ou au développeur (FAIL) |
| 💬 **Commentaire PR** | Rapport structuré posté directement sur la PR GitHub |
| 📋 **Transition Jira** | Avancement automatique du ticket (In Review → Done / Needs Fix) |

---

## 🏗️ Architecture

PR-Guardian suit une architecture **orchestrateur + agents spécialisés** :

```
┌─────────────────────────────────────────────────────────────────┐
│                      Points d'entrée                            │
│  ┌──────────────────┐          ┌──────────────────────────┐     │
│  │  CLI (__main__.py)│          │  Webhook (FastAPI Server) │     │
│  │  click + rich     │          │  POST /webhook/github     │     │
│  └────────┬─────────┘          └────────────┬─────────────┘     │
│           └──────────────┬─────────────────┘                    │
└──────────────────────────┼──────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ⚙️  ORCHESTRATOR                               │
│                    review_pr()                                    │
│                                                                  │
│   Étape 0 ─── Récupération contextuelle (Jira key, Figma, UML)  │
│   Étape 1 ─── Exécution parallèle Agents 1→4 (asyncio.gather)   │
│               puis re-exécution 2→4 avec résultats code          │
│   Étape 2 ─── LLM-as-a-Judge (dossier de preuves)               │
│   Étape 3 ─── Reporter + Actions (email, Jira, commentaire PR)  │
└───────┬──────────┬──────────┬──────────┬────────────────────────┘
        │          │          │          │
        ▼          ▼          ▼          ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│  Agent 1 ││  Agent 2 ││  Agent 3 ││  Agent 4 │
│   Code   ││   UML    ││  Figma   ││   Jira   │
│ Analyst  ││ Checker  ││ Checker  ││Validator │
└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
     │           │           │           │
     ▼           ▼           ▼           ▼
┌──────────┐┌──────────┐┌──────────┐┌──────────┐
│  GitHub  ││  GitHub  ││  Figma   ││   Jira   │
│  Client  ││  Client  ││  Client  ││  Client  │
└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘
     │           │           │           │
     ▼           ▼           ▼           ▼
  GitHub API   GitHub API  Figma API  Jira Cloud
                                      REST v3
```

Tous les agents utilisent **Cohere LLM** (`command-a-03-2025`) pour l'analyse intelligente.

---

## 🔄 Workflow détaillé

### Étape 0 — Récupération contextuelle

L'Orchestrator construit un `PRContext` enrichi :

1. **GitHub** : récupère le diff, le titre, la description, l'auteur de la PR
2. **Jira key** : extraite du titre/description de la PR (ex: `PROJ-123`)
3. **Rapporteur Jira** : email et nom du reporter (pour notification PASS)
4. **Lien Figma** : recherché dans le repo GitHub et dans le ticket Jira
5. **Fichiers UML** : détection des `.puml` dans le repo
6. **Transition Jira → In Review** : le ticket passe en revue

### Étape 1 — Agents parallèles

Les 4 agents s'exécutent en parallèle via `asyncio.gather()` :

| Agent | Entrée | Sortie | Intégration |
|-------|--------|--------|-------------|
| **Code Analyst** | Diff PR | `CodeAnalysisResult` | GitHub API |
| **UML Checker** | Fichiers `.puml` + diff | `UMLCheckResult` | GitHub API + LLM |
| **Figma Checker** | Lien Figma + diff | `FigmaCheckResult` | Figma API + LLM |
| **Jira Validator** | Jira key + diff | `JiraValidationResult` | Jira API + LLM |

Puis les agents 2, 3, 4 sont **re-exécutés** avec les résultats de l'Agent 1 pour une analyse croisée plus fine.

### Étape 2 — LLM-as-a-Judge

Le **Judge** reçoit un dossier de preuves consolidé (les 4 résultats) et rend :

- Un **verdict** : `PASS`, `FAIL` ou `BLOCKED`
- Un **score de confiance** (0-100)
- Une **justification** (5-10 points)
- Une liste de **must-fix items** avec sévérité et suggestions

### Étape 3 — Reporter & Actions

Le **Reporter** génère le rapport final, puis l'Orchestrator exécute :

| Verdict | Email | Jira | PR |
|---------|-------|------|----|
| **PASS** | 📧 Envoyé au rapporteur Jira (Scrum Master) | Transition → Done | ✅ Commentaire PASS |
| **FAIL** | 📧 Envoyé au développeur | Transition → Needs Fix | ❌ Commentaire FAIL + must-fix |
| **BLOCKED** | — | Reste en état | 🚫 Commentaire BLOCKED |

---

## 🤖 Agents

Tous les agents héritent de `BaseAgent` (classe abstraite) et implémentent `async run(context, **kwargs)`.

### Agent 1 — Code Analyst (`code_analyst.py`)

Analyse le diff de la PR via GitHub et le LLM :
- Fichiers modifiés, ajouts/suppressions
- Features détectées, endpoints, classes/méthodes touchées
- Migrations, tests ajoutés/modifiés
- Points sensibles (sécurité, performance)

### Agent 2 — UML Checker (`uml_checker.py`)

Vérifie la cohérence entre les diagrammes PlantUML et le code :
- Parse les fichiers `.puml` avec `plantuml_parser`
- Compare entités/relations avec les classes du code
- Détecte les mismatches (classe manquante, relation absente)

### Agent 3 — Figma Checker (`figma_checker.py`)

Vérifie la conformité design ↔ implémentation :
- Récupère les frames/composants depuis l'API Figma
- Mappe chaque exigence Figma au code via LLM
- Fallback : si un node spécifique est inaccessible, charge le fichier complet

### Agent 4 — Jira Validator (`jira_validator.py`)

Valide les critères d'acceptation et la DoD :
- Récupère les champs du ticket Jira (AC, DoD, description)
- Évalue chaque critère contre le diff via LLM
- Recommande un verdict préliminaire

### Agent J — Judge (`judge.py`)

LLM-as-a-Judge — décision finale :
- Reçoit les 4 résultats comme dossier de preuves
- Analyse globale avec pondération
- Produit le verdict, la confiance et les must-fix items

### Agent 5 — Reporter (`reporter.py`)

Génère les sorties finales :
- Table de validation (catégorie, item, statut, preuve)
- Email HTML pour le Scrum Master (PASS) ou le développeur (FAIL)
- Payload de transition Jira
- Rapport structuré

---

## 🔌 Intégrations externes

| Service | Client | Utilisation |
|---------|--------|-------------|
| **GitHub** | `github_client.py` (PyGithub) | Diff, fichiers, commentaires PR, extraction Jira key |
| **Jira Cloud** | `jira_client.py` (REST API v3) | Champs ticket, transitions, commentaires, reporter |
| **Figma** | `figma_client.py` (REST API) | Métadonnées fichier, extraction frames/composants, cache |
| **Cohere LLM** | Direct API | Analyse qualité, cohérence, conformité, verdict |
| **Email (SMTP/SendGrid)** | `email_client.py` | Notifications PASS (rapporteur) / FAIL (développeur) |

---

## 📦 Modèles de données

Tous les modèles sont définis dans `models.py` avec **Pydantic v2** :

```
PRContext                  ← Contexte de la PR (entrée)
├── CodeAnalysisResult     ← Sortie Agent 1
│   └── ModifiedFile
├── UMLCheckResult         ← Sortie Agent 2
│   ├── UMLDiagram
│   │   ├── UMLEntity
│   │   └── UMLRelation
│   └── UMLMismatch
├── FigmaCheckResult       ← Sortie Agent 3
│   ├── FigmaRequirement
│   └── FigmaMapping
├── JiraValidationResult   ← Sortie Agent 4
│   └── AcceptanceCriterion
├── JudgeVerdict           ← Sortie Judge
│   └── MustFixItem
└── FinalReport            ← Rapport consolidé
    ├── ValidationRow
    └── EmailPayload
```

### Enums

| Enum | Valeurs |
|------|---------|
| `Verdict` | `PASS`, `FAIL`, `BLOCKED` |
| `CheckStatus` | `OK`, `PASS`, `FAIL`, `PARTIAL`, `MISMATCH`, `BLOCKED`, `N/A` |
| `Severity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO` |

---

## 🚀 Installation

### Prérequis

- Python 3.10+
- Comptes : GitHub, Jira Cloud, Figma, Cohere

### Étapes

```bash
# Cloner le repo
git clone <repo-url>
cd Team7

# Créer l'environnement virtuel
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Installer les dépendances
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Créer un fichier `.env` à la racine du projet (voir `.env.example`) :

```env
# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# Jira
JIRA_BASE_URL=https://your-org.atlassian.net
JIRA_USER_EMAIL=user@example.com
JIRA_API_TOKEN=your-jira-token
JIRA_DONE_TRANSITION_ID=41
JIRA_IN_REVIEW_TRANSITION_ID=31
JIRA_NEEDS_FIX_TRANSITION_ID=21

# Figma
FIGMA_ACCESS_TOKEN=figd_xxxxxxxxxxxxxxxxxxxx

# Cohere LLM
COHERE_API_KEY=your-cohere-key
COHERE_MODEL=command-a-03-2025

# Email (SMTP Gmail)
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=PR-Guardian <your-email@gmail.com>

# Général
LOG_LEVEL=INFO
LANGUAGE=fr
```

La configuration est gérée par **pydantic-settings** dans `config.py`. Toutes les variables sont optionnelles — les intégrations non configurées sont simplement ignorées.

---

## 💻 Utilisation

### Mode CLI

```bash
# Revue d'une PR
python -m pr_guardian --repo owner/repo --pr 42

# Sortie JSON brute
python -m pr_guardian --repo owner/repo --pr 42 --json-output

# Spécifier une branche
python -m pr_guardian --repo owner/repo --pr 42 --branch feature/my-feature
```

### Mode Webhook (serveur)

```bash
# Lancer le serveur FastAPI
python -m pr_guardian --server --port 8080
```

Le serveur écoute les webhooks GitHub sur `POST /webhook/github` et déclenche automatiquement une revue lorsqu'une PR est ouverte, synchronisée ou réouverte.

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/health` | GET | Health check |
| `/webhook/github` | POST | Réception des événements GitHub |

### Simulation

```bash
# Simuler un pipeline complet
python scripts/simulate_pipeline.py
```

---

## 📁 Structure du projet

```
Team7/
├── pr_guardian/
│   ├── __init__.py
│   ├── __main__.py          # Point d'entrée CLI & Server
│   ├── config.py             # Settings (pydantic-settings)
│   ├── models.py             # Tous les modèles Pydantic
│   ├── orchestrator.py       # Orchestrateur principal (4 étapes)
│   ├── webhook.py            # Serveur FastAPI webhook
│   ├── agents/
│   │   ├── base_agent.py     # Classe abstraite BaseAgent
│   │   ├── code_analyst.py   # Agent 1 — Analyse du code
│   │   ├── uml_checker.py    # Agent 2 — Cohérence UML
│   │   ├── figma_checker.py  # Agent 3 — Conformité Figma
│   │   ├── jira_validator.py # Agent 4 — Validation Jira
│   │   ├── judge.py          # Agent J — Verdict final
│   │   └── reporter.py       # Agent 5 — Rapports & emails
│   ├── integrations/
│   │   ├── email_client.py   # SMTP / SendGrid
│   │   ├── figma_client.py   # Figma REST API
│   │   ├── github_client.py  # PyGithub wrapper
│   │   └── jira_client.py    # Jira REST API v3
│   ├── parsers/
│   │   ├── diff_parser.py    # Parse unified diffs
│   │   └── plantuml_parser.py# Parse .puml files
│   ├── templates/
│   │   ├── email_pass.html   # Template email PASS
│   │   ├── email_fail.html   # Template email FAIL
│   │   ├── report_dev.md     # Rapport développeur
│   │   └── report_scrum.md   # Rapport Scrum Master
│   └── utils/
│       ├── helpers.py        # Fonctions utilitaires
│       └── logger.py         # Configuration logging (Rich)
├── tests/
│   ├── conftest.py           # Fixtures pytest
│   ├── test_orchestrator.py  # Tests Orchestrator
│   ├── fixtures/             # Données de test
│   │   ├── sample_diagram.puml
│   │   ├── sample_diff.patch
│   │   └── sample_jira_response.json
│   └── test_agents/          # Tests unitaires agents
│       ├── test_code_analyst.py
│       ├── test_figma_checker.py
│       ├── test_jira_validator.py
│       ├── test_judge.py
│       └── test_uml_checker.py
├── UMLdiagrams/              # Diagrammes PlantUML (.puml + .png)
├── docs/                     # Documentation additionnelle
├── scripts/                  # Scripts utilitaires
├── .env                      # Variables d'environnement (non versionné)
├── .env.example              # Template de configuration
├── pyproject.toml            # Metadata projet & config pytest/ruff
├── requirements.txt          # Dépendances Python
└── README.md                 # Ce fichier
```

---

## 🧪 Tests

```bash
# Lancer tous les tests
pytest

# Avec verbosité
pytest -v

# Un fichier spécifique
pytest tests/test_agents/test_judge.py -v
```

**46 tests** couvrent les agents, l'orchestrateur, les parsers et les intégrations. Le mode async est géré par `pytest-asyncio` (mode `auto`).

---

## 📐 Diagrammes UML

Les diagrammes du projet sont dans le dossier `UMLdiagrams/` au format PlantUML :

| # | Diagramme | Fichier |
|---|-----------|---------|
| 1 | Classes — Agents & Orchestrateur | `01_class_diagram_agents.puml` |
| 2 | Classes — Modèles de données | `02_class_diagram_models.puml` |
| 3 | Classes — Intégrations & Parseurs | `03_class_diagram_integrations.puml` |
| 4 | Séquence — Revue CLI complète | `04_sequence_diagram_review.puml` |
| 5 | Composants — Architecture | `05_component_diagram.puml` |
| 6 | Séquence — Webhook GitHub | `06_sequence_diagram_webhook.puml` |
| 7 | Activité — Décision verdict | `07_activity_diagram_verdict.puml` |
| 8 | Cas d'utilisation | `08_usecase_diagram.puml` |

Générer les PNG :

```bash
plantuml -tpng UMLdiagrams/*.puml
```

---

## 🔧 Stack technique

| Catégorie | Technologies |
|-----------|-------------|
| **Langage** | Python 3.10+ |
| **Framework CLI** | Click + Rich |
| **Framework Web** | FastAPI + Uvicorn |
| **Modèles** | Pydantic v2 + pydantic-settings |
| **LLM** | Cohere (`command-a-03-2025`) |
| **GitHub** | PyGithub |
| **Jira** | REST API v3 (requests) |
| **Figma** | REST API (httpx) |
| **Email** | SMTP (Gmail) / SendGrid |
| **Tests** | pytest + pytest-asyncio + pytest-mock + respx |
| **Linting** | Ruff |

---

*PR-Guardian Orchestrator — Team7*
