# 🚀 PR-Guardian — Guide de Démarrage

> De zéro à votre première revue automatique de PR en 10 minutes.

---

## Table des Matières

1. [Prérequis](#1--prérequis)
2. [Installation](#2--installation)
3. [Configuration Rapide](#3--configuration-rapide)
4. [Première Revue (Mode CLI)](#4--première-revue-mode-cli)
5. [Mode Serveur Webhook](#5--mode-serveur-webhook)
6. [Configurer le Webhook GitHub](#6--configurer-le-webhook-github)
7. [Comprendre les Résultats](#7--comprendre-les-résultats)
8. [Commandes Utiles](#8--commandes-utiles)
9. [Lancer les Tests](#9--lancer-les-tests)
10. [Architecture du Projet](#10--architecture-du-projet)
11. [FAQ](#11--faq)

---

## 1 — Prérequis

| Outil         | Version minimale | Vérifier                          |
|:--------------|:-----------------|:----------------------------------|
| **Python**    | 3.10+            | `python --version`                |
| **pip**       | 23+              | `pip --version`                   |
| **Git**       | 2.30+            | `git --version`                   |

### Clés API nécessaires

- ✅ **GitHub Personal Access Token** (obligatoire)
- ⚪ Jira API Token (optionnel)
- ⚪ Figma Access Token (optionnel)
- ⚪ Cohere API Key (optionnel — fallback heuristique sans)
- ⚪ Email SMTP ou SendGrid (optionnel)

> 📖 Voir [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) pour obtenir chaque clé.

---

## 2 — Installation

### 2.1 — Cloner le projet

```bash
cd /home/malek/Desktop
git clone <votre-repo-url> Team7
cd Team7
```

> Si le projet est déjà cloné, passez à l'étape suivante.

### 2.2 — Créer l'environnement virtuel

```bash
python -m venv .venv
```

### 2.3 — Activer l'environnement

```bash
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (CMD)
.venv\Scripts\activate.bat
```

> Vous devriez voir `(.venv)` au début de votre prompt.

### 2.4 — Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2.5 — Vérifier l'installation

```bash
python -m pr_guardian --help
```

Sortie attendue :
```
Usage: python -m pr_guardian [OPTIONS] COMMAND [ARGS]...

🛡️ PR-Guardian Orchestrator — Revue automatique de Pull Requests.

Options:
  -r, --repo TEXT         Repository (owner/repo)
  -p, --pr INTEGER        Numéro de la PR
  -b, --branch TEXT       Branche source (optionnel)
  --server                Lancer le serveur webhook
  --port INTEGER          Port du serveur webhook
  --json-output           Sortie JSON brute
  --help                  Show this message and exit.
```

---

## 3 — Configuration Rapide

### 3.1 — Créer le fichier `.env`

```bash
cp .env.example .env
```

### 3.2 — Éditer le `.env`

Ouvrez `.env` dans votre éditeur et remplissez **au minimum** :

```dotenv
GITHUB_TOKEN=ghp_votre_token_github_ici
```

### 3.3 — Vérifier

```bash
python -c "
from pr_guardian.config import get_settings
s = get_settings()
print('GitHub configuré :', '✅' if s.github_configured else '❌')
print('Jira configuré   :', '✅' if s.jira_configured else '⚪')
print('Figma configuré  :', '✅' if s.figma_configured else '⚪')
print('Cohere configuré :', '✅' if s.llm_configured else '⚪')
print('Email configuré  :', '✅' if s.email_configured else '⚪')
"
```

> 📖 Pour la configuration complète de chaque service, voir [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md).

---

## 4 — Première Revue (Mode CLI)

### 4.1 — Syntaxe de base

```bash
python -m pr_guardian --repo <owner/repo> --pr <numéro>
```

### 4.2 — Exemple concret

```bash
# Analyser la PR #42 du repo "team7/mon-projet"
python -m pr_guardian --repo team7/mon-projet --pr 42
```

### 4.3 — Avec branche spécifique

```bash
python -m pr_guardian --repo team7/mon-projet --pr 42 --branch feature/login-page
```

### 4.4 — Sortie JSON (pour intégration CI/CD)

```bash
python -m pr_guardian --repo team7/mon-projet --pr 42 --json-output
```

### 4.5 — Sortie attendue

```
╭──────────────────────────────────────────────╮
│ 🛡️ PR-Guardian Orchestrator                   │
│ Revue de : team7/mon-projet #42              │
╰──────────────────────────────────────────────╯

📋 Étape 0 — Récupération du contexte...
  • Jira Key    : PROJ-42
  • Figma URL   : https://figma.com/file/xxx
  • Fichiers UML: 1 trouvé(s)

⚡ Étape 1 — Exécution parallèle des agents...
  ✅ Agent 1 — Code Analyst         (Score: 0.85)
  ✅ Agent 2 — UML Checker          (Score: 0.90)
  ✅ Agent 3 — Figma Checker        (Score: 0.75)
  ✅ Agent 4 — Jira Validator       (Score: 0.80)

⚖️ Étape 2 — LLM-as-a-Judge...
  Verdict : ✅ PASS

📧 Étape 3 — Actions...
  • Commentaire PR posté ✅
  • Email envoyé ✅
  • Transition Jira → Done ✅

╭──────────────────────────────────────────────╮
│  VERDICT FINAL : ✅ PASS                      │
│  Confiance     : 0.83                         │
╰──────────────────────────────────────────────╯
```

---

## 5 — Mode Serveur Webhook

Le mode serveur écoute les événements GitHub et lance automatiquement une revue à chaque PR ouverte/mise à jour.

### 5.1 — Lancer le serveur

```bash
python -m pr_guardian --server --port 8080
```

Sortie :
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 5.2 — Vérifier que le serveur fonctionne

```bash
curl http://localhost:8080/health
```

Réponse :
```json
{"status": "ok", "service": "pr-guardian"}
```

### 5.3 — Tester avec un faux webhook

```bash
curl -X POST http://localhost:8080/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -d '{
    "action": "opened",
    "pull_request": {
      "number": 42,
      "head": { "ref": "feature/test" }
    },
    "repository": {
      "full_name": "team7/mon-projet"
    }
  }'
```

Réponse :
```json
{
  "message": "Revue déclenchée.",
  "repo": "team7/mon-projet",
  "pr": 42,
  "branch": "feature/test"
}
```

---

## 6 — Configurer le Webhook GitHub

Pour que GitHub envoie automatiquement les événements PR à votre serveur :

### 6.1 — Exposer votre serveur (développement)

Si vous êtes en local, utilisez **ngrok** pour créer un tunnel :

```bash
# Installer ngrok
# https://ngrok.com/download
ngrok http 8080
```

Vous obtiendrez une URL publique comme : `https://abc123.ngrok-free.app`

### 6.2 — Configurer dans GitHub

1. Allez dans votre repo GitHub → **Settings** → **Webhooks**
2. Cliquez **"Add webhook"**
3. Configurez :

| Champ            | Valeur                                           |
|:-----------------|:-------------------------------------------------|
| **Payload URL**  | `https://abc123.ngrok-free.app/webhook/github`   |
| **Content type** | `application/json`                               |
| **Secret**       | *(optionnel — non implémenté pour le moment)*    |
| **Events**       | Sélectionnez **"Pull requests"** uniquement      |

4. Cliquez **"Add webhook"**

### 6.3 — Production (VPS / Cloud)

Pour un déploiement en production :

```bash
# Avec systemd (Linux)
# Créer /etc/systemd/system/pr-guardian.service

[Unit]
Description=PR-Guardian Orchestrator Webhook Server
After=network.target

[Service]
Type=simple
User=deploy
WorkingDirectory=/opt/pr-guardian
EnvironmentFile=/opt/pr-guardian/.env
ExecStart=/opt/pr-guardian/.venv/bin/python -m pr_guardian --server --port 8080
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pr-guardian
sudo systemctl start pr-guardian
```

Puis mettez un **reverse proxy** (Nginx/Caddy) devant avec HTTPS.

---

## 7 — Comprendre les Résultats

### Les 3 verdicts possibles

| Verdict      | Signification | Action automatique                    |
|:-------------|:--------------|:--------------------------------------|
| ✅ **PASS**    | La PR est conforme | Jira → Done, Email de succès       |
| ❌ **FAIL**    | Des problèmes détectés | Jira → Needs Fix, Email avec détails |
| 🟡 **BLOCKED** | Impossible de statuer | Pas de transition, Email d'alerte   |

### Score de confiance

Chaque agent retourne un score entre 0 et 1 :

- **0.0 – 0.3** : Problèmes majeurs détectés
- **0.3 – 0.7** : Conformité partielle
- **0.7 – 1.0** : Bonne conformité

### Rapport détaillé

Le rapport final contient :
- **Tableau de validation** : chaque critère vérifié avec son statut
- **Must-fix items** : liste des points à corriger obligatoirement
- **Résumé par agent** : ce que chaque agent a trouvé
- **Justification du Judge** : pourquoi le verdict a été rendu

### Sortie JSON

Avec `--json-output`, le rapport complet est en JSON :

```json
{
  "verdict": "PASS",
  "confidence": 0.83,
  "judge_reasoning": "Tous les critères principaux sont satisfaits...",
  "must_fix": [],
  "agent_results": {
    "code_analyst": { "score": 0.85, "details": "..." },
    "uml_checker": { "score": 0.90, "details": "..." },
    "figma_checker": { "score": 0.75, "details": "..." },
    "jira_validator": { "score": 0.80, "details": "..." }
  },
  "timestamp": "2026-02-11T10:30:00Z"
}
```

---

## 8 — Commandes Utiles

### Revue CLI

```bash
# Revue simple
python -m pr_guardian --repo owner/repo --pr 42

# Avec branche
python -m pr_guardian --repo owner/repo --pr 42 --branch feature/xyz

# Sortie JSON
python -m pr_guardian --repo owner/repo --pr 42 --json-output

# Debug verbose
LOG_LEVEL=DEBUG python -m pr_guardian --repo owner/repo --pr 42
```

### Serveur Webhook

```bash
# Port par défaut (8080)
python -m pr_guardian --server

# Port personnalisé
python -m pr_guardian --server --port 3000
```

### Vérification santé

```bash
# Config
python -c "from pr_guardian.config import get_settings; s = get_settings(); print(s.model_dump())"

# Health check serveur
curl http://localhost:8080/health
```

---

## 9 — Lancer les Tests

### Tous les tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

### Un fichier spécifique

```bash
python -m pytest tests/test_agents/test_code_analyst.py -v
```

### Avec couverture

```bash
pip install pytest-cov
python -m pytest tests/ -v --cov=pr_guardian --cov-report=term-missing
```

### Tests stricts (warnings = erreurs)

```bash
python -m pytest tests/ -v -W error::DeprecationWarning
```

> **État actuel** : 46/46 tests passent ✅

---

## 10 — Architecture du Projet

```
Team7/
├── .env.example              # Template de configuration
├── .env                      # Votre configuration (NE PAS COMMITTER)
├── .gitignore
├── requirements.txt
├── pyproject.toml
├── README.md
├── docs/
│   ├── CONFIGURATION_GUIDE.md  # Guide détaillé des API keys
│   └── GETTING_STARTED.md      # Ce fichier
├── pr_guardian/
│   ├── __init__.py
│   ├── __main__.py           # 🚀 Point d'entrée (CLI + Webhook)
│   ├── config.py             # ⚙️ Configuration centralisée
│   ├── models.py             # 📦 Modèles de données
│   ├── orchestrator.py       # 🎯 Chef d'orchestre principal
│   ├── webhook.py            # 🌐 Serveur FastAPI
│   ├── integrations/
│   │   ├── github_client.py  # 🐙 API GitHub
│   │   ├── jira_client.py    # 📋 API Jira
│   │   ├── figma_client.py   # 🎨 API Figma
│   │   └── email_client.py   # 📧 Envoi d'emails
│   ├── agents/
│   │   ├── base_agent.py     # 🏗️ Classe abstraite Agent
│   │   ├── code_analyst.py   # Agent 1 — Analyse de code
│   │   ├── uml_checker.py    # Agent 2 — Vérification UML
│   │   ├── figma_checker.py  # Agent 3 — Conformité UI
│   │   ├── jira_validator.py # Agent 4 — Validation Jira
│   │   ├── reporter.py       # Agent 5 — Rapports & Notifications
│   │   └── judge.py          # ⚖️ LLM-as-a-Judge
│   ├── parsers/
│   │   ├── plantuml_parser.py
│   │   └── diff_parser.py
│   ├── templates/
│   │   ├── report_scrum.md
│   │   ├── report_dev.md
│   │   ├── email_pass.html
│   │   └── email_fail.html
│   └── utils/
│       ├── logger.py
│       └── helpers.py
└── tests/
    ├── conftest.py
    ├── test_orchestrator.py
    └── test_agents/
        ├── test_code_analyst.py
        ├── test_uml_checker.py
        ├── test_figma_checker.py
        ├── test_jira_validator.py
        └── test_judge.py
```

### Flux d'exécution

```
PR ouverte sur GitHub
        │
        ▼
┌───────────────────┐
│  CLI ou Webhook   │ ← Point d'entrée
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│   Orchestrator    │ ← Chef d'orchestre
└───────┬───────────┘
        │
        ├──→ Étape 0 : Récupérer contexte (Jira key, Figma URL, UML files)
        │
        ├──→ Étape 1 : Exécution parallèle
        │       ├── Agent 1 — Code Analyst    (analyse diff + fichiers)
        │       ├── Agent 2 — UML Checker     (PlantUML vs code)
        │       ├── Agent 3 — Figma Checker   (maquettes vs code)
        │       └── Agent 4 — Jira Validator  (AC/DoD vs implémentation)
        │
        ├──→ Étape 2 : LLM-as-a-Judge
        │       └── Agrège les résultats → Verdict PASS/FAIL/BLOCKED
        │
        └──→ Étape 3 : Actions
                ├── Poster commentaire sur la PR
                ├── Envoyer email (Scrum Master + Dev)
                └── Transitionner le ticket Jira
```

---

## 11 — FAQ

### Q: Que se passe-t-il si je n'ai pas de clé Jira ?

L'agent Jira Validator sera simplement **ignoré**. Le Judge ne tiendra pas compte de la validation Jira dans son verdict. Le reste fonctionne normalement.

### Q: Puis-je utiliser un LLM autre que Cohere ?

Actuellement, seul Cohere est supporté nativement. Cependant, vous pouvez modifier `pr_guardian/agents/judge.py` pour utiliser un autre provider (OpenAI, Anthropic, Google Gemini, Ollama, etc.) en remplaçant l'appel à l'API Cohere par le SDK de votre choix.

### Q: Comment ajouter un nouveau type de vérification ?

1. Créez un nouvel agent dans `pr_guardian/agents/` qui hérite de `BaseAgent`
2. Implémentez la méthode `async def run(self, context, **kwargs)`
3. Ajoutez-le dans `orchestrator.py` dans la liste des agents

### Q: Les tests ont-ils besoin de vrais tokens API ?

**Non.** Tous les 46 tests utilisent des **mocks** — aucun appel API réel n'est fait. Vous pouvez lancer les tests sans aucune configuration.

### Q: Comment débugger un problème ?

```bash
# 1. Activer le mode debug
LOG_LEVEL=DEBUG python -m pr_guardian --repo owner/repo --pr 42

# 2. Vérifier la config
python -c "from pr_guardian.config import get_settings; print(get_settings().model_dump())"

# 3. Tester un agent isolément
python -c "
import asyncio
from pr_guardian.config import get_settings
from pr_guardian.integrations.github_client import GitHubClient
from pr_guardian.agents.code_analyst import CodeAnalyst

settings = get_settings()
client = GitHubClient(settings)
agent = CodeAnalyst(settings, client)
# ... tester l'agent
"
```

### Q: Comment déployer en CI/CD ?

Ajoutez cette étape dans votre pipeline GitHub Actions :

```yaml
# .github/workflows/pr-review.yml
name: PR Guardian Review
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run PR Guardian
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          COHERE_API_KEY: ${{ secrets.COHERE_API_KEY }}
          JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
          JIRA_USER_EMAIL: ${{ secrets.JIRA_USER_EMAIL }}
          JIRA_API_TOKEN: ${{ secrets.JIRA_API_TOKEN }}
        run: |
          python -m pr_guardian \
            --repo ${{ github.repository }} \
            --pr ${{ github.event.pull_request.number }} \
            --branch ${{ github.head_ref }} \
            --json-output
```

---

## Récapitulatif — Démarrage en 5 minutes

```bash
# 1. Aller dans le projet
cd /home/malek/Desktop/Team7

# 2. Activer l'environnement
source .venv/bin/activate

# 3. Créer le .env
cp .env.example .env

# 4. Éditer le .env (au minimum GITHUB_TOKEN)
nano .env

# 5. Vérifier la config
python -c "from pr_guardian.config import get_settings; s = get_settings(); print('✅ OK' if s.github_configured else '❌ Token manquant')"

# 6. Lancer une revue
python -m pr_guardian --repo owner/repo --pr 42

# 7. Ou lancer le serveur
python -m pr_guardian --server --port 8080
```

---

> 📖 **Documents liés** :
> - [CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md) — Guide détaillé de chaque API key
> - [README.md](../README.md) — Vue d'ensemble du projet
