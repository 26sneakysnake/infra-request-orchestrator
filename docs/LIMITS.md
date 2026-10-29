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
## Agent de qualification
- Les 30 cas d'évaluation sont synthétiques, et écrits par l'auteur du système. Ils sont probablement plus
  propres que de vraies demandes, donc le score est optimiste.
- Avec si peu de cas, un 27/27 donne un intervalle de Wilson qui va de 0,875 à 1. Ce n'est pas une garantie
  d'exactitude.
- Les cassettes figent les réponses du modèle. Si le prompt, le schéma ou les cas changent, `make eval` échoue
  tant qu'on n'a pas réenregistré les réponses, ce qui demande une clé et coûte de l'argent.
- En mode live, les réponses du modèle peuvent varier d'un appel à l'autre : les modèles 5.5 n'acceptent pas de
  température.
- La réponse du demandeur est repérée comme le premier commentaire qui suit la question du processus et ne
  commence pas par « [NetCo] ». Sur l'instance de démonstration, tous les commentaires sont écrits par le même
  compte.
- Le coût affiché est calculé au tarif du modèle demandé. Une réponse produite par le modèle de repli (après un
  refus) serait facturée autrement.

## Agent de diagnostic
- Les 10 pannes sont injectées volontairement, une seule à la fois, et chacune correspond exactement à un
  runbook. Les vraies pannes sont plus floues : causes multiples, symptômes qui changent avec le temps,
  composants hors du namespace. Un 10/10 sur ce banc ne dit rien de ces cas-là.
- L'agent ne voit qu'un instantané du namespace du service. Le réseau sous-jacent, les nœuds et les autres
  namespaces ne sont pas observés.
- L'instantané ne garde que les événements Warning, et normalise les messages. Un détail utile peut s'y perdre.
- Les remédiations se limitent à une liste fermée : réappliquer un objet calculé, ou relever un quota. Une
  panne qui demande autre chose se termine par « corrigé moi-même » ou `escalate`.
- Dans l'e2e, la validation humaine de la remédiation est simulée par le script.

## Machines virtuelles (vcsim)
- vcsim simule l'API vSphere : la VM existe dans l'inventaire, avec son dossier, sa taille, son réseau et son état
  « allumée », mais elle n'exécute rien. Elle n'a ni système, ni disque utile, ni adresse IP, et aucun lien
  réseau avec le service exposé sur kind.
- L'inventaire est celui de vcsim par défaut : un datacenter, un cluster, un datastore, un seul réseau
  (`VM Network`). Il n'y a ni placement, ni modèle de VM, ni personnalisation du système.
- vcsim garde son inventaire en mémoire : un redémarrage du conteneur efface les VM créées.
- Aucune VM n'est supprimée par le processus : le retrait d'un service n'est pas traité, ni pour la VM ni pour le
  namespace.

## Agent de documentation
- Le contrôle vérifie que chaque valeur technique du texte figure dans les faits, pas que le texte est juste. Une
  valeur présente dans les faits mais mal attribuée (une zone bloquée présentée comme autorisée), ou une phrase
  fausse sans valeur concrète, passe le contrôle.
- Les valeurs sont repérées par motifs : backticks, adresses et réseaux, `port/tcp`, identifiants, namespaces,
  tailles. Une valeur écrite autrement, en toutes lettres par exemple, échappe au contrôle.
- Il n'y a pas de jeu d'évaluation dédié : la mesure porte sur le pilote et sur les 4 rédactions de l'e2e.
- Les documents sont joints aux tickets, pas publiés dans une base de connaissances.

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
- Une vérification en échec passe par le diagnostic de l'agent, puis par une validation humaine (voir plus
  haut).
- La VM et le namespace sont créés en parallèle, mais la vérification ne porte que sur l'exposition Kubernetes :
  la VM est seulement relue dans vcsim par l'e2e.

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
