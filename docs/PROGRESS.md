# Avancement

Une section par phase : ce qui est fait, ce qui est mesuré, où c'est vérifié, ce qui reste.

## P0 : Squelette (terminée le 2026-10-28)

### Fait
- Outillage : `pyproject.toml` (uv, Python 3.12) et `uv.lock`, ruff, pytest, Makefile, `.gitignore`,
  `.gitattributes`, `.env.example`.
- README minimal (avertissement « NetCo fictive, données synthétiques » en première section), `docs/LIMITS.md`,
  `docs/NEXT.md`.
- `docker-compose.yml` : Camunda **8.10** dans sa configuration légère officielle (`camunda/camunda:8.10.7`, soit
  Zeebe, Operate, Tasklist et Admin ; `camunda/connectors-bundle:8.10.2`), plus vcsim (`vmware/vcsim:v0.56.2`).
  La version et le fichier ont été vérifiés dans la documentation et l'archive officielles de Camunda le
  2026-10-28. Les écarts sont listés en tête du fichier.
- `src/stack/health.py` : sonde, depuis l'hôte, des 6 points d'accès (REST, management, Operate, Tasklist,
  Connectors, vcsim). `make up` attend qu'ils répondent tous.
- CI GitHub Actions : un job `lint-test` (`make lint test`) et un job `stack` (`make up`, puis arrêt de la pile).
- Les cibles des phases suivantes (`seed`, `deploy-bpmn`, `workers`, `e2e`, `eval`, `metrics`, `readme`) existent
  et échouent avec un message explicite (« arrives in phase Px »).

### Mesuré (une seule exécution, à titre indicatif)
- Tests unitaires : 8/8 passent.
- `make up` sur le PC de Seif (Windows 10, Docker Desktop 28.5.1) : 140 s au premier lancement, téléchargement des
  images compris, puis 20 s avec les images en cache.
- Mémoire au repos : orchestration environ 620 Mo (limite 1 Go), connectors environ 390 Mo (limite 512 Mo), vcsim
  environ 15 Mo.
- GitHub Actions : 10 s pour le job `lint-test` ; 52 s pour le job `stack`, dont 42 s pour `make up`, images
  téléchargées comprises.

### Vérifié où
CI de référence : [run 40690470381](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40690470381)
sur le commit `ecf3b63`. Le premier run (commit `efa6970`) a échoué avant toute exécution : `astral-sh/setup-uv@v10`
n'existe pas comme étiquette. Corrigé en épinglant `v10.3.2`.

| Vérification | PC de Seif (Windows) | GitHub Actions (Linux) |
|---|---|---|
| `make lint test` | vert | vert |
| `make up` : les 6 points d'accès répondent | vert | vert (la sonde sort en erreur sinon) |
| `/v2/topology` : 1 broker en 8.10.7, partition `healthy` | vérifié avec curl | non vérifié |
| Operate et Tasklist servent leur page (HTTP 200) | vérifié avec curl | non vérifié |
| Connexion `demo/demo` à l'API REST (recherche de définitions de processus) | vérifiée avec curl | non vérifiée |
| `make down`, puis relance à froid | vert | `docker compose down -v` en fin de job |

Non vérifié : la connexion interactive à Operate dans un navigateur. Je n'ai testé que les réponses HTTP.

### Reste
- Rien pour P0.
- À surveiller : GitHub annonce que `ubuntu-latest` passe à Ubuntu 26 à partir du 19 octobre 2026. Si le job
  `stack` casse, épingler `ubuntu-24.04`.
- `CONTEXT.md` reste local, ignoré par git, à la demande de Seif. `CLAUDE.md` y fait référence.
- Prochaine phase : P1, seulement avec l'accord de Seif.

## P1 : Comptes et connecteurs (terminée le 2026-10-28)

### Fait
- Comptes créés par Seif :
  - instance développeur ServiceNow (release Zurich) ;
  - site Jira Cloud gratuit, avec le projet `NETOPS` en mode team-managed.

  La clé Anthropic n'est pas encore créée ; elle servira en P3.
- `src/integrations/` :
  - `servicenow.py` : client mince pour les API Table, Attachment et Service Catalog ;
  - `jira.py` : client mince pour l'API REST v3 (création, lecture, commentaire, pièce jointe, transition) ;
  - `config.py` : lecture de `.env` ;
  - `cassette.py` : enregistrement et rejeu des échanges HTTP par les transports httpx. Aucun en-tête n'est
    stocké, et les hôtes, e-mails et identifiants sont remplacés.
