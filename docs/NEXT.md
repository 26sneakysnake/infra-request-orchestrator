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
- Jeu d'évaluation tiré de vraies demandes anonymisées, plus difficile que les 30 cas synthétiques. Juge LLM
  pour la qualité des questions posées au demandeur.
- Variante de l'agent de qualification sur le connecteur AI Agent de Camunda, pour comparer avec le worker
  Python sur les mêmes cas.
- Banc de diagnostic plus difficile : pannes combinées, pannes intermittentes, pannes hors du namespace (DNS,
  nœud), et cas où la bonne réponse est `escalate`.
- Retour d'expérience : conserver les diagnostics validés ou corrigés par les opérateurs, pour enrichir les
  runbooks et le jeu d'évaluation.
- Retrait d'un service : suppression de la VM et du namespace, avec son propre changement.
- VM plus réaliste, hors vcsim : clone d'un modèle, adresse IP attribuée par un IPAM, personnalisation du
  système, et vérification de la joignabilité de la VM.
- Documentation publiée dans une base de connaissances (ServiceNow Knowledge ou Confluence) plutôt qu'en pièce
  jointe, et évaluation de sa fidélité sur un jeu de dossiers, avec un juge pour les erreurs d'attribution.
