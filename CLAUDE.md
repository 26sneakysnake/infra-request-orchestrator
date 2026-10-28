# CLAUDE.md: infra-request-orchestrator

Orchestration de bout en bout d'une demande d'infrastructure avec Camunda 8, ServiceNow, Jira, Kubernetes, un
simulateur vSphere et des agents IA. Projet de preuve de travail pour une mission « automatisation et orchestration
des processus d'un département d'ingénierie d'hébergement et de réseau ». Auteur : Seifeddine BEN RHOUMA.
Lire `CONTEXT.md` avant toute chose, puis `PLAN.md`.

## Règles non négociables
1. **Données et entreprise fictives.** L'entreprise s'appelle « NetCo ». Aucun nom de client réel, aucun texte de
   l'offre recopié, aucune donnée réelle. Les demandes sont synthétiques. Le README le dit en première section.
2. **L'IA propose, le processus décide.** Les agents IA qualifient, diagnostiquent et rédigent. Les décisions de
   classement des changements passent par une table DMN déterministe. Toute action corrective proposée par un agent
   passe par une validation humaine (tâche utilisateur) avant exécution. Aucun agent n'a de droit d'écriture direct
   sur l'infrastructure.
3. **Aucune affirmation sans preuve.** Chaque chiffre du README vient d'un fichier de `results/` produit par un
   script. Petits échantillons : k/n et intervalle de Wilson à 95 %. Ce qui n'a pas tourné n'est pas annoncé.
4. **Rien d'inventé sur l'infrastructure.** Kubernetes tourne sur kind (équivalent local d'OpenShift, à dire comme
   tel). VMware est simulé avec vcsim (simulateur officiel de l'API vSphere, à dire comme tel). Le pare-feu est
   modélisé par des NetworkPolicy Kubernetes. Le README ne prétend jamais à un vrai vCenter ou à un vrai OpenShift.
5. **Pas de sur-ingénierie.** Un seul processus métier bien fait vaut mieux que cinq à moitié. Pas d'interface web
   maison : on utilise Operate et Tasklist de Camunda. Toute idée hors périmètre va dans `docs/NEXT.md`.
6. **Reproductible.** `make up` démarre tout en local (Docker), `make e2e` rejoue le scénario complet. Les appels
   LLM sont enregistrés (cassettes) et rejoués en CI ; le mode live est manuel avec plafond de coût.
7. **Aucun secret dans le dépôt.** Identifiants ServiceNow, Jira et Anthropic dans `.env` (ignoré par git) et dans
   les secrets GitHub. Seif ne les colle jamais dans la conversation.
8. **Les limites sont publiées** dans `docs/LIMITS.md`.

## Contraintes d'environnement
Claude Code sur le web ne peut pas lancer Docker ni kind (runc imbriqué). Donc : tests unitaires et mocks ici,
scénario de bout en bout dans GitHub Actions (docker compose + kind + vcsim), démo sur l'ordinateur de Seif.
Signaler clairement dans `docs/PROGRESS.md` ce qui a été vérifié où.

## Stack
Camunda 8 Self-Managed (Docker Compose local : Zeebe, Operate, Tasklist, Connectors), BPMN 2.0 et DMN,
connecteur AI Agent de Camunda (fournisseur Anthropic) ou worker Python si le connecteur ne convient pas,
workers Python 3.12 (client Zeebe/Camunda REST), uv, pytest, ruff. ServiceNow (instance développeur personnelle,
Table API), Jira Cloud (gratuit, API REST), Kubernetes via kind, vcsim (govmomi) avec pyVmomi.
Code et commentaires en anglais. Livrables de conseil (`docs/`) et README en français.

## Méthode
- Une phase de `PLAN.md` à la fois, en mode plan d'abord. Tests écrits avec le code. `make lint test` vert avant
  chaque commit. Fin de phase : `docs/PROGRESS.md` (fait, mesuré, vérifié où, reste), commit, push.
- Si une phase dépasse 150 % de son budget, s'arrêter et proposer une coupe (voir `PLAN.md`).
- Ne jamais modifier `results/` ni `eval/cases/` à la main.

## Commandes (Makefile)
`make setup` · `make lint` · `make test` · `make up` · `make down` · `make deploy-bpmn` · `make workers` ·
`make seed` · `make e2e` · `make eval` · `make readme`
