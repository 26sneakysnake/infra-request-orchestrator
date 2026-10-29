# infra-request-orchestrator

> **Entreprise et données fictives.** NetCo est une entreprise inventée pour ce projet. Toutes les demandes,
> tous les tickets et toutes les configurations de ce dépôt sont synthétiques. Aucun client réel, aucune donnée
> réelle.

Orchestration de bout en bout d'une demande d'infrastructure (« exposer un service sur le réseau ») :
ServiceNow → Camunda 8 → Jira, Kubernetes et un simulateur de l'API vSphere. Des agents IA proposent, un processus
BPMN et une table DMN décident, et un humain valide toute action corrective.

## État

Phases P0 à P7 : le processus BPMN tourne de bout en bout, de la demande ServiceNow jusqu'aux tickets clos. Il
comprend :
- un agent IA de qualification, qui transforme le texte libre en formulaire, cite le référentiel et interroge le
  demandeur quand une information manque ;
- une table DMN ;
- une approbation dans Tasklist ;
- un vrai provisionnement sur un cluster kind local et, quand la demande en réclame une, en parallèle, une VM
  créée sur vcsim, le simulateur de l'API vSphere ;
- en cas d'échec de la vérification réseau, un agent IA de diagnostic. Il est en lecture seule et propose une
  action d'une liste fermée, qu'un humain valide avant que le processus ne l'applique ;
- un agent IA de documentation, qui rédige la fiche de service et le compte rendu du changement. Un contrôle
  automatique refuse toute valeur absente des variables du processus, et un gabarit prend alors le relais. Les
  deux fichiers sont joints au ticket Jira et au changement ServiceNow.

Les résultats chiffrés sont dans [results/qualification.json](results/qualification.json) et
[results/diagnosis.json](results/diagnosis.json), et le suivi détaillé dans [docs/PROGRESS.md](docs/PROGRESS.md).

## Livrables de conseil

Six documents courts (2 pages au plus chacun) dans [docs/](docs/) :

| Document | Contenu |
|---|---|
| [01 Diagnostic de l'existant](docs/01-diagnostic-as-is.md) | Cartographie BPMN, irritants, priorisation de 8 processus |
| [02 Architecture cible](docs/02-architecture-cible.md) | Processus cible, composants, intégration, Camunda, n8n ou scripts, agents |
| [03 Feuille de route](docs/03-feuille-de-route.md) | Pitch de 5 minutes, trois vagues, indicateurs de sortie |
| [04 Gouvernance](docs/04-gouvernance.md) | Rôles, cycle de vie du modèle, indicateurs, garde-fous IA |
| [05 Guide opérationnel](docs/05-guide-operationnel.md) | Démarrer, suivre, traiter un incident, valider une remédiation |
| [06 Kit de formation](docs/06-kit-formation.md) | Atelier de 2 h avec trois exercices et leurs corrigés |

![Exposition d'un service, existant (hypothèse)](docs/img/expose_service_as_is.svg)

![Exposition d'un service, processus cible exécuté par Camunda](docs/img/expose_service.svg)

Les deux images sont produites par `make diagrams` depuis les modèles BPMN.

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
- 2 normales, en attente d'approbation dans Tasklist (groupe `cab`). Après approbation, celle qui réclame une
  VM la crée dans vcsim, dans le dossier `netco/recette` ;
- 2 refusées par le référentiel, avec un commentaire dans ServiceNow.

Chaque instance terminée laisse deux fichiers Markdown sur son ticket Jira et sur son changement ServiceNow : la
fiche de service et le compte rendu du changement.

Pour voir le diagnostic, il faut provoquer une panne sur un service avant `make workers`. Par exemple, en
PowerShell : `$env:NETCO_INJECT_FAULT = "network_policy_zone:catalogue-api"`. Les variantes sont listées dans
[src/k8s/faults.py](src/k8s/faults.py). La tâche « Valider la remédiation » apparaît alors dans Tasklist, avec
la cause, les preuves et l'action proposées par l'agent.

`make e2e` rejoue le scénario complet de façon automatique : approbation simulée, réponse simulée du
demandeur, VM, panne injectée et remédiation validée par le script, documentation jointe aux deux tickets. `make kind-down` et `make down` arrêtent tout.

## Mesures

Source : [results/metrics.json](results/metrics.json). `make metrics` le produit à partir de l'historique Camunda
de chaque instance (étapes datées, variables).

### Mesuré en laboratoire
L'échantillon compte 5 exécutions de l'e2e avec de vrais appels LLM, soit 20 demandes : 5 standard, 5 normales
avec VM, 5 en texte libre et 5 avec une panne réseau. Tout tourne sur un seul poste, et les décisions humaines
sont simulées par le script.

| Mesure | Valeur |
|---|---|
| Demandes terminées | 20/20 (Wilson 95 % : 0,839 à 1) |
| Durée de bout en bout, médiane (min à max) | 33,7 s (25,1 à 80,9) |
| Médiane par type : standard, normale avec VM, texte libre, panne | 26,0 s, 29,2 s, 46,1 s, 76,5 s |
| Temps de traitement hors attente humaine simulée, médiane | 30,1 s |
| Latence médiane des agents : qualification, diagnostic, documentation | 5,8 s, 6,3 s, 10,3 s |
| Activités automatisées | 210/225 |
| Demandes sans aucune intervention humaine (les demandes standard) | 5/20 (Wilson 95 % : 0,112 à 0,469) |
| Coût LLM par demande, médiane (maximum) | 0,0255 $ (0,0387 $) |
| Documentation rédigée par l'agent et acceptée par le contrôle | 20/20 (Wilson 95 % : 0,839 à 1) |

### Hypothèse « as-is » (non mesurée)
| Demande | Étapes manuelles | Effort humain | Délai |
|---|---|---|---|
| Standard, sans VM | 7 | 185 min | 3 à 12 jours ouvrés |
| Normale, avec VM | 9 | 240 min | 4 à 20 jours ouvrés |

Ces valeurs sont des hypothèses de l'auteur ([hypotheses/as-is.yaml](hypotheses/as-is.yaml)) pour une entreprise
fictive, pas une mesure. Les deux tableaux ne se soustraient pas : le laboratoire ne mesure pas l'attente humaine
réelle (CAB, demandeur), qui fait l'essentiel du délai supposé. Aucun gain n'est donc affirmé. La première
mesure à faire sur le terrain est un relevé de tickets réels ([diagnostic](docs/01-diagnostic-as-is.md)).

## Évaluation de l'agent de qualification

```sh
make eval        # 30 cas synthétiques, réponses rejouées depuis cassettes/llm/ : sans clé, sans coût
make eval-live   # réenregistre les réponses manquantes (clé Anthropic, plafond de dépense dans .env)
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
