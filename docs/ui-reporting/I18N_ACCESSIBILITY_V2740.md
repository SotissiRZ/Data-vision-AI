# DataVision AI v2.74 — Internationalisation & Accessibilité

## Portée

La v2.74 introduit un socle d'internationalisation et d'accessibilité appliqué au shell DataVision, aux préférences utilisateur et aux principaux mécanismes de navigation. Cette preuve est une **baseline d'ingénierie interne** et ne constitue pas une certification WCAG externe.

## Internationalisation

- catalogues de traduction à clés identiques pour `fr`, `en`, `es` et `ar` ;
- français par défaut avec détection du navigateur au premier chargement ;
- langue persistée localement et dans le profil Entreprise ;
- `lang` et `dir` appliqués dynamiquement au document ;
- arabe pris en charge en RTL ;
- navigation principale, navigation contextuelle, palette de commandes et réglages d'affichage localisés ;
- fallback déterministe vers le français pour les clés futures non encore traduites.

## Accessibilité — baseline WCAG 2.2 AA

| Domaine | Mesure v2.74 | Preuve |
|---|---|---|
| 1.3.1 Structure et relations | landmarks, navigation nommée, contenu principal identifiable | `frontend/app/page.tsx` |
| 1.4.3 / 1.4.11 Contraste | mode contraste renforcé et focus visible à fort contraste | `frontend/app/globals.css` |
| 1.4.4 Redimensionnement | modes de lecture et zoom UI 90–140 % persistants | `page.tsx`, préférences profil |
| 2.1.1 Clavier | skip-link, palette `Ctrl/Cmd+K`, fermeture Escape, contrôles natifs | `page.tsx`, E2E |
| 2.4.3 Ordre du focus | focus transféré au contenu principal lors d'un changement de vue | `page.tsx` |
| 2.4.7 Focus visible | règle globale `:focus-visible` | `globals.css` |
| 2.3.3 Animation | préférence explicite + `prefers-reduced-motion` | `globals.css` |
| 3.1.1 Langue de page | `documentElement.lang` synchronisé avec la locale | `page.tsx` |
| 4.1.2 Nom, rôle, valeur | `aria-expanded`, `aria-pressed`, `aria-current`, labels explicites | `page.tsx` |
| 4.1.3 Messages d'état | région `aria-live` et erreurs `role=alert` | `page.tsx` |

## Tests

- `backend/tests/test_i18n_accessibility_v274.py` : contrats déterministes côté source + persistance backend ;
- `frontend/e2e/accessibility.spec.ts` : contrat navigateur pour skip-link, focus, palette clavier, changement de langue/RTL, contraste et réduction d'animations ;
- `scripts/i18n_accessibility_acceptance.py` : gate 8/8 de release.

## Limites documentées

La v2.74 établit le socle de conformité et les tests de navigation essentiels. Une certification externe complète, incluant tests manuels multi-screen-reader et audit indépendant de chaque écran métier, reste distincte du statut d'implémentation produit et devra être conduite avant toute revendication de certification réglementaire formelle.
