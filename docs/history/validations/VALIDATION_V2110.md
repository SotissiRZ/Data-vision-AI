# Validation v2.11.0

Validation exécutée dans l'environnement de génération :

```text
pytest -q                         59 passed
python compileall                 OK
TypeScript ciblé strictNullChecks OK
CSS / TSX syntax                  OK
```

Scénarios v2.11 ajoutés :

- Slack Web API avec Bearer token chiffré ;
- absence de secret dans les réponses API ;
- payload `chat.postMessage` ;
- Jira Cloud issue payload + Basic API token ;
- SMTP STARTTLS + login + envoi ;
- chaîne d'approbation Data Scientist → Admin ;
- refus d'un approbateur hors étape ;
- progression et finalisation de la chaîne ;
- enqueue Redis uniquement après la dernière approbation.

Non validé dans cet environnement :

- livraison réseau réelle vers Slack/Teams/Jira/SMTP ;
- build `next build` complet, car `npm install` a dépassé le délai disponible ;
- OAuth2 réel contre un fournisseur externe.

Ces points doivent être vérifiés dans l'environnement Docker cible avec les credentials réels.
