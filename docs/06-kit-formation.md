# Kit de formation : atelier de 2 heures

> Pour les équipes réseau, plateforme et service desk de NetCo (fictive). Prérequis : le laboratoire lancé par
> le formateur (`make up kind-up deploy-bpmn`), et Camunda Modeler installé sur chaque poste.

## Objectifs
À la fin de l'atelier, chaque participant sait :
1. lire un modèle BPMN : tâches, passerelles, événements, couloirs, erreurs ;
2. suivre une demande dans Operate et traiter une tâche dans Tasklist ;
3. modéliser un processus simple de son équipe dans Camunda Modeler ;
4. écrire une règle de décision dans une table DMN ;
5. expliquer ce que les agents IA font, et ce qu'ils ne font pas.

## Déroulé
| Durée | Séquence | Support |
|---|---|---|
| 0:00 – 0:15 | Pourquoi orchestrer : l'existant et ses irritants | [01-diagnostic-as-is.md](01-diagnostic-as-is.md), diagramme as-is |
| 0:15 – 0:35 | Démonstration : une demande de ServiceNow à Jira, en direct | Operate, Tasklist, ServiceNow, Jira |
| 0:35 – 1:05 | **Exercice 1** : modéliser le renouvellement d'un certificat | Camunda Modeler |
| 1:05 – 1:10 | Pause | |
| 1:10 – 1:35 | **Exercice 2** : ajouter une règle à la table de classement | `bpmn/change_class.dmn` |
| 1:35 – 1:50 | **Exercice 3** : valider (ou refuser) une remédiation proposée par l'agent | Tasklist, runbooks |
| 1:50 – 2:00 | Questions, et ce que chaque équipe veut modéliser ensuite | [03-feuille-de-route.md](03-feuille-de-route.md) |

## Exercice 1 : modéliser le renouvellement d'un certificat TLS (30 min, par binômes)
**Énoncé.**
- Trente jours avant l'expiration d'un certificat, l'équipe plateforme doit en obtenir un nouveau, le déployer
  et vérifier que le service répond avec le bon certificat.
- Si l'autorité de certification refuse la demande, l'équipe sécurité est prévenue.
- Si la vérification échoue, le certificat précédent est remis en place.

**Consignes.**
- Un couloir par équipe.
- Un événement de début temporisé.
- Une passerelle exclusive pour le refus.
- Une erreur en bordure de la tâche de vérification.
- Nommer chaque tâche avec un verbe à l'infinitif.

**Corrigé en esquisse.**
- Début temporisé (« J-30 »), puis « Demander le certificat ».
- Passerelle « Accepté ? » : si non, « Prévenir la sécurité », puis fin.
- Si oui : « Déployer le certificat », puis « Vérifier le service ».
- Erreur en bordure « Vérification en échec » : « Remettre le certificat précédent », puis fin en échec.
- Sinon : « Clore le changement », puis fin.

**Points de discussion.**
- Quelles tâches peut-on automatiser tout de suite ?
- Laquelle doit rester humaine ?
- Où se trouve aujourd'hui la date d'expiration ?

## Exercice 2 : une règle dans la table DMN (25 min)
**Énoncé.** Le CAB décide qu'une ouverture vers un port sensible (base de données) en `dev` reste un
changement `standard`, sauf si la demande est externe.

**Consignes.**
- Ouvrir `change_class.dmn` dans Camunda Modeler.
- Ajouter la règle au bon endroit : la table est en politique `FIRST`, la première règle qui s'applique gagne.
- Écrire les deux cas de test correspondants.

**Corrigé.**
- La table contient 5 règles : urgent, prod, exposition externe, port sensible, autres cas.
- La nouvelle règle se place **après** « exposition externe » et **avant** « port sensible ».
- Ses entrées : `environment = "dev"`, `sensitivePort = true`, `exposure = "interne"`. Sa sortie : `standard`.
- Les deux cas de test, non urgents :
  - `dev`, sensible, interne donne `standard` ;
  - `dev`, sensible, externe donne `normal`.

**Discussion.**
- Pourquoi cette décision est-elle dans une table relue par le CAB, et pas dans un agent IA ?
- Qui approuve la modification ? (voir [04-gouvernance.md](04-gouvernance.md))

## Exercice 3 : valider une remédiation (15 min)
**Mise en place.** Le formateur lance les workers avec une panne injectée, par exemple :
`$env:NETCO_INJECT_FAULT = "network_policy_zone:catalogue-api"`.

**Consignes.** Dans Tasklist, ouvrir « Valider la remédiation », puis :
1. relire les preuves citées par l'agent ;
2. ouvrir le runbook cité ;
3. décider, puis suivre la nouvelle vérification dans Operate.

**À retenir.**
- L'agent ne voit qu'un instantané et ne peut rien modifier.
- L'action vient d'une liste fermée.
- Sans validation humaine, rien ne s'exécute.

## Évaluation de l'atelier
- Chaque binôme repart avec son modèle de l'exercice 1, à relire en revue
  ([04-gouvernance.md](04-gouvernance.md)).
- Un questionnaire de 5 questions en fin de séance, une par objectif. Seuil visé : 4 bonnes réponses sur 5.
- Trois semaines plus tard, chaque équipe propose un processus à modéliser pour la vague 2.
