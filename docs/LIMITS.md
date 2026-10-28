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

## ServiceNow et Jira
- ServiceNow tourne sur une instance développeur personnelle, réservée à l'apprentissage. ServiceNow peut la
  reprendre après une période d'inactivité ; `make seed` recrée alors l'article de catalogue et les demandes.
- Les appels API utilisent le compte admin en authentification Basic, avec le rôle `snc_basic_auth_api_access`.
  Une vraie intégration utiliserait un compte de service dédié, limité aux rôles nécessaires, avec OAuth.
- Jira Cloud est en offre gratuite, avec un jeton d'API personnel à durée limitée.
- `make seed` crée 5 nouvelles demandes à chaque lancement. C'est voulu : des données fraîches pour la démo.
- Les tests rejouent des réponses enregistrées une seule fois : ils ne détectent pas une évolution des API
  survenue depuis. `make record` les rafraîchit, mais crée alors des enregistrements de test dans les instances.

## Portée
- Ce projet est une démonstration construite en quelques jours. Il ne remplace pas une expérience d'exploitation
  d'infrastructures réelles.
