# Guide opérationnel : faire tourner le processus d'exposition

> Laboratoire de démonstration (NetCo fictive) : Camunda 8.10 en configuration Docker légère, cluster kind, vcsim.
> Les commandes sont celles du `Makefile`.

## Démarrer et arrêter
| Action | Commande | Contrôle |
|---|---|---|
| Démarrer la pile | `make up` | les 6 sondes répondent (santé du moteur, API REST, Operate, Tasklist, Connectors, vcsim) |
| Démarrer le cluster | `make kind-up` | les pods `probe` des zones sont prêts |
| Déployer les modèles | `make deploy-bpmn` | « Deployed 4 resources » |
| Vérifier ServiceNow et Jira | `make verify` | lecture seule, échoue tôt si l'instance dort |
| Lancer les workers | `make workers` | une seule fenêtre ; Ctrl+C pour arrêter |
| Tout arrêter | `make kind-down` puis `make down` | les volumes Camunda sont conservés |

**Règle.** Il ne faut jamais lancer deux jeux de workers en même temps (par exemple `make workers` pendant
`make e2e`), ni en local pendant un e2e en CI : ils se disputeraient les mêmes jobs et la même instance
ServiceNow.

## Suivre
- **Operate** (http://localhost:8080/operate) : instances, variables (`qualification`, `diagnosis`,
  `documentation`, `llmCostUsd`) et incidents.
- **Tasklist** (http://localhost:8080/tasklist) : approbations du CAB (groupe `cab`) et validations de
  remédiation (groupe `ops`).
- **Journal des workers** : la sortie de `make workers`, ou `out/e2e-workers.log` pour un e2e.
- **Mesures** : `make metrics` écrit `results/metrics.json`.

## Traiter un incident Camunda
Un job en échec est relancé 3 fois, à 10 s d'intervalle. Ensuite, Operate affiche un **incident** sur l'instance.
1. Lire le message de l'incident dans Operate, puis la ligne correspondante du journal des workers.
2. Corriger la cause (voir le tableau ci-dessous).
3. Dans Operate, relancer l'incident (« Retry »). Les handlers sont idempotents : un changement, un ticket ou une
   pièce jointe déjà créés ne sont pas dupliqués.

| Symptôme | Cause probable | Action |
|---|---|---|
| `ServiceNowError ... non-JSON response` | instance développeur en veille | se connecter à l'instance pour la réveiller, puis relancer |
| ServiceNow 401 | mot de passe changé, ou rôle `snc_basic_auth_api_access` retiré | corriger `.env` et les secrets GitHub, ou le rôle |
| Jira 401 | jeton d'API expiré | créer un jeton, mettre à jour `.env` et les secrets |
| `CassetteMiss` | rejeu d'un prompt jamais enregistré (variables différentes de l'enregistrement) | en démo, passer en `NETCO_LLM_MODE=live` ; pour la CI, réenregistrer (voir plus bas) |
| `BudgetExceeded` | plafond de dépense LLM atteint (`out/llm-spend.json`) | décision humaine : relever `NETCO_LLM_BUDGET_USD` ou attendre |
| Instance bloquée sur un job `CREATED` | aucun worker ne tourne | relancer `make workers` |
| Journal des workers : `Expected to find process definition with process ID 'expose_service'` | modèles non déployés (après `docker compose down -v`, par exemple) | `make deploy-bpmn`, sans arrêter les workers : la demande est rouverte et repart au passage suivant |
| Vérification réseau en échec | panne réelle, ou panne injectée (`NETCO_INJECT_FAULT`) | suivre la tâche « Valider la remédiation » dans Tasklist |
| Documentation de source `gabarit` | l'agent a écrit une valeur absente des faits, ou n'a pas répondu | rien d'urgent : le gabarit est complet ; lire `documentation.problems` |

## Valider une remédiation (opérateur)
La tâche affiche le constat, la cause proposée, la confiance, le runbook, les preuves citées et l'action.
1. Vérifier que les preuves correspondent au constat. Le compteur « preuves retrouvées » doit être plein.
2. Ouvrir le runbook cité (`referentiel/runbooks/`).
3. Choisir l'une des deux réponses :
   - **Appliquer** : le processus réapplique l'objet calculé à partir de la demande validée ;
   - **J'ai corrigé moi-même** : le processus relance seulement la vérification.

   Si l'action proposée est `escalate`, rien n'est exécuté.

## Entretien courant
- **Ajouter ou modifier une règle.** Éditer `referentiel/netco.yaml` et la section Markdown du même identifiant,
  puis lancer `make test`. Si la qualification en dépend, ajouter un cas d'évaluation, puis lancer
  `make eval-live` et `make eval-freeze`.
- **Changer un prompt ou le modèle.** Lancer `make eval-live` (coût affiché, plafond appliqué), comparer
  `results/`, puis réenregistrer l'e2e : `NETCO_LLM_MODE=record make e2e`, puis `NETCO_LLM_MODE=replay make e2e`
  pour vérifier qu'aucune cassette ne manque.
- **Faire tourner les secrets.** Mettre à jour `.env` (jamais commité) et les secrets GitHub, puis lancer
  `make verify`.
- **Nettoyer les données de test.** Chaque e2e crée 4 demandes, 4 changements et 4 tickets Jira : il faut les
  archiver ou les fermer de temps en temps dans les outils.

## Limites à connaître
Les limites détaillées sont dans [LIMITS.md](LIMITS.md). En exploitation réelle, il faudrait au minimum :
- une configuration Camunda complète, avec authentification et licence de production ;
- un compte d'intégration ServiceNow dédié, en OAuth ;
- des webhooks au lieu de l'interrogation ;
- une supervision des workers.
