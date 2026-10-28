# infra-request-orchestrator

> **Entreprise et données fictives.** NetCo est une entreprise inventée pour ce projet. Toutes les demandes,
> tous les tickets et toutes les configurations de ce dépôt sont synthétiques. Aucun client réel, aucune donnée
> réelle.

Orchestration de bout en bout d'une demande d'infrastructure (« exposer un service sur le réseau ») :
ServiceNow → Camunda 8 → Jira, Kubernetes et un simulateur de l'API vSphere. Des agents IA proposent, un processus
BPMN et une table DMN décident, et un humain valide toute action corrective.

## État

Phase P0 (squelette) seulement : outillage, CI et pile locale. Le processus, les intégrations et les agents ne
sont pas encore écrits. Suivi détaillé : [docs/PROGRESS.md](docs/PROGRESS.md).

## Démarrer en local

Prérequis : Docker avec Compose 2.24 ou plus, [uv](https://docs.astral.sh/uv/), GNU make.

```sh
make setup      # environnement Python 3.12 (uv)
make lint test  # ruff et pytest
make up         # pile Camunda 8.10 + vcsim, attend que tout réponde
make down       # arrête la pile (les volumes sont conservés)
```

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
