"""
Client GitHub — PR-Guardian Orchestrator.

Fournit l'accès à l'API GitHub pour :
- Récupérer les métadonnées d'une PR (titre, description, auteur, branche)
- Lister les fichiers modifiés avec leur diff/patch
- Rechercher des fichiers dans le repo (UML, liens Figma…)
- Poster des commentaires sur la PR
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from github import Github, GithubException
from github.PullRequest import PullRequest

from pr_guardian.config import get_settings
from pr_guardian.models import ModifiedFile, PRContext

logger = logging.getLogger("pr_guardian.github")


class GitHubClient:
    """Wrapper autour de PyGithub pour les besoins de PR-Guardian."""

    def __init__(self, token: str | None = None):
        settings = get_settings()
        self._token = token or settings.github_token
        if not self._token:
            raise ValueError("GITHUB_TOKEN non configuré.")
        self._gh = Github(self._token, base_url=settings.github_api_url)

    # ── PR metadata ─────────────────────────

    def get_pr(self, repo_name: str, pr_number: int) -> PullRequest:
        """Récupère l'objet PullRequest GitHub."""
        repo = self._gh.get_repo(repo_name)
        return repo.get_pull(pr_number)

    def build_pr_context(self, repo_name: str, pr_number: int) -> PRContext:
        """Construit un PRContext riche à partir de l'API GitHub."""
        pr = self.get_pr(repo_name, pr_number)
        return PRContext(
            repo=repo_name,
            pr_number=pr_number,
            branch=pr.head.ref,
            pr_title=pr.title or "",
            pr_description=pr.body or "",
            pr_author=pr.user.login if pr.user else "",
            pr_author_email=pr.user.email or "" if pr.user else "",
        )

    # ── Fichiers modifiés ───────────────────

    def get_modified_files(self, repo_name: str, pr_number: int) -> list[ModifiedFile]:
        """Liste les fichiers modifiés dans la PR avec leur patch."""
        pr = self.get_pr(repo_name, pr_number)
        files: list[ModifiedFile] = []
        for f in pr.get_files():
            ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else ""
            files.append(
                ModifiedFile(
                    filename=f.filename,
                    status=f.status or "",
                    additions=f.additions,
                    deletions=f.deletions,
                    patch=f.patch or "",
                    language=ext,
                )
            )
        return files

    # ── Recherche dans le repo ──────────────

    def search_files(
        self, repo_name: str, pattern: str, branch: str = "main"
    ) -> list[str]:
        """Recherche des fichiers par pattern (glob simplifié) dans le repo."""
        repo = self._gh.get_repo(repo_name)
        try:
            tree = repo.get_git_tree(sha=branch, recursive=True)
        except GithubException:
            tree = repo.get_git_tree(sha="master", recursive=True)

        matched: list[str] = []
        regex = re.compile(pattern, re.IGNORECASE)
        for item in tree.tree:
            if item.type == "blob" and regex.search(item.path):
                matched.append(item.path)
        return matched

    def get_file_content(
        self, repo_name: str, filepath: str, branch: str = "main"
    ) -> str:
        """Lit le contenu d'un fichier du repo."""
        repo = self._gh.get_repo(repo_name)
        try:
            content_file = repo.get_contents(filepath, ref=branch)
        except GithubException:
            content_file = repo.get_contents(filepath, ref="master")

        if isinstance(content_file, list):
            raise ValueError(f"{filepath} est un répertoire, pas un fichier.")
        return content_file.decoded_content.decode("utf-8", errors="replace")

    # ── Extraction Jira key ─────────────────

    def extract_jira_key(self, pr_context: PRContext) -> str | None:
        """Tente d'extraire une clé Jira (ex: PROJ-123) depuis titre, description ou branche."""
        pattern = r"[A-Z][A-Z0-9]+-\d+"
        for text in [pr_context.pr_title, pr_context.pr_description, pr_context.branch]:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    # ── Recherche lien Figma ────────────────

    def find_figma_links(self, repo_name: str, branch: str = "main") -> list[str]:
        """Recherche les liens Figma dans le repo (README, docs, etc.)."""
        candidates = self.search_files(
            repo_name,
            r"(README|figma|design[-_]?link|docs/design)",
            branch,
        )
        links: list[str] = []
        figma_re = re.compile(r"https?://(?:www\.)?figma\.com/(?:file|design)/[^\s\)\"'>]+")
        for filepath in candidates:
            try:
                content = self.get_file_content(repo_name, filepath, branch)
                links.extend(figma_re.findall(content))
            except Exception:
                logger.debug(f"Impossible de lire {filepath}")
        return list(set(links))

    # ── Recherche fichiers UML ──────────────

    def find_uml_files(self, repo_name: str, branch: str = "main") -> list[str]:
        """Recherche les fichiers PlantUML dans le repo."""
        return self.search_files(repo_name, r"\.(puml|plantuml|wsd)$", branch)

    # ── Commenter la PR ─────────────────────

    def post_pr_comment(self, repo_name: str, pr_number: int, body: str) -> None:
        """Poste un commentaire sur la PR."""
        pr = self.get_pr(repo_name, pr_number)
        pr.create_issue_comment(body)
        logger.info(f"Commentaire posté sur {repo_name}#{pr_number}")
