# Matrice de couverture CDC — DataVision AI

- CDC: 1.0 — August 2026
- Produit: 2.69.0
- Couverture pondérée: **88.7%**
- Implémenté: **58** / Partiel: **17** / Manquant: **0**
- Preuves absentes: **0**

> Méthode: implemented=1, partial=0.5, missing=0. Le score mesure la couverture du CDC, pas une certification externe.

| § | Exigence | Statut | Priorité | Gap principal |
|---:|---|---|---|---|
| 1 | Vision produit | implemented | P2 | — |
| 2 | Préserver / dépasser R & Shiny | partial | P2 | Runtime Python/R persistant livré; l’équivalence complète avec l’écosystème Shiny/Jupyter externe reste hors du périmètre natif. |
| 3 | Objectifs | implemented | P2 | — |
| 4 | Utilisateurs cibles | implemented | P2 | — |
| 5 | Principes produit | implemented | P2 | — |
| 6 | Workflow UX de bout en bout | implemented | P2 | — |
| 7 | Dashboard | implemented | P2 | — |
| 8 | Workspaces | implemented | P2 | — |
| 9 | Import & connecteurs | implemented | P1 | — |
| 10 | Profiling | implemented | P2 | — |
| 11 | Data Quality | implemented | P2 | — |
| 12 | AI Data Quality | partial | P1 | Suggestions AI de qualité existent mais la couverture de remédiation guidée n’est pas exhaustive. |
| 13 | Preparation Studio | implemented | P2 | — |
| 14 | Versioning dataset | implemented | P2 | — |
| 15 | Exploration automatique | implemented | P2 | — |
| 16 | Statistiques | implemented | P2 | — |
| 17 | Statistical Advisor | implemented | P2 | — |
| 18 | Visualisation | implemented | P1 | — |
| 19 | Langage naturel vers visualisation | implemented | P1 | — |
| 20 | AI Analyst | implemented | P2 | — |
| 21 | Architecture multi-agent | implemented | P1 | — |
| 22 | Reliability layer | implemented | P2 | — |
| 23 | Semantic layer | implemented | P2 | — |
| 24 | NLQ / Text-to-SQL | implemented | P2 | — |
| 25 | AutoML | partial | P1 | Classification, régression et clustering sont unifiés et gouvernés; le forecasting reste volontairement dans son moteur dédié jusqu’au lot forecasting/anomaly. |
| 26 | Model Benchmark | implemented | P2 | — |
| 27 | ML Guardrails | implemented | P2 | — |
| 28 | Explainable AI | implemented | P2 | — |
| 29 | Model Card | implemented | P2 | — |
| 30 | Forecasting | implemented | P2 | — |
| 31 | Anomaly detection | implemented | P2 | — |
| 32 | Automated Insight | implemented | P2 | — |
| 33 | Root Cause Analysis | implemented | P2 | — |
| 34 | What-if / sensitivity | implemented | P2 | — |
| 35 | Data storytelling | partial | P1 | Storytelling narratif multi-page automatisé encore partiel. |
| 36 | Report Builder | implemented | P2 | — |
| 37 | Reproducible analysis | implemented | P2 | — |
| 38 | Notebook | implemented | P1 | — |
| 39 | SQL workspace | implemented | P2 | — |
| 40 | Python workspace | partial | P1 | Kernel Python persistant et lock de dépendances projet livrés; environnements Conda/venv utilisateur avec installation dynamique restent hors du runtime sécurisé actuel. |
| 41 | R workspace | partial | P1 | Kernel R persistant et dépendances projet verrouillées livrés; installation dynamique de packages R reste image-managed par sécurité. |
| 42 | Collaboration | implemented | P2 | — |
| 43 | Data Catalog | implemented | P1 | — |
| 44 | Lineage | implemented | P2 | — |
| 45 | Governance | implemented | P2 | — |
| 46 | Security | partial | P1 | MFA WebAuthn, scan antivirus ClamAV et chiffrement AES-256-GCM dédié sont implémentés. Un KMS/HSM cloud externe reste optionnel et non intégré nativement. |
| 47 | AI Privacy | implemented | P2 | — |
| 48 | Model Gateway | partial | P1 | OpenAI-compatible et Ollama couverts; adaptateurs Anthropic/Gemini natifs restent à compléter. |
| 49 | MCP / Tool connectivity | implemented | P2 | — |
| 50 | Plugin System | implemented | P2 | — |
| 51 | Public API | implemented | P2 | — |
| 52 | Architecture technique cible | implemented | P2 | — |
| 53 | Architecture logique | implemented | P2 | — |
| 54 | Multi-tenant | implemented | P2 | — |
| 55 | Observability | implemented | P2 | — |
| 56 | AI Observability | implemented | P2 | — |
| 57 | Agent evaluation | implemented | P2 | — |
| 58 | Testing | implemented | P2 | — |
| 59 | Performance | partial | P1 | Benchmarks charge/latence à grande échelle et objectifs SLO complets restent à exécuter en environnement production. |
| 60 | UX/UI | implemented | P2 | — |
| 61 | Command Palette | implemented | P2 | — |
| 62 | AI Interaction | implemented | P2 | — |
| 63 | Quick Commands | implemented | P2 | — |
| 64 | Internationalisation | partial | P1 | Interface principalement française; framework i18n multi-langue complet absent. |
| 65 | Accessibilité | partial | P1 | Zoom et modes de lecture présents; audit WCAG complet, navigation clavier exhaustive et tests screen reader non documentés. |
| 66 | Product Plans | partial | P2 | Entitlements/quotas commerciaux par plan non appliqués partout dans le runtime. |
| 67 | Roadmap | implemented | P2 | — |
| 68 | MVP obligatoire | implemented | P0 | — |
| 69 | V1 | partial | P1 | Quelques profondeurs connecteurs/UX et détails de workspace avancé restent partiels. |
| 70 | V2 | partial | P1 | Multi-agent avancé, cloud deployment Enterprise complet et certaines fonctions causales/proactives restent partiels. |
| 71 | Critères d’acceptation | partial | P0 | CI/E2E/charge/Helm sont désormais automatisés; l’exécution cible et l’acceptance utilisateur métier doivent encore être signées comme preuves externes. |
| 72 | Règles impératives de développement | implemented | P0 | — |
| 73 | Livrables | implemented | P1 | — |
| 74 | Definition of Done | partial | P0 | La DoD technique est exécutable de bout en bout; le sign-off final reste conditionné aux preuves de l’environnement cible et à l’UAT signée. |
| 75 | Vision finale | partial | P1 | Vision largement matérialisée, mais les gaps P0/P1 empêchent de déclarer 100% du CDC. |

