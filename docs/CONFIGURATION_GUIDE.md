# 🔧 PR-Guardian — Guide Complet de Configuration

> Ce guide vous accompagne pas à pas pour configurer **toutes les clés API et services** nécessaires au fonctionnement de PR-Guardian Orchestrator.

---

## Table des Matières

1. [Vue d'ensemble](#1--vue-densemble)
2. [Fichier `.env`](#2--fichier-env)
3. [GitHub — Personal Access Token](#3--github--personal-access-token)
4. [Jira — API Token](#4--jira--api-token)
5. [Figma — Access Token](#5--figma--access-token)
6. [Cohere — API Key (LLM-as-a-Judge)](#6--cohere--api-key-llm-as-a-judge)
7. [Email — SMTP ou SendGrid](#7--email--smtp-ou-sendgrid)
8. [Paramètres Généraux](#8--paramètres-généraux)
9. [Vérification de la Configuration](#9--vérification-de-la-configuration)
10. [Configuration Minimale vs Complète](#10--configuration-minimale-vs-complète)
11. [Résolution de Problèmes](#11--résolution-de-problèmes)

---

## 1 — Vue d'ensemble

PR-Guardian se connecte à **5 services externes** :

| Service      | Obligatoire ? | Rôle                                              |
|:-------------|:-------------:|:--------------------------------------------------|
| **GitHub**   | ✅ OUI        | Lire la PR, les fichiers modifiés, poster un commentaire |
| **Jira**     | ⚪ Optionnel  | Valider les critères d'acceptation du ticket       |
| **Figma**    | ⚪ Optionnel  | Vérifier la conformité UI avec les maquettes       |
| **Cohere**   | ⚪ Optionnel  | LLM-as-a-Judge — verdict intelligent (fallback heuristique sinon) |
| **Email**    | ⚪ Optionnel  | Envoyer les rapports par email                     |

> **Seul GitHub est strictement obligatoire.** Les autres agents fonctionnent en mode dégradé si leurs APIs ne sont pas configurées.

---

## 2 — Fichier `.env`

### Créer le fichier

```bash
cd /home/malek/Desktop/Team7
cp .env.example .env
```

### Principe

Le fichier `.env` est lu automatiquement par Pydantic Settings au démarrage. Il ne doit **jamais** être commité dans Git (il est déjà dans `.gitignore`).

### Structure complète

```dotenv
# ── GitHub ──────────────────────────────────
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_API_URL=https://api.github.com

# ── Jira ────────────────────────────────────
JIRA_BASE_URL=https://votre-instance.atlassian.net
JIRA_USER_EMAIL=user@example.com
JIRA_API_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx
JIRA_DONE_TRANSITION_ID=31
JIRA_NEEDS_FIX_TRANSITION_ID=21

# ── Figma ───────────────────────────────────
FIGMA_ACCESS_TOKEN=figd_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── LLM / Cohere ───────────────────────────
COHERE_API_KEY=votre_cle_cohere_ici
COHERE_MODEL=command-r-plus
COHERE_MAX_TOKENS=4096

# ── Email (SMTP) ───────────────────────────
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=bot@example.com
SMTP_PASSWORD=app-password-here
EMAIL_FROM=PR-Guardian <bot@example.com>

# ── Email (SendGrid — alternatif) ──────────
# EMAIL_PROVIDER=sendgrid
# SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── Général ─────────────────────────────────
LOG_LEVEL=INFO
LANGUAGE=fr
```

---

## 3 — GitHub — Personal Access Token

### Étape 1 : Créer un token

1. Allez sur **[github.com/settings/tokens](https://github.com/settings/tokens)**
2. Cliquez **"Generate new token"** → choisissez **"Fine-grained personal access token"** (recommandé)
3. Configurez :
   - **Token name** : `PR-Guardian`
   - **Expiration** : 90 jours (ou plus selon votre politique)
   - **Repository access** : sélectionnez le(s) repo(s) ciblé(s)
4. Accordez ces **permissions** :

| Permission           | Accès requis | Pourquoi                                    |
|:---------------------|:-------------|:--------------------------------------------|
| **Pull requests**    | Read & Write | Lire la PR + poster des commentaires         |
| **Contents**         | Read-only    | Lire les fichiers (UML, code, etc.)          |
| **Metadata**         | Read-only    | Accéder aux infos du repo                    |

5. Cliquez **"Generate token"** et copiez le token (`ghp_...` ou `github_pat_...`)

### Étape 2 : Configurer dans `.env`

```dotenv
GITHUB_TOKEN=ghp_votre_token_ici
GITHUB_API_URL=https://api.github.com
```

> **GitHub Enterprise ?** Changez `GITHUB_API_URL` vers `https://github.votre-entreprise.com/api/v3`

### Vérification rapide

```bash
curl -H "Authorization: token ghp_votre_token_ici" https://api.github.com/user
```

Vous devriez voir votre profil JSON. Si erreur `401`, le token est invalide.

---

## 4 — Jira — API Token

### Étape 1 : Créer un API Token Atlassian

1. Allez sur **[id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)**
2. Connectez-vous avec votre compte Atlassian
3. Cliquez **"Créer un jeton d'API"**
4. **Label** : `PR-Guardian`
5. Copiez le token généré (il ne sera plus affiché)

### Étape 2 : Trouver votre URL Jira

Votre URL est de la forme : `https://VOTRE-ESPACE.atlassian.net`

Exemple : si vous accédez à Jira via `https://team7.atlassian.net/browse/PROJ-42`, alors :
```
JIRA_BASE_URL=https://team7.atlassian.net
```

### Étape 3 : Trouver les Transition IDs

Les transitions Jira (Done, Needs Fix) ont des IDs numériques. Pour les trouver :

```bash
# Remplacez les valeurs par les vôtres
curl -u "votre-email@example.com:VOTRE_JIRA_TOKEN" \
  "https://VOTRE-ESPACE.atlassian.net/rest/api/3/issue/PROJ-42/transitions" \
  | python -m json.tool
```

Réponse type :
```json
{
  "transitions": [
    { "id": "21", "name": "In Progress" },
    { "id": "31", "name": "Done" },
    { "id": "41", "name": "Needs Fix" }
  ]
}
```

Utilisez les IDs correspondants dans votre `.env`.

### Étape 4 : Configurer dans `.env`

```dotenv
JIRA_BASE_URL=https://team7.atlassian.net
JIRA_USER_EMAIL=votre-email@example.com
JIRA_API_TOKEN=votre_jira_token_ici
JIRA_DONE_TRANSITION_ID=31
JIRA_NEEDS_FIX_TRANSITION_ID=41
```

### Convention de nommage des tickets

PR-Guardian extrait la clé Jira automatiquement depuis :
- Le **titre** de la PR (ex: `[PROJ-42] Fix login page`)
- La **description** de la PR
- Le **nom de la branche** (ex: `feature/PROJ-42-login-fix`)

Le format attendu est : `PROJ-123` (lettres majuscules, tiret, chiffres).

---

## 5 — Figma — Access Token

### Étape 1 : Créer un token Figma

1. Ouvrez **[figma.com](https://www.figma.com)** et connectez-vous
2. Cliquez sur votre **avatar** (en haut à gauche) → **Settings**
3. Descendez jusqu'à **"Personal access tokens"**
4. Cliquez **"Generate new token"**
5. **Token name** : `PR-Guardian`
6. **Expiration** : choisissez la durée souhaitée
7. **Scopes** : cochez au minimum **"File content"** (Read-only)
8. Copiez le token (`figd_...`)

### Étape 2 : Configurer dans `.env`

```dotenv
FIGMA_ACCESS_TOKEN=figd_votre_token_ici
```

### Comment PR-Guardian trouve les fichiers Figma

L'agent Figma cherche des URLs Figma dans :
- La **description** de la PR
- Les **commentaires** de la PR

Format attendu :
```
https://www.figma.com/file/ABCDEF123456/NomDuFichier
https://www.figma.com/design/ABCDEF123456/NomDuFichier
```

> **Astuce** : incluez le lien Figma dans la description de votre PR pour que l'agent puisse vérifier la conformité UI.

### Vérification rapide

```bash
curl -H "X-Figma-Token: figd_votre_token_ici" \
  "https://api.figma.com/v1/me"
```

---

## 6 — Cohere — API Key (LLM-as-a-Judge)

### Étape 1 : Obtenir une clé API

1. Allez sur **[dashboard.cohere.com/api-keys](https://dashboard.cohere.com/api-keys)**
2. Créez un compte ou connectez-vous
3. Cliquez **"Create Trial Key"** (gratuit) ou **"Create Production Key"**
4. Copiez la clé

> ⚠️ **Le plan Trial est gratuit** avec des limites de rate (20 appels/minute). Pour un usage intensif, passez au plan Production.

### Étape 2 : Choisir le modèle

| Modèle                | Coût     | Qualité    | Recommandé pour         |
|:----------------------|:---------|:-----------|:------------------------|
| `command-a-03-2025`   | Trial*   | Excellente | Production (défaut)     |
| `command-r-plus-08-2024` | Trial* | Très bonne | Alternative stable      |
| `command-r7b-12-2024` | Trial*   | Bonne      | Usage rapide, low-cost  |

\* Gratuit sous les limites du plan Trial (20 req/min, 1000 req/mois).

### Étape 3 : Configurer dans `.env`

```dotenv
COHERE_API_KEY=votre_cle_cohere_ici
COHERE_MODEL=command-a-03-2025
COHERE_MAX_TOKENS=4096
```

### Mode Fallback (sans Cohere)

Si `COHERE_API_KEY` est vide, le Judge utilise un **fallback heuristique** :
- Analyse les scores des agents
- Applique des règles simples (seuils de score)
- Produit quand même un verdict PASS/FAIL/BLOCKED

C'est moins intelligent mais fonctionnel pour les cas simples.

---

## 7 — Email — SMTP ou SendGrid

PR-Guardian supporte deux providers d'email :

### Option A : SMTP (Gmail, Outlook, etc.)

#### Gmail — Configuration

1. Activez la **vérification en 2 étapes** sur votre compte Google
2. Allez sur **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)**
3. Créez un **mot de passe d'application** :
   - **App** : `Mail`
   - **Device** : `Other` → `PR-Guardian`
4. Copiez le mot de passe de 16 caractères (sans espaces)

```dotenv
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=votre-email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
EMAIL_FROM=PR-Guardian <votre-email@gmail.com>
```

#### Outlook / Office 365

```dotenv
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=votre-email@outlook.com
SMTP_PASSWORD=votre_mot_de_passe
EMAIL_FROM=PR-Guardian <votre-email@outlook.com>
```

#### Serveur SMTP custom

```dotenv
EMAIL_PROVIDER=smtp
SMTP_HOST=mail.votre-domaine.com
SMTP_PORT=587
SMTP_USER=bot@votre-domaine.com
SMTP_PASSWORD=mot_de_passe
EMAIL_FROM=PR-Guardian <bot@votre-domaine.com>
```

### Option B : SendGrid

1. Créez un compte sur **[sendgrid.com](https://sendgrid.com)**
2. Allez dans **Settings → API Keys**
3. Cliquez **"Create API Key"**
4. **Nom** : `PR-Guardian`
5. **Permissions** : `Restricted Access` → activez **"Mail Send"**
6. Copiez la clé (`SG.xxx`)

```dotenv
EMAIL_PROVIDER=sendgrid
SENDGRID_API_KEY=SG.votre_cle_ici
EMAIL_FROM=PR-Guardian <noreply@votre-domaine.com>
```

> **Note** : avec SendGrid, vous devez aussi vérifier votre domaine ou adresse d'envoi dans le dashboard SendGrid.

---

## 8 — Paramètres Généraux

```dotenv
LOG_LEVEL=INFO
LANGUAGE=fr
```

| Variable     | Valeurs possibles | Par défaut | Description                    |
|:-------------|:------------------|:-----------|:-------------------------------|
| `LOG_LEVEL`  | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` | Niveau de log dans la console |
| `LANGUAGE`   | `fr`, `en`        | `fr`       | Langue des rapports et logs   |

- **`DEBUG`** : affiche tout, y compris les payloads API (utile pour le développement)
- **`INFO`** : affiche les étapes principales (recommandé pour la production)
- **`WARNING`** : uniquement les problèmes

---

## 9 — Vérification de la Configuration

### Script de vérification rapide

Après avoir rempli votre `.env`, lancez ce script pour vérifier que tout est bien configuré :

```bash
cd /home/malek/Desktop/Team7
source .venv/bin/activate
python -c "
from pr_guardian.config import get_settings

s = get_settings()
print('=== PR-Guardian — Vérification de la Configuration ===')
print()
print(f'  GitHub    : {'✅ Configuré' if s.github_configured else '❌ Manquant (OBLIGATOIRE)'}')
print(f'  Jira      : {'✅ Configuré' if s.jira_configured else '⚪ Non configuré (optionnel)'}')
print(f'  Figma     : {'✅ Configuré' if s.figma_configured else '⚪ Non configuré (optionnel)'}')
print(f'  Cohere    : {'✅ Configuré' if s.llm_configured else '⚪ Non configuré (fallback heuristique)'}')
print(f'  Email     : {'✅ Configuré' if s.email_configured else '⚪ Non configuré (optionnel)'}')
print()
if s.github_configured:
    print('🟢 Configuration minimale OK — PR-Guardian peut fonctionner.')
else:
    print('🔴 GITHUB_TOKEN manquant — PR-Guardian ne peut pas fonctionner.')
"
```

### Vérifier la connexion GitHub

```bash
python -c "
from pr_guardian.config import get_settings
from pr_guardian.integrations.github_client import GitHubClient

client = GitHubClient(get_settings())
user = client._github.get_user()
print(f'✅ Connecté en tant que : {user.login}')
print(f'   Rate limit restant : {client._github.get_rate_limit().core.remaining}')
"
```

---

## 10 — Configuration Minimale vs Complète

### 🟡 Minimale (GitHub uniquement)

```dotenv
GITHUB_TOKEN=ghp_votre_token
```

**Agents actifs** : Code Analyst uniquement  
**Judge** : Fallback heuristique  
**Résultat** : Analyse de code basique, pas de validation Jira/Figma/UML, pas d'email

---

### 🟢 Recommandée (GitHub + Cohere + Jira)

```dotenv
GITHUB_TOKEN=ghp_votre_token
COHERE_API_KEY=votre_cle_cohere
JIRA_BASE_URL=https://team7.atlassian.net
JIRA_USER_EMAIL=email@example.com
JIRA_API_TOKEN=jira_token
```

**Agents actifs** : Code Analyst + Jira Validator + UML Checker  
**Judge** : LLM intelligent  
**Résultat** : Analyse de code complète, validation des critères Jira, vérification UML

---

### 🔵 Complète (tous les services)

```dotenv
GITHUB_TOKEN=ghp_votre_token
GEMINI_API_KEY=AIzaSy-votre_cle
JIRA_BASE_URL=https://team7.atlassian.net
JIRA_USER_EMAIL=email@example.com
JIRA_API_TOKEN=jira_token
FIGMA_ACCESS_TOKEN=figd_votre_token
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=bot@gmail.com
SMTP_PASSWORD=app_password
EMAIL_FROM=PR-Guardian <bot@gmail.com>
```

**Agents actifs** : Tous les 5 agents  
**Judge** : LLM intelligent  
**Résultat** : Revue complète avec vérification UI Figma + emails automatiques

---

## 11 — Résolution de Problèmes

### `GITHUB_TOKEN` → Erreur 401

- Le token a peut-être expiré → régénérez-le
- Vérifiez que le token a les bons scopes (Pull requests Read/Write, Contents Read)

### `JIRA_API_TOKEN` → Erreur 401

- Vérifiez que l'email correspond au compte qui a créé le token
- Le token Jira est lié à un compte, pas à un projet
- Testez manuellement : `curl -u "email:token" https://instance.atlassian.net/rest/api/3/myself`

### `FIGMA_ACCESS_TOKEN` → Erreur 403

- Le token doit avoir le scope **"File content"**
- Vérifiez que vous avez accès au fichier Figma ciblé (pas en mode "restricted")

### `GEMINI_API_KEY` → Erreur 429

- Vous avez atteint la limite de requêtes → attendez ou passez au plan payant
- Vérifiez vos quotas sur [aistudio.google.com](https://aistudio.google.com)

### Email → Erreur de connexion SMTP

- **Gmail** : assurez-vous d'utiliser un **mot de passe d'application**, pas votre mot de passe normal
- **Port** : essayez `465` (SSL) si `587` (TLS) ne fonctionne pas
- **Firewall** : vérifiez que le port n'est pas bloqué par votre réseau

### `.env` non chargé

- Le fichier doit être à la **racine du projet** : `/home/malek/Desktop/Team7/.env`
- Pas dans un sous-dossier
- Pas de `.env` avec un espace dans le nom
- Vérifiez les guillemets : pas de `"` autour des valeurs (sauf si la valeur contient des espaces)

---

> **Besoin d'aide ?** Lancez avec `LOG_LEVEL=DEBUG` pour voir les détails de chaque appel API.
