# Classement des changements et approbations

## CHG-01 : classes de changement
Chaque demande conforme devient un changement, classé par une table de décision (DMN `change_class`) :

| Condition (dans cet ordre) | Classe | Approbation |
|---|---|---|
| Changement urgent demandé (incident en cours) | urgent | Approbation prioritaire |
| Environnement `prod` | normal | Approbation du CAB |
| Exposition `externe` | normal | Approbation du CAB |
| Port sensible (PORT-05) | normal | Approbation du CAB |
| Autres cas | standard | Aucune, changement pré-approuvé |

## CHG-02 : approbation
L'approbation est une tâche humaine du groupe `cab` dans Tasklist. Un refus clôt la demande dans ServiceNow avec le
motif de l'approbateur. L'IA ne décide jamais d'une approbation.

## CHG-03 : traçabilité
Chaque changement exécuté est enregistré dans ServiceNow (modèle « Change Registration », réservé aux changements
automatisés) et lié au ticket Jira de mise en œuvre.
