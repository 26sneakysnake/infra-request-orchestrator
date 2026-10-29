# Démo de 5 minutes

> NetCo est fictive. La démo crée de vrais enregistrements de test dans l'instance ServiceNow de développement et
> dans Jira : 5 demandes, et les changements et tickets qui en découlent. Les appels LLM sont réels : environ
> 0,03 $ par demande, sous le plafond de `.env`.

## La veille (15 min)
1. Se connecter une fois à l'instance ServiceNow, pour la réveiller, et à Jira.
2. Lancer `make verify` : la commande doit afficher ServiceNow OK et Jira OK.
3. Vérifier la dépense LLM dans `out/llm-spend.json`, et le plafond `NETCO_LLM_BUDGET_USD` dans `.env`.
4. Faire une répétition complète en suivant ce document. Prendre les captures (voir plus bas), puis enregistrer
   la vidéo du plan B.

## Le jour même, 15 minutes avant
Dans un terminal PowerShell, à la racine du dépôt :

```powershell
docker compose down -v                  # facultatif : repartir d'un Operate vide (efface l'historique local)
make up kind-up deploy-bpmn             # environ 3 min ; les 6 sondes doivent répondre
make verify
$env:NETCO_INJECT_FAULT = "network_policy_zone:reporting-batch"
make seed                               # affiche les 5 numéros RITM : les noter
make workers                            # laisser tourner pendant toute la démo
```

Une minute plus tard, vérifier dans Operate (http://localhost:8080/operate, `demo`/`demo`) :
- **`catalogue-api`** : instance terminée ;
- **`paiement-front` et `reporting-batch`** : en attente d'approbation ;
- **`facturation-api`** : en attente de la réponse du demandeur ;
- **`legacy-erp`** : refusée.

Ouvrir les onglets : Operate, Tasklist, la demande `facturation-api` dans ServiceNow, le tableau Jira, et le
README du dépôt sur GitHub.

## Le déroulé (5 min)
| Temps | Ce qu'on montre | Ce qu'on dit |
|---|---|---|
| 0:00 – 0:40 | README : diagramme de l'existant, puis diagramme cible | « 9 étapes manuelles et 5 équipes, d'après une hypothèse déclarée. Dans la cible, les humains n'interviennent qu'à trois points de décision. » |
| 0:40 – 1:30 | Operate : l'instance `catalogue-api`, chemin parcouru, variables `qualification` et `llmCostUsd`. Puis Jira : le ticket terminé et la fiche jointe | « Une demande standard passe sans intervention humaine. L'agent a qualifié la demande en citant le référentiel, la DMN l'a classée standard. La fiche est rédigée, contrôlée, puis jointe. » |
| 1:30 – 2:15 | Tasklist : « Approuver le changement » de `reporting-batch`, approuver avec un commentaire. Dans Operate, la VM se crée en parallèle de Kubernetes | « Le CAB décide. La classe du changement vient d'une table DMN relue par le CAB, pas d'un agent. » |
| 2:15 – 3:15 | La vérification échoue (panne injectée). Tasklist : « Valider la remédiation » montre la cause, les preuves, le runbook RB-01 et l'action. Appliquer, puis suivre la deuxième vérification dans Operate | « L'agent lit un instantané, il ne peut rien modifier. Il propose une action d'une liste fermée, et rien ne s'exécute sans validation humaine. » |
| 3:15 – 3:45 | ServiceNow : la question posée sur `facturation-api`. Répondre en commentaire « C'est pour la recette. » ; l'instance repart dans les 10 s | « Quand une information manque, le processus la demande au bon endroit et attend 72 h au plus. » |
| 3:45 – 4:30 | README, section « Résultats » | « Chaque chiffre vient d'un fichier produit par un script, en k/n avec l'intervalle de Wilson. L'existant est une hypothèse, je ne la soustrais pas des mesures. » |
| 4:30 – 5:00 | `docs/03-feuille-de-route.md` et « Ce que ce projet ne montre pas » | « Trois vagues, avec des indicateurs de sortie. Le laboratoire est local et le dit : kind, vcsim, NetworkPolicy. » |

Si l'agent juge `facturation-api` urgente (« assez urgent » dans le texte), elle passe ensuite par
l'approbation. C'est le comportement attendu, à commenter si la question vient.

## Captures pour le README
Les prendre pendant la répétition, les enregistrer sous ces noms dans `docs/img/captures/`, puis lancer
`make readme` et committer :

| Fichier | Écran |
|---|---|
| `operate-instance.png` | Operate : l'instance terminée de `reporting-batch`, avec le chemin parcouru (la branche VM et la boucle de remédiation) |
| `tasklist-remediation.png` | Tasklist : la tâche « Valider la remédiation » ouverte, avec la cause et les preuves |
| `servicenow-change.png` | ServiceNow : le changement clos, avec ses deux pièces jointes et ses notes de travail |
| `jira-issue.png` | Jira : le ticket terminé, avec ses pièces jointes et le lien vers le changement |

Ne capturer ni identifiant ni mot de passe, ni l'adresse complète de l'instance si on préfère la garder privée.

## Plan B
| Problème | Réponse |
|---|---|
| ServiceNow en veille ou injoignable | Se connecter à l'instance pour la réveiller (2 à 3 min). Sinon, passer la vidéo. |
| Docker ou kind ne démarre pas | Passer la vidéo de 3 minutes, puis le README (captures, résultats). |
| Les workers répètent « Expected to find process definition … 'expose_service' » | Les modèles ne sont pas déployés. Lancer `make deploy-bpmn` dans un autre terminal, sans arrêter les workers : les demandes repartent dans les 10 s. |
| Un agent ne répond pas (réseau, plafond atteint) | L'incident apparaît dans Operate : le montrer, c'est aussi la démo des relances. Puis passer la vidéo. |
| Plus de temps que prévu | Sauter l'étape 3:15 (réponse du demandeur). |

**La vidéo du plan B** (3 min, enregistrée la veille avec Xbox Game Bar, Win+Alt+R) reprend les étapes de 0:40
à 3:15. Elle est hébergée hors du dépôt. Lien : *à ajouter par Seif*.

## Après la démo
Ctrl+C dans le terminal des workers, puis `make kind-down down`.
