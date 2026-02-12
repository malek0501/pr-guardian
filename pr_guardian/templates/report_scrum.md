# 📊 Rapport PR-Guardian — Scrum Master

**Verdict :** {{ verdict.verdict.value }} {{ "✅" if verdict.verdict.value == "PASS" else "❌" }}
**Score de confiance :** {{ verdict.confidence_score }}/100
**Date :** {{ timestamp }}

---

## Contexte PR

| Champ       | Valeur |
|-------------|--------|
| Repo        | {{ pr_context.repo }} |
| PR          | #{{ pr_context.pr_number }} |
| Branche     | {{ pr_context.branch }} |
| Auteur      | {{ pr_context.pr_author }} |
| Jira        | {{ pr_context.jira_key or "N/A" }} |
| Figma       | {{ pr_context.figma_link or "N/A" }} |

---

## Justification

{% for j in verdict.justification %}
- {{ j }}
{% endfor %}

---

## Table de Validation

| Catégorie | Item | Statut | Preuve |
|-----------|------|--------|--------|
{% for row in validation_table %}
| {{ row.category }} | {{ row.item }} | {{ row.status.value }} | {{ row.evidence }} |
{% endfor %}

---

*Généré par PR-Guardian Orchestrator — Team7*