- `make verify` (en lecture seule) contrôle l'accès aux deux API.
- `make seed` :
  - crée, si elles n'existent pas, la catégorie « NetCo » et l'article « Exposition de service (NetCo) » avec ses
    8 variables (texte libre, puis service, environnement, ports, réseaux sources, exposition, VM et taille) ;
  - commande ensuite 5 demandes synthétiques par l'API Service Catalog (`seed/requests.yaml`).
- `make record` réenregistre les cassettes sur les vraies instances.

### Mesuré
- Tests : 29 sur 29 passent, sans réseau. Deux d'entre eux rejouent de vrais appels enregistrés : 10 échanges avec
  ServiceNow et 7 avec Jira.
- `make seed` : 5 demandes sur 5 créées (REQ0010001 à REQ0010005, RITM0010001 à RITM0010005). Les variables ont
  été relues par la Table API (`variables.<nom>`). Une seconde exécution de la création de l'article ne crée aucun
  doublon.

### Vérifié où
| Vérification | PC de Seif (Windows) | GitHub Actions |
|---|---|---|
| `make verify` : `ServiceNow OK`, `Jira OK` | vert, lancé par Claude Code puis par Seif lui-même | sans objet : pas de secret en CI |
| `make seed` : 5 demandes créées | vert | sans objet |
| Cassettes enregistrées sur les vraies instances | oui | rejouées sans réseau |
| Cassettes sans secret ni identifiant (mot de passe, jeton, e-mail, hôtes, nom affiché, `accountId`) | vérifié par script | sans objet |
| `make lint test` | vert | vert : [run 40703449301](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40703449301), commit `45acc72` |

### Écarts et incidents
- **Projet Jira :** créé avec la clé `KAN`, puis renommé `NETOPS` par Seif. `.env` a été corrigé en conséquence.
- **ServiceNow en 401 :** sur cette instance Zurich, l'API refuse l'authentification Basic sans le rôle
  `snc_basic_auth_api_access`, même pour admin. Seif a ajouté ce rôle à admin et changé le mot de passe.
- **Jira en français :** le type « Tâche » est choisi par son nom anglais (`untranslatedName` = `Task`), et la
  transition par catégorie de statut (`done`). Le code ne dépend donc pas des noms traduits.
- **vcrpy écarté :** 5 versions publiées le même jour, trois jours plus tôt. L'enregistrement s'appuie sur les
  transports httpx.
