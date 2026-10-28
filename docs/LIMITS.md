# Limites

Ce que le projet ne fait pas, ou fait de façon simplifiée. Complété à chaque phase.

## Données
- NetCo est fictive. Les demandes, le référentiel et les tickets sont synthétiques.

## Plateforme locale
- Camunda 8.10 tourne avec la configuration Docker Compose légère officielle : un seul nœud, stockage secondaire
  H2, API REST et gRPC sans authentification, compte `demo/demo`. Camunda la destine au développement local et à
  l'évaluation. Elle ne dit rien de la tenue en charge, de la haute disponibilité ni de la sécurité d'une vraie
  plateforme.
- VMware est simulé par vcsim, le simulateur de l'API vSphere du projet govmomi. Aucun serveur VMware réel n'est
  utilisé.
- Pas encore de Kubernetes (kind arrive en P2), ni d'appel à un LLM (pas avant P3).

## Portée
- Ce projet est une démonstration construite en quelques jours. Il ne remplace pas une expérience d'exploitation
  d'infrastructures réelles.