## Gaps prioritaires

### P0
- **§71 Critères d’acceptation** — CI/E2E/charge/Helm sont désormais automatisés; l’exécution cible et l’acceptance utilisateur métier doivent encore être signées comme preuves externes.
- **§74 Definition of Done** — La DoD technique est exécutable de bout en bout; le sign-off final reste conditionné aux preuves de l’environnement cible et à l’UAT signée.

### P1
- **§12 AI Data Quality** — Suggestions AI de qualité existent mais la couverture de remédiation guidée n’est pas exhaustive.
- **§25 AutoML** — Classification, régression et clustering sont unifiés et gouvernés; le forecasting reste volontairement dans son moteur dédié jusqu’au lot forecasting/anomaly.
- **§35 Data storytelling** — Storytelling narratif multi-page automatisé encore partiel.
- **§40 Python workspace** — Kernel Python persistant et lock de dépendances projet livrés; environnements Conda/venv utilisateur avec installation dynamique restent hors du runtime sécurisé actuel.
- **§41 R workspace** — Kernel R persistant et dépendances projet verrouillées livrés; installation dynamique de packages R reste image-managed par sécurité.
- **§46 Security** — MFA WebAuthn, scan antivirus ClamAV et chiffrement AES-256-GCM dédié sont implémentés. Un KMS/HSM cloud externe reste optionnel et non intégré nativement.
- **§48 Model Gateway** — OpenAI-compatible et Ollama couverts; adaptateurs Anthropic/Gemini natifs restent à compléter.
- **§59 Performance** — Benchmarks charge/latence à grande échelle et objectifs SLO complets restent à exécuter en environnement production.
- **§64 Internationalisation** — Interface principalement française; framework i18n multi-langue complet absent.
- **§65 Accessibilité** — Zoom et modes de lecture présents; audit WCAG complet, navigation clavier exhaustive et tests screen reader non documentés.
- **§69 V1** — Quelques profondeurs connecteurs/UX et détails de workspace avancé restent partiels.
- **§70 V2** — Multi-agent avancé, cloud deployment Enterprise complet et certaines fonctions causales/proactives restent partiels.
- **§75 Vision finale** — Vision largement matérialisée, mais les gaps P0/P1 empêchent de déclarer 100% du CDC.

### P2
- **§2 Préserver / dépasser R & Shiny** — Runtime Python/R persistant livré; l’équivalence complète avec l’écosystème Shiny/Jupyter externe reste hors du périmètre natif.
- **§66 Product Plans** — Entitlements/quotas commerciaux par plan non appliqués partout dans le runtime.

## Preuves manquantes

- Aucune preuve référencée manquante.