- **Données de test réellement créées par les enregistrements :** RITM0010006 dans ServiceNow ; NETOPS-4 et
  NETOPS-5 dans Jira (le premier enregistrement a été refait pour masquer le nom affiché et l'`accountId`).

### Reste
- Critère de fin atteint : Seif a obtenu `ServiceNow OK` et `Jira OK` avec `make verify`.
- Secrets GitHub : inutiles en P1, puisque la CI rejoue les cassettes. À créer avant le job e2e de P2.
- Clé Anthropic : à créer avant P3.
- Prochaine phase : P2, seulement avec l'accord de Seif.

## P2 : Processus BPMN de base, sans IA

### Fait
- **Test préalable ServiceNow.** Un changement « Normal » ne passe de Assess à Authorize qu'avec l'approbation
  ServiceNow des membres du groupe d'affectation. Les approuver par l'API reviendrait à agir au nom de ces
  personnes. Le processus enregistre donc le changement avec le modèle « Change Registration », que ServiceNow
  décrit ainsi : *« a record of an automated change. There are no approvals associated with this change
  model. »* C'est cohérent avec une approbation faite dans Camunda. La clôture exige `close_code=successful` et une
  description non vide. Le test a laissé 3 changements : CHG0030001 (annulé), CHG0030002 et CHG0030003 (clos).
- **Référentiel NetCo `referentiel/`** : `netco.yaml` (source de vérité pour le code) et 5 pages Markdown. Chaque
  règle a un identifiant : NOM, ENV, EXP, PORT, ZONE, CHG.
- **Modèles** :
  - `bpmn/expose_service.bpmn`, avec le diagramme complet ;
  - `bpmn/change_class.dmn`, en hit policy FIRST avec 5 règles ;
  - les formulaires Tasklist `change-approval` et `verification-fix`.
- **Workers Python** sur le SDK officiel `camunda-orchestration-sdk` 10.0.0, pour 7 types de job :
  - un poller ServiceNow ;
  - le provisionnement Kubernetes (Namespace, Deployment, Service, NetworkPolicy) ;
  - la vérification par des sondes dans chaque zone.
- **Workers idempotents.** Zeebe livre un job « au moins une fois ». Un job rejoué retrouve son changement (par
  `correlation_id` = numéro de la demande) et son ticket Jira (par un label du même numéro), au lieu de les
  recréer.
- **Commandes** : `make kind-up`, `deploy-bpmn`, `workers`, `e2e`, et le workflow `.github/workflows/e2e.yml`.
- Catalogue ServiceNow : nouvelle variable `urgent`.

### Mesuré (sur le PC de Seif, à titre indicatif)
- Tests unitaires : 64 sur 64.
- DMN évaluée par le moteur : 5 cas attendus sur 5.
- `make e2e` : 3 exécutions, et à chaque fois 2 demandes sur 2 menées au bout avec 5 contrôles sur 5. Les deux
  demandes sont une standard sans approbation et une normale avec approbation simulée. Durée de la commande à la
  clôture lors de la 1re exécution : 13,9 s et 30,0 s.
- NetworkPolicy :
  - la zone demandée joint le service, une zone non demandée est bloquée ;
  - contre-épreuve, sans la NetworkPolicy : les deux zones joignent le service.
- **Refus** : une demande avec un port interdit termine son instance, et le RITM passe en Closed Incomplete avec la
  règle PORT-01 en commentaire.
- **Incident** :
  - avec un jeton Jira faux, 3 échecs, puis un incident « JOB_NO_RETRIES » apparaît avec le message de Jira ;
  - après correction du jeton et relance, l'instance se termine.
- **Idempotence** : en rejouant les deux handlers sur une demande déjà traitée, on retrouve les mêmes
  enregistrements (CHG0030010, NETOPS-13).

### Vérifié où
| Vérification | PC de Seif (Windows) | GitHub Actions |
|---|---|---|
| `make lint test` | vert | vert : [run 40711285304](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40711285304), commit `f380ba6` |
| `make e2e` | vert (3 exécutions) | vert : [run 40711285386](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40711285386), tentative 2, 2 min 24 s au total, dont kind 40 s, pile 54 s, scénario 22 s |
| Refus, incident, idempotence | vérifiés par des scripts ponctuels | non couverts |
| Chemin « vérification en échec » (erreur BPMN) | test unitaire seulement | non couvert : les pannes injectées arrivent en P4 |
| Instance complète visible dans Operate | à faire par Seif | sans objet |

### Écarts et incidents
- Le changement ServiceNow utilise le modèle « Change Registration », et non Normal ou Standard (voir plus haut).
  La classe calculée par la DMN figure dans sa description.
- **Bug de concurrence corrigé.** Pendant un `exec`, `kubernetes.stream` bascule son ApiClient en WebSocket. Un
  provisionnement qui tournait en parallèle échouait donc, puis réussissait au 2e essai. Un client dédié par `exec`
  règle le problème : 0 échec aux exécutions suivantes.
- **Job capté par un worker arrêté.** Le long polling d'un worker arrêté brutalement peut encore capter un job, qui
  reste alors réservé jusqu'à son délai. Ce délai passe à 1 min (3 min pour la vérification). C'est en observant ce
  cas qu'on a constaté un ticket Jira en double (NETOPS-11, resté ouvert), d'où l'idempotence ci-dessus.
- Un seul port par demande (PORT-03), et `traefik/whoami` tient lieu de vrai service.
- **1re tentative de l'e2e en CI en échec**, dès `make verify` : ServiceNow OK, mais Jira 401. Les secrets GitHub
  `JIRA_EMAIL` et `JIRA_API_TOKEN` ne correspondaient pas au `.env`. Seif les a corrigés, et la 2e tentative est
  verte.
- **Données de test créées dans les instances** : RITM0010007 à RITM0010016, CHG0030004 à CHG0030011, NETOPS-6 à
  NETOPS-14.

### Reste
- Job e2e vert en CI : fait. Reste à confirmer que Seif voit une instance complète dans Operate chez lui.
- Prochaine phase : P3, seulement avec l'accord de Seif.

## P3 : Agent de qualification

### Fait
- **Agent `src/agents/qualification.py`**, construit avec le SDK Anthropic 1.13.0 :
  - une boucle d'outils manuelle, avec un seul outil, en lecture seule : la recherche dans le référentiel ;
  - une sortie JSON imposée par un schéma ;
  - des citations, la liste des champs manquants et les questions à poser ;
  - un repli côté serveur en cas de refus du modèle.
- **Fusion déterministe avec le formulaire** : ce que le demandeur a rempli l'emporte, et les manques sont
  recalculés après fusion.
- **Cassettes LLM** : adressées par contenu (`cassettes/llm/`, 62 réponses), avec trois modes (replay, record,
  live), un registre de dépense et un plafond.
- **Processus** :
  - la tâche « Qualifier la demande (agent IA) », puis une passerelle à trois issues : hors périmètre,
    informations manquantes, complète ;
  - en cas de manque, une question au demandeur en commentaire ServiceNow, puis l'attente de sa réponse
    (message corrélé par le numéro de demande) ou d'un délai de 72 h ;
  - à réception de la réponse, une nouvelle qualification.
- **Poller** : il détecte les réponses du demandeur et corrèle le message.
- **Évaluation** :
  - 30 cas synthétiques, figés par une empreinte ;
  - `make eval` produit `results/qualification.json` ;
  - un job CI `eval` vérifie que ce fichier est reproduit octet pour octet à partir des cassettes.
- **`docs/02-architecture-cible.md`** : le choix entre un worker Python et le connecteur AI Agent de Camunda.
- **e2e** : une 3e demande, en texte libre et sans environnement ; le scénario répond à la question de l'agent.

### Mesuré
Source : `results/qualification.json`. Modèle Claude Sonnet 5.5, effort `medium`, 30 cas.

| Mesure | k/n | Wilson 95 % |
|---|---|---|
| Demandes entièrement exactes (8 champs) | 27/27 | 0,875 à 1 |
| Informations manquantes détectées | 8/8 | 0,676 à 1 |
| Fausses alertes de manque | 0/19 | 0 à 0,168 |
| Hors périmètre détecté | 3/3 | 0,439 à 1 |
| Citations présentes dans le référentiel | 71/71 | 0,949 à 1 |
| Décision finale du processus correcte | 30/30 | 0,887 à 1 |

- **Coût** : 0,244 $ pour les 30 demandes, soit 0,0081 $ par demande. Dépense cumulée de la phase (pilote,
  évaluation et e2e) : 0,32 $ sur un budget de 3 $.
- **e2e en local** : 3 demandes sur 3 vont au bout, dont la boucle question puis réponse (6 contrôles sur 6 pour
  la demande en texte libre).

### Vérifié où
| Vérification | PC de Seif (Windows) | GitHub Actions |
|---|---|---|
| `make lint test` (88 tests) | vert | vert : [run 40718460578](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40718460578), commit `875670f` |
| `make eval` rejoué sans clé ni `.env`, identique au passage live | vérifié avec `cmp` | vert : job `eval`, avec `git diff --exit-code results/` sans écart, sous Linux |
| `make e2e` (enregistrement, puis rejeu complet) | vert | vert en rejeu, sans clé Anthropic : [run 40718447071](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40718447071), 3 demandes en 33 s |
| Chemin « vérification en échec » : erreur BPMN puis correction manuelle | exercé pour de vrai (voir ci-dessous) | non couvert |

### Écarts et incidents
- **Course entre « pod prêt » et « règles réseau appliquées ».**
  - Ce qui s'est passé : à la 1re exécution de l'e2e, la zone finance a été vue bloquée alors qu'elle était
    autorisée. L'erreur BPMN a ouvert la tâche de correction ; une fois cette tâche complétée, l'instance s'est
    terminée.
  - Correctif : une zone autorisée dispose désormais de 30 s pour répondre ; une zone interdite n'a aucun délai.
- **Variables d'une erreur BPMN non remontées au processus.** Le compteur de tentatives restait à 1, et le
  formulaire de correction n'aurait pas affiché le constat. Correctif : des mappings de sortie sur l'événement
  d'erreur.
- **Mode record** : il réutilise une cassette déjà enregistrée. La 2e exécution de l'e2e n'a rien coûté.
- **Pilote** : 3 cas live (0,04 $) avant l'évaluation complète. Ils ont été refaits ensuite, parce que la mise
  en cache du prompt système a changé la forme des requêtes.
- **Dépendances** :
  - SDK `anthropic` en 1.13.0, car la branche 2.x a moins de deux semaines ;
  - il repose sur `httpx2`, d'où un transport de cassette dédié.
- **Données de test créées dans les instances** : RITM0010017 à RITM0010024, CHG0030012 à CHG0030019,
  NETOPS-15 à NETOPS-22. Les deux premiers de chaque série viennent de l'e2e de P2 en CI.

### Reste
- Rien pour P3 : `make eval` produit `results/qualification.json` et la CI le rejoue sans clé.
- Prochaine phase : P4, seulement avec l'accord de Seif.

## P4 : Diagnostic et remédiation

### Fait
- **10 pannes reproductibles** (`src/k8s/faults.py`), 2 variantes pour chacune des 5 causes :
  - NetworkPolicy sur une mauvaise zone ou un mauvais port ;
  - `port` ou `targetPort` du Service décalé ;
  - selector avec une faute ou sur un label absent ;
  - image sur un tag ou un registre inexistant ;
  - quota de pods nul, ou déjà atteint.

  Dans le processus, une panne n'est injectée que sur demande (`NETCO_INJECT_FAULT=<panne>:<service>`), et
  seulement au provisionnement.
- **Instantané canonique en lecture seule** (`src/k8s/observe.py`) :
  - ce qu'il contient : objets, pods, endpoints prêts, NetworkPolicy, quotas, événements Warning, journaux,
    résultat des sondes ;
  - ce qu'il retire : noms aléatoires, horodatages, durées, adresses IP.
- **Agent de diagnostic** (`src/agents/diagnosis.py`, Sonnet 5.5) :
  - 6 outils, tous en lecture seule sur l'instantané et sur les runbooks `referentiel/runbooks/` (RB-01 à
    RB-06) ;
  - une réponse par schéma : cause, action de la liste fermée, runbook, explication, preuves.
