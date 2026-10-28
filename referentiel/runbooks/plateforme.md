# Runbooks plateforme

## RB-04 : image introuvable
Symptômes : le déploiement n'est jamais prêt. Les pods restent en attente avec `ImagePullBackOff`, et des
événements Warning `Failed` ou `BackOff` mentionnent le tirage de l'image.
Vérifications : comparer l'image du déploiement avec l'image approuvée (`traefik/whoami:v1.12.0` dans le
laboratoire). Un tag inexistant ou un registre injoignable empêche le démarrage.
Cause : image introuvable ou inaccessible (`image`).
Action autorisée : `reapply_deployment`.

## RB-05 : quota du namespace atteint
Symptômes : le déploiement n'est jamais prêt et aucun pod du service n'existe. Des événements Warning
`FailedCreate` sur le ReplicaSet indiquent `exceeded quota`.
Vérifications : lire le ResourceQuota du namespace. Un quota de pods à 0, ou déjà consommé par un autre pod,
bloque la création.
Cause : quota de pods atteint (`quota`).
Action autorisée : `raise_pod_quota`.

## RB-06 : cause hors des runbooks
Symptômes : aucun des runbooks RB-01 à RB-05 n'explique les constats, ou les preuves se contredisent.
Cause : autre (`other`).
Action autorisée : `escalate`. Aucune action automatique : l'équipe plateforme analyse le namespace.
