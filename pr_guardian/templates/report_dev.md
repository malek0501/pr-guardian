# 🔧 Rapport PR-Guardian — Développeur

**Verdict :** {{ verdict.verdict.value }} {{ "✅" if verdict.verdict.value == "PASS" else ("❌" if verdict.verdict.value == "FAIL" else "🚫") }}
**Score de confiance :** {{ verdict.confidence_score }}/100
**Date :** {{ timestamp }}

---

## Contexte PR

| Champ       | Valeur |
|-------------|--------|
| Repo        | {{ pr_context.repo }} |
| PR          | #{{ pr_context.pr_number }} |
| Branche     | {{ pr_context.branch }} |
| Jira        | {{ pr_context.jira_key or "N/A" }} |

---

## Justification

{% for j in verdict.justification %}
- {{ j }}
{% endfor %}

---

{% if verdict.must_fix %}
## 🔧 MUST-FIX (priorisé)

{% for mf in verdict.must_fix %}
### {{ loop.index }}. [{{ mf.severity.value }}] {{ mf.description }}
- 📍 **Où :** {{ mf.location }}
- 💡 **Suggestion :** {{ mf.suggestion }}

{% endfor %}
{% endif %}

---

## Table de Validation

| Catégorie | Item | Statut | Preuve |
|-----------|------|--------|--------|
{% for row in validation_table %}
| {{ row.category }} | {{ row.item }} | {{ row.status.value }} | {{ row.evidence }} |
{% endfor %}

---

## Analyse de Code

{% if code_analysis %}
{{ code_analysis.summary }}

- **Classes modifiées :** {{ code_analysis.classes_touched | join(", ") or "aucune" }}
- **Endpoints :** {{ code_analysis.endpoints | join(", ") or "aucun" }}
- **Tests :** {{ code_analysis.test_coverage_info }}
- **Points sensibles :** {{ code_analysis.sensitive_points | join(", ") or "aucun" }}
{% else %}
Non disponible.
{% endif %}

---

*Généré par PR-Guardian Orchestrator — Team7*