- **Boucle d'outils commune** aux deux agents (`src/agents/loop.py`). Le refactoring n'a changé aucune requête
  de la qualification : ses cassettes et ses résultats sont restés identiques.
- **Processus** : en cas d'erreur de vérification, l'enchaînement est le suivant.
  1. « Diagnostiquer l'échec (agent IA) ».
  2. « Valider la remédiation » dans Tasklist : appliquer l'action proposée, ou déclarer « corrigé moi-même ».
  3. « Appliquer la remédiation (liste autorisée) ». Elle réapplique uniquement l'objet calculé à partir de la
     demande validée, ou relève le quota, puis laisse une note de travail sur le changement ServiceNow et un
     commentaire Jira.
  4. Nouvelle vérification.

  La tâche manuelle de P2 et son formulaire disparaissent.
- **Évaluation** : capture des 10 cas sur kind (`make eval-capture`), figés par une empreinte. `make eval` lance
  les deux évaluations. Le job CI `eval` vérifie `results/qualification.json` et `results/diagnosis.json`.
- **e2e** : une 4e demande avec la panne `network_policy_zone`. Le scénario vérifie le diagnostic et valide la
  remédiation à la place d'un opérateur. Le service doit être exposé après la 2e vérification.

### Mesuré
Source : `results/diagnosis.json`. Modèle Claude Sonnet 5.5, effort `medium`, 10 pannes.

