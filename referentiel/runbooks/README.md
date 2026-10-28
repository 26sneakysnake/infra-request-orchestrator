# Runbooks NetCo : échecs de vérification d'une exposition

> NetCo est une entreprise fictive. Ces runbooks sont inventés pour la démonstration.

Chaque runbook décrit un symptôme constaté après le provisionnement, les vérifications à faire, et **l'action
autorisée**. L'agent de diagnostic les consulte. Il ne peut proposer qu'une action de cette liste, et un humain
la valide avant que le processus l'applique.

| Action autorisée | Effet |
|---|---|
| `reapply_network_policy` | Réapplique la NetworkPolicy calculée à partir de la demande validée |
| `reapply_service` | Réapplique le Service calculé à partir de la demande validée (ports, selector) |
| `reapply_deployment` | Réapplique le déploiement approuvé (image, labels, ports) |
| `raise_pod_quota` | Relève le quota de pods du namespace pour laisser démarrer le service |
| `escalate` | Aucune action automatique : l'équipe plateforme prend la main |
