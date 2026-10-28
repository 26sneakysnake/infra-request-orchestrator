# PLAN.md: infra-request-orchestrator (budget total : environ 16 h de Claude Code, sur 2 à 3 jours)

🟢 = Seif · 🤖 = Claude Code. Chaque phase se termine par un état utilisable.

## P0 : Squelette (1 h)
🤖 Dépôt public `infra-request-orchestrator`, `pyproject.toml` (uv), Makefile, ruff, pytest, CI (lint + tests),
`.gitignore` (`.env`), `.env.example`, README minimal (avertissement NetCo fictive, données synthétiques),
`docs/PROGRESS.md`, `docs/LIMITS.md`, `docs/NEXT.md`. `docker-compose.yml` Camunda 8 (Zeebe, Operate, Tasklist,
Connectors) d'après la documentation officielle à jour, plus vcsim.
**Fini quand :** `make lint test` passe en CI, et un job CI démarre la pile Docker et attend qu'elle réponde.

## P1 : Les comptes et les connecteurs (1 h 30)
🟢 Créer l'instance développeur ServiceNow, un site Jira Cloud gratuit (projet `NETOPS`), une clé Anthropic plafonnée.
Les mettre dans `.env` en local et dans les secrets GitHub.
🤖 `src/integrations/servicenow.py` et `jira.py` : clients minces (création, lecture, commentaire, pièce jointe,
changement d'état), avec tests sur réponses enregistrées. Script `make seed` qui crée 5 demandes synthétiques dans
ServiceNow. Script de vérification qui confirme l'accès aux deux API.
**Fini quand :** Seif lance le script de vérification chez lui et obtient « ServiceNow OK, Jira OK ».

## P2 : Le processus BPMN de base, sans IA (3 h)
🤖 `bpmn/expose_service.bpmn` et `bpmn/change_class.dmn`. Workers Python : démarrage depuis ServiceNow, création
Jira et changement ServiceNow, provisionnement Kubernetes (namespace, déploiement, Service, NetworkPolicy),
vérification, clôture. Tâche d'approbation dans Tasklist pour les changements « normaux ». Retries, événements
d'erreur, incidents visibles dans Operate. Référentiel NetCo dans `referentiel/` (nommage, ports, règles).
Pour l'instant, la qualification lit un formulaire déjà structuré.
CI : job e2e (docker compose + kind) qui joue une demande standard et une demande normale avec approbation simulée.
**Fini quand :** le job e2e est vert et Seif voit une instance complète dans Operate chez lui.

## P3 : L'agent de qualification (2 h)
🤖 Agent qui transforme le texte libre en champs structurés, cite le passage du référentiel utilisé, et signale les
informations manquantes (boucle de relance via commentaire ServiceNow). Connecteur AI Agent de Camunda si adapté,
sinon worker Python avec le SDK Anthropic ; justifier le choix dans `docs/02-architecture-cible.md`.
Cassettes pour la CI. `eval/cases/qualification/` : 30 demandes synthétiques variées (claires, ambiguës, port
interdit, environnement manquant, demande hors périmètre) avec réponse attendue, figées par empreinte.
**Fini quand :** `make eval` produit `results/qualification.json` (champs exacts k/n, informations manquantes
détectées k/n) et la CI rejoue sans clé.

## P4 : Diagnostic et remédiation (2 h 30)
🤖 Pannes injectées et reproductibles : NetworkPolicy trop restrictive, mauvais port de Service, image introuvable,
selector erroné, quota dépassé. Agent de diagnostic avec outils en lecture seule (événements, logs, description des
objets, recherche dans `referentiel/runbooks/`), qui rend une cause et une action proposée parmi une liste
autorisée. Tâche humaine de validation, puis exécution par le worker, puis nouvelle vérification.
`eval/cases/diagnosis/` : 10 pannes avec cause attendue.
**Fini quand :** `results/diagnosis.json` (bonne cause k/10, bonne action k/10) et le job e2e couvre une panne.

## P5 : VM sur vcsim et agent de documentation (1 h 30)
🤖 Branche « VM demandée » : création de VM sur vcsim via pyVmomi (dossier, réseau, taille). Agent de documentation :
fiche de service et compte rendu de changement en Markdown, joints au ticket Jira et au changement ServiceNow.
Contrôle automatique que la fiche ne contient que des valeurs présentes dans les variables du processus.
**Fini quand :** une instance avec VM passe de bout en bout en CI et la fiche est jointe aux deux tickets.

## P6 : Mesures (1 h)
🤖 `make metrics` lit l'historique des instances (API Camunda ou journal des workers) : durée par étape et de bout
en bout, part des tâches automatisées, interventions humaines, coût LLM par demande. Scénario « as-is » chronométré
de façon déclarée (hypothèses écrites, pas mesurées) pour la comparaison, présenté comme une hypothèse.
**Fini quand :** `results/metrics.json` existe et le README sépare mesuré et hypothèse.

## P7 : Les livrables de conseil (2 h)
🤖 Les six documents de `docs/` décrits dans `CONTEXT.md`, en français, avec les diagrammes BPMN as-is et to-be
exportés en image. Le kit de formation contient un exercice où un participant modélise un processus dans Camunda
Modeler. Chaque document tient en 2 pages maximum.
**Fini quand :** Seif peut présenter le diagnostic et la feuille de route en 5 minutes.

## P8 : README et démo (1 h 30)
🤖 `make readme` : README en français généré depuis `results/`, avec schéma, captures (Operate, Tasklist, ServiceNow,
Jira), chiffres avec k/n, « Ce que ce projet ne montre pas » et « Limites ». `docs/DEMO.md` : script de démo de 5 min
pour l'entretien, avec les commandes à lancer et un plan B (vidéo) si la démo locale échoue.
🟢 Lancer la démo en local une fois, enregistrer une vidéo de 3 min.
**Fini quand :** la démo tourne chez Seif en suivant `docs/DEMO.md` sans aide.

## Seuils de coupe (dans cet ordre)
1. P5 : garder la VM vcsim, supprimer l'agent de documentation (fiche générée par gabarit).
2. P6 : seulement la durée de bout en bout et la part automatisée.
3. P4 : 5 pannes au lieu de 10.
4. P7 : fusionner gouvernance et kit de formation.
Ne jamais couper : le BPMN de bout en bout, la DMN, la validation humaine avant remédiation, ServiceNow et Jira
réels, les limites publiées.
