# infra-request-orchestrator

> **Entreprise et données fictives.** NetCo est une entreprise inventée pour ce projet. Toutes les demandes,
> tous les tickets et toutes les configurations de ce dépôt sont synthétiques. Aucun client réel, aucune donnée
> réelle.

Orchestration de bout en bout d'une demande d'infrastructure (« exposer un service sur le réseau ») :
ServiceNow → Camunda 8 → Jira, Kubernetes et un simulateur de l'API vSphere. Des agents IA proposent, un processus
BPMN et une table DMN décident, et un humain valide toute action corrective.

## État

Phases P0 à P2 : le processus BPMN tourne de bout en bout, sans IA, de la demande ServiceNow jusqu'aux tickets
clos, avec une table DMN, une approbation dans Tasklist et un vrai provisionnement sur un cluster kind local. Les
agents IA (qualification, diagnostic, documentation) ne sont pas encore écrits. Suivi détaillé :
[docs/PROGRESS.md](docs/PROGRESS.md).

## Démarrer en local

Prérequis : Docker avec Compose 2.24 ou plus, [uv](https://docs.astral.sh/uv/), GNU make.

```sh
make setup      # environnement Python 3.12 (uv)
make lint test  # ruff et pytest
make up         # pile Camunda 8.10 + vcsim, attend que tout réponde
make down       # arrête la pile (les volumes sont conservés)
```

Avec un fichier `.env` rempli (modèle : [.env.example](.env.example)) :

```sh
make verify     # vérifie l'accès aux API ServiceNow et Jira, en lecture seule
make seed       # crée l'article de catalogue NetCo et commande 5 demandes synthétiques
```

## Démo locale du processus

Prérequis supplémentaire : [kind](https://kind.sigs.k8s.io/).

```sh
make up kind-up deploy-bpmn   # Camunda, cluster kind avec les zones réseau, déploiement des modèles
make seed                     # 5 demandes NetCo dans ServiceNow
make workers                  # workers et interrogation de ServiceNow (laisser tourner, Ctrl+C pour arrêter)
```

Dans Operate, on suit les 5 instances :
- 1 standard, terminée sans approbation ;
- 2 normales, en attente d'approbation dans Tasklist (groupe `cab`) ;
- 2 refusées par le référentiel, avec un commentaire dans ServiceNow.

`make e2e` rejoue le scénario complet de façon automatique, avec une approbation simulée. `make kind-down` et
`make down` arrêtent tout.

| Service | Adresse | Accès |
|---|---|---|
| Operate | http://localhost:8080/operate | `demo` / `demo` |
| Tasklist | http://localhost:8080/tasklist | `demo` / `demo` |
| API REST Camunda | http://localhost:8080/v2 | sans authentification (configuration locale légère) |
| Connectors | http://localhost:8086 | |
| vcsim, simulateur de l'API vSphere | https://localhost:8989/sdk | n'importe quel identifiant |

La pile reprend la configuration Docker Compose « légère » officielle de Camunda 8.10, que l'éditeur destine au
développement local et à l'évaluation. Les écarts sont décrits en tête de [docker-compose.yml](docker-compose.yml).

## Limites

Voir [docs/LIMITS.md](docs/LIMITS.md).

Auteur : Seifeddine BEN RHOUMA.
