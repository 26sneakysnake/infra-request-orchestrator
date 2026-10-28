# Idées hors périmètre

Notées pour plus tard, volontairement non traitées : un seul processus bien fait passe avant tout le reste.

- Configuration Docker Compose complète de Camunda (Keycloak, Management Identity, Optimize) avec authentification
  OIDC des API.
- Déploiement de Camunda par Helm sur le cluster kind, plus proche d'une installation Kubernetes réelle.
- Compte d'intégration ServiceNow dédié, limité aux rôles nécessaires, avec OAuth au lieu d'admin en
  authentification Basic.
- Déclenchement par webhook ServiceNow (connecteur entrant Camunda) au lieu de l'interrogation, une fois la pile
  joignable.
- Plusieurs ports par demande, et ports UDP.
- Modèle de changement standard ServiceNow dédié (« Exposition de service standard ») pour les changements
  pré-approuvés.
