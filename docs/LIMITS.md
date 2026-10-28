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
- Kubernetes tourne sur kind : un cluster local d'un seul nœud, pas une plateforme de conteneurs d'entreprise.
- Le pare-feu est modélisé par des NetworkPolicy Kubernetes. Une zone réseau NetCo est un namespace, et une demande
  ouvre la zone entière, pas seulement le sous-réseau demandé.
- La charge déployée est un petit serveur HTTP (`traefik/whoami`) qui écoute sur le port demandé, pas le vrai
  service. Une demande = un port TCP.
- Aucun appel à un LLM avant P3.

## Processus
- Les demandes arrivent par interrogation de ServiceNow toutes les 10 s. Il n'y a pas de webhook, car la pile
  locale n'a pas d'adresse publique.
- Dans l'e2e, l'approbation du CAB est **simulée** par le script, sans humain. En démonstration, elle se fait dans
  Tasklist.
- Le changement ServiceNow suit le modèle « Change Registration » (changement automatisé, sans approbation
  ServiceNow) : l'approbation a lieu dans Camunda.
- Il ne faut pas lancer `make workers` en local pendant un e2e en CI : les deux visent la même instance
  ServiceNow.
- Chaque exécution de l'e2e crée de vrais enregistrements de test (demandes, changements, tickets Jira). Si
  l'instance ServiceNow est en veille, le job échoue dès la première étape (`make verify`).
- Une vérification en échec ouvre une tâche humaine de correction. Le diagnostic assisté arrive en P4.

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