| Mesure | k/n | Wilson 95 % |
|---|---|---|
| Bonne cause | 10/10 | 0,723 à 1 |
| Bonne action | 10/10 | 0,723 à 1 |
| Cause et action toutes deux justes | 10/10 | 0,723 à 1 |
| Preuves citées présentes dans l'instantané | 35/35 | 0,901 à 1 |

- **Coût** : 0,103 $ pour les 10 diagnostics (0,010 $ chacun). Dépense cumulée depuis P3 : 0,44 $ sur 3 $.
- **Déterminisme de l'instantané** :
  - deux captures successives de la même panne sont identiques à l'octet près ;
  - dans l'e2e, le worker a produit le même instantané que le cas D01 : la cassette du diagnostic a été
    réutilisée, sans nouvel appel.

### Vérifié où
| Vérification | PC de Seif (Windows) | GitHub Actions |
|---|---|---|
| `make lint test` (102 tests) | vert | vert : [run 40726821959](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40726821959), commit `8532c77` |
| `make eval` rejoué sans clé ni `.env`, identique au passage live (deux fichiers) | vérifié avec `cmp` | vert : job `eval`, sans écart sur `results/` |
| `make e2e` avec la panne : enregistrement, puis rejeu complet sans aucune cassette manquante | vert (deux exécutions) | vert en rejeu, sans clé : [run 40726822043](https://github.com/26sneakysnake/infra-request-orchestrator/actions/runs/40726822043), 4 demandes en 66 s |

### Écarts et incidents
- **Le libellé `pod-template-hash`** change à chaque déploiement : il cassait le déterminisme de l'instantané.
  Il est retiré avant la capture.
- **Le quota relevé** : le contrôleur des ReplicaSet recrée le pod de lui-même. La nouvelle vérification attend
  jusqu'à 120 s que le déploiement soit prêt.
- **Données de test créées** : RITM0010025 à RITM0010035, CHG0030020 à CHG0030030, NETOPS-23 à NETOPS-33. Les
  trois premiers de chaque série viennent de l'e2e de P3 en CI.

### Reste
- Rien pour P4 : `results/diagnosis.json` donne la cause et l'action justes 10 fois sur 10, et le job e2e couvre
  une panne.
- Prochaine phase : P5, seulement avec l'accord de Seif.
