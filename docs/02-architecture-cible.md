# Architecture cible

> Document complété en phase P7. Cette première version consigne le choix fait en P3 pour l'agent de
> qualification.

## Agent de qualification : connecteur AI Agent de Camunda ou worker Python ?

Camunda 8.10 propose un connecteur **AI Agent**. Il prend en charge Anthropic (API native ou point
d'accès compatible). Ses outils sont les activités d'un sous-processus ad hoc, sa réponse peut être du JSON
structuré, et sa mémoire de conversation est gardée en variable de processus. Le projet a retenu à la place
un **worker Python** qui appelle l'API Anthropic avec le SDK officiel.

| Critère | Connecteur AI Agent | Worker Python (retenu) |
|---|---|---|
| Boucle de l'agent visible dans Operate | Oui : chaque appel d'outil est une activité du sous-processus | Non : une seule tâche de service. Le détail (citations, coût, nombre de tours) est dans les variables |
| Code à maintenir | Aucun : configuration BPMN et FEEL | Environ 250 lignes, testées |
| Sortie structurée | JSON parsé en contexte FEEL | Schéma JSON imposé par l'API (`output_config.format`) |
| Évaluation sur 30 cas | Un moteur et une instance par cas | Appel direct de la fonction : 30 cas rejoués en quelques secondes |
| CI sans clé d'API | Exige un proxy de rejeu derrière le point d'accès compatible | Cassettes adressées par contenu, rejouées par un transport HTTP |
| Contrôles déterministes après le modèle | À écrire en FEEL ou dans une tâche suivante | Dans le même code : citations vérifiées dans le référentiel, fusion avec le formulaire, champs manquants recalculés |
| Coût | Facture du fournisseur | Mesuré à chaque appel, avec un plafond de dépense cumulée |

**Décision.** Ce projet exige que chaque chiffre publié soit reproductible à partir de fichiers versionnés, et
que la CI tourne sans clé (règles 3 et 6 de `CLAUDE.md`). Le worker satisfait ces deux exigences directement.
Le connecteur reste le bon choix pour une équipe qui préfère le low-code et veut voir chaque appel d'outil dans
Operate. Il sera réévalué pour l'agent de diagnostic (P4) : la visibilité de la boucle y pèse davantage, car un
humain doit valider la remédiation proposée.

**Paramètres retenus** :
- modèle Claude Sonnet 5.5 (`claude-sonnet-5-5`), effort `medium` ;
- un seul outil en lecture seule, `search_referentiel` ;
- au plus 6 tours ;
- en cas de refus, repli côté serveur (`fallbacks: "default"`) ;
- un plafond de dépense cumulée de 3 $ pendant la construction.

Le modèle se change par `NETCO_LLM_MODEL`. Le coût mesuré d'une demande figure dans
`results/qualification.json`.

**Garde-fous** :
- L'agent ne décide de rien. Ses champs passent par la validation déterministe du référentiel, puis par la
  table DMN.
- Un champ rempli par le demandeur dans le formulaire l'emporte toujours sur la proposition de l'agent.
- La liste des informations manquantes est recalculée après fusion, donc l'agent ne peut pas masquer un manque.
- Une citation n'est comptée que si l'extrait figure réellement dans le référentiel.

## Agent de diagnostic : même choix, réévalué en P4

Avec le connecteur AI Agent, on aurait vu chaque appel d'outil dans Operate, ce qui a de la valeur quand un
humain doit valider une remédiation. Le projet garde pourtant le worker, pour deux raisons :
- **la reproductibilité** : l'agent travaille sur un **instantané canonique** du namespace, pris une fois au
  moment de l'échec (noms aléatoires, horodatages et adresses IP retirés). Le même état produit donc exactement
  les mêmes requêtes, et l'évaluation sur 10 pannes comme l'e2e se rejouent en CI sans clé ;
- **la séparation entre lecture et écriture**, qui est nette :
  - l'agent n'a que des outils de lecture sur l'instantané et les runbooks ;
  - il choisit une action dans une **liste fermée** (`reapply_network_policy`, `reapply_service`,
    `reapply_deployment`, `raise_pod_quota`, `escalate`) ;
  - un humain valide dans Tasklist ;
  - un autre worker applique l'action. Il ne réapplique jamais que la configuration calculée à partir de la
    demande validée, et n'exécute aucune commande libre.

Ce qui reste visible dans Operate : la tâche de diagnostic, la décision de l'opérateur, et les variables
`diagnosis` (cause, preuves, runbook, coût) et `remediationsApplied`.

## Agent de documentation : un seul appel, contrôlé, avec un gabarit en secours (P5)

La rédaction n'a besoin d'aucun outil : tout ce que l'agent doit savoir est déjà dans les variables du
processus. Le worker les met en forme dans un **dossier de faits** (demande, classe et approbation, objets
Kubernetes, VM, vérification, incident et remédiation s'il y en a eu), et l'agent répond en un seul appel par un
schéma à deux champs : `fiche_service` et `compte_rendu`.

Trois garde-fous :
- **des marqueurs** : les numéros de la demande, du changement et du ticket Jira, et la date, n'apparaissent
  dans le dossier que sous la forme `{{ritmNumber}}`, `{{changeNumber}}`, `{{jiraKey}}` et `{{date}}`. Le
  worker les remplace après la rédaction. L'agent ne peut donc pas se tromper de numéro, et le prompt reste le
  même d'une exécution à l'autre, ce qui permet de le rejouer en CI ;
- **un contrôle déterministe** : chaque valeur concrète du texte (entre backticks, adresses et réseaux,
  `port/tcp`, identifiants, namespaces, tailles) doit figurer dans le dossier. Un numéro de ticket écrit en dur,
  un marqueur inconnu ou un terme interdit (une plateforme que le laboratoire n'est pas) fait aussi échouer le
  contrôle ;
- **un gabarit** : si le contrôle échoue, ou si l'agent ne répond pas, les documents sont produits par un gabarit
  déterministe. Une demande close a donc toujours sa documentation, et la variable `documentation` indique la
  source (`agent` ou `gabarit`) et les valeurs refusées.

La VM suit la même règle que Kubernetes : aucun agent n'y touche. Le worker `create-vm` la crée sur vcsim à
partir du référentiel (VM-01), en parallèle du provisionnement Kubernetes.
