# Gouvernance : qui décide, comment le modèle évolue, ce qu'on surveille

> NetCo est fictive. Les rôles ci-dessous sont ceux qu'il faudrait nommer. Les garde-fous IA décrits existent
> dans le dépôt.

## Rôles
| Activité | Propriétaire du processus | Équipe automatisation | Équipe réseau | Plateforme et virtualisation | CAB |
|---|---|---|---|---|---|
| Règles du référentiel (`referentiel/`) | A | C | R | R | I |
| Modèle BPMN et table DMN | A | R | C | C | C |
| Workers, intégrations, agents | I | A/R | C | C | – |
| Classement des changements (DMN) | A | R | C | C | C |
| Approbation d'un changement normal | I | – | C | C | A/R |
| Validation d'une remédiation proposée par l'agent | I | – | A/R | R | – |
| Indicateurs et revue mensuelle | A/R | R | C | C | I |

R : réalise, A : approuve, C : consulté, I : informé. Le **propriétaire du processus** est une personne nommée
(par exemple le responsable de l'ingénierie réseau). Il arbitre le périmètre et accepte les évolutions du modèle.

## Cycle de vie du modèle
- **Tout est dans git.** Le BPMN, la DMN, les formulaires, le référentiel, les prompts et les cas d'évaluation.
  Rien ne se modifie directement dans un moteur.
- **Toute modification passe par une revue (pull request).** Deux relectures : l'équipe automatisation, et le
  métier concerné (réseau pour une règle, CAB pour la DMN).
- **La CI bloque ce qui casse.**
  - Les tests vérifient que chaque type de tâche a son worker, que chaque élément est dessiné, que les
    formulaires et décisions appelés existent, et que le référentiel YAML et sa documentation restent alignés.
  - Les évaluations des agents doivent redonner exactement les résultats publiés.
  - Le scénario de bout en bout tourne sur les vrais outils (ServiceNow, Jira).
- **Versionnement.** Camunda versionne chaque déploiement. Les instances en cours finissent sur leur version, et
  les nouvelles prennent la dernière. Une migration d'instances se décide au cas par cas, jamais par défaut.
- **Une règle métier = un identifiant.** Exemples : `PORT-01`, `CHG-02`, `VM-01`. L'identifiant est cité dans les
  messages de refus et par l'agent. Ajouter une règle, c'est l'ajouter au YAML, l'expliquer dans le Markdown et
  faire passer le test de cohérence.

## Indicateurs suivis
Calculés par `make metrics` depuis l'historique Camunda, et revus chaque mois par le propriétaire du processus :
- **délai de bout en bout**, médiane et pire cas, par classe de changement ;
- **temps de traitement hors attente humaine**, qui montre où la machine attend ;
- **part des activités automatisées**, et **demandes traitées sans intervention humaine** (k/n) ;
- **interventions humaines par type** : approbations CAB, réponses du demandeur, validations de remédiation ;
- **coût LLM par demande**, médiane et maximum ;
- **qualité des agents** :
  - qualification exacte et diagnostic juste, sur les jeux d'évaluation ;
  - rédactions acceptées par le contrôle ;
- **incidents Camunda** (jobs en échec après relances), par type de tâche.

Un indicateur se publie avec son effectif (k/n) et, pour une proportion, son intervalle de confiance. Un chiffre
sans source n'est pas publié.

## Garde-fous IA
**Le principe : l'IA propose, le processus décide.** Les mécanismes en place :
1. **Décisions déterministes.**
   - Le classement des changements passe par une table DMN, jamais par un agent.
   - La conformité est vérifiée par le référentiel, jamais par l'agent de qualification.
2. **Un humain valide avant toute correction.** L'agent de diagnostic propose une action ; un opérateur la
   valide dans Tasklist ; le processus l'applique ensuite.
3. **Une liste fermée d'actions.** Elle ne fait que réappliquer la configuration calculée à partir de la demande
   validée, ou relever un quota. Aucune commande libre.
4. **Des agents en lecture seule.** Les outils de l'agent de diagnostic lisent un instantané figé. Aucun agent
   n'a de droit d'écriture sur l'infrastructure.
5. **Le formulaire l'emporte sur l'agent.** Une valeur saisie par le demandeur n'est jamais remplacée.
6. **Une rédaction contrôlée.** Toute valeur absente des variables du processus fait rejeter la documentation,
   et un gabarit prend le relais. Les numéros de ticket sont insérés par le worker.
7. **Des agents évalués avant chaque changement.** Les cas sont figés par empreinte, les réponses enregistrées et
   rejouées en CI. Un changement de prompt ou de modèle exige un nouveau passage des évaluations, publié avec ses
   intervalles.
8. **Un coût plafonné.** Un budget cumulé est vérifié avant chaque appel réel. Au-delà, l'appel est refusé.
9. **Une traçabilité complète.** Le modèle, le nombre de tours, le coût, les citations et les preuves sont
   enregistrés dans les variables de l'instance, consultables dans Operate.

## Rituels
- **Revue mensuelle** (30 min) : indicateurs, incidents, évolutions demandées du référentiel.
- **Revue trimestrielle des agents** : nouveaux cas d'évaluation tirés des diagnostics validés ou corrigés,
  puis décision de garder, changer ou retirer un agent.
- **Après chaque incident de processus** : une note dans le guide opérationnel
  ([05-guide-operationnel.md](05-guide-operationnel.md)) et, si besoin, un cas de test.
