# Feuille de route : trois vagues

> NetCo est fictive. Les durées des vagues sont des propositions. Les chiffres du laboratoire viennent de
> `results/`, et ceux de l'existant sont des hypothèses (`hypotheses/as-is.yaml`).

## Le pitch en 5 minutes
1. **Le constat** (1 min).
   - L'exposition d'un service compte 9 étapes manuelles et traverse 5 acteurs.
   - On suppose de 3 à 20 jours ouvrés et de 185 à 240 minutes de travail humain par demande.
   - Personne ne mesure ces délais aujourd'hui ([diagnostic](01-diagnostic-as-is.md)).
2. **La cible** (1 min).
   - Un processus BPMN orchestré par Camunda, entre ServiceNow, Jira, la plateforme de conteneurs et la
     virtualisation.
   - Les règles sont écrites une fois dans un référentiel, et le classement des changements dans une table DMN.
   - Les humains interviennent à trois points de décision seulement ([architecture](02-architecture-cible.md)).
3. **La preuve** (1 min). Le laboratoire tourne de bout en bout sur de vrais ServiceNow et Jira.
   - Sur 20 demandes avec de vrais appels LLM, 20 sont allées au bout.
   - Une demande standard est traitée en 26,0 s (médiane).
   - 210 activités sur 225 sont automatiques.
   - Le coût LLM médian est de 0,0255 $ par demande (`results/metrics.json`).
   - Ces chiffres valent pour un poste de laboratoire, avec des approbations simulées.
4. **Le plan** (1 min) : trois vagues, chacune avec ses indicateurs de sortie (ci-dessous).
5. **Les conditions** (1 min) :
   - un propriétaire de processus nommé ;
   - la licence de production Camunda chiffrée ;
   - les accès API au pare-feu et aux plateformes ;
   - une première mesure réelle des délais avant la vague 1, pour juger ensuite sur pièces.

## Vague 1 (mois 0 à 3) : l'exposition d'un service, de bout en bout
- **Périmètre.**
  - Le processus du laboratoire, branché sur les vrais systèmes : pare-feu par API, plateforme de conteneurs,
    plateforme de virtualisation.
  - Les demandes standard d'abord, puis les changements normaux, avec le CAB dans Tasklist.
- **Prérequis.**
  - Licence Camunda pour un usage de production, ou SaaS.
  - Compte d'intégration ServiceNow en OAuth.
  - Accès API aux équipements, dans un environnement de recette.
  - Relevé de 20 à 30 tickets récents pour mesurer l'existant.
- **Livrables.**
  - Référentiel validé par les équipes.
  - Modèles en revue.
  - Workers déployés et supervisés.
  - Guide opérationnel et atelier de formation ([kit](06-kit-formation.md)).
- **Indicateurs de sortie.**
  - Délai médian mesuré, comparé au relevé initial.
  - Demandes standard sans intervention humaine (k/n).
  - Zéro écart entre la demande validée et la règle appliquée, contrôlé par la vérification.
- **Risques.**
  - Règles implicites découvertes tard : un atelier référentiel en semaine 1.
  - Résistance au changement du CAB : on commence par les seuls changements standard.

## Vague 2 (mois 3 à 6) : réutiliser les briques
- **Périmètre.** Ce sont les deux processus suivants de la matrice, qui réutilisent référentiel, intégrations et
  vérification :
  - l'ouverture de flux seule ;
  - le diagnostic d'incident réseau de niveau 1, avec l'agent de diagnostic et la validation humaine.
- **En parallèle.**
  - Un inventaire des certificats avec alerte d'expiration.
  - Le passage de l'interrogation de ServiceNow au webhook.
- **Indicateurs de sortie.**
  - Part des incidents de niveau 1 diagnostiqués avec une cause confirmée par l'opérateur (k/n).
  - Taux de remédiations refusées.
  - Coût LLM par incident.
- **Risque.** Une confiance excessive dans l'agent. La validation humaine reste obligatoire, et les
  diagnostics corrigés enrichissent le jeu d'évaluation ([gouvernance](04-gouvernance.md)).

## Vague 3 (mois 6 à 12) : élargir et industrialiser
- **Périmètre.**
  - VM à la demande hors exposition.
  - Accès VPN des prestataires.
  - Décommissionnement, qui supprime proprement ce que les vagues 1 et 2 ont créé.
  - Documentation publiée dans la base de connaissances.
- **Industrialisation.**
  - Camunda en haute disponibilité.
  - Supervision des workers.
  - Revue trimestrielle des agents.
  - Tableau de bord des indicateurs pour le propriétaire de processus.
- **Hors du moteur.** L'enregistrement DNS, simple et rare, est automatisé par un script.

## Ce qui ferait arrêter ou réorienter
- Après la vague 1, le délai médian mesuré ne baisse pas par rapport au relevé initial : il faut chercher où
  l'instance attend dans Operate, avant d'étendre.
- La part de demandes refusées ou reprises à la main dépasse un seuil convenu avec le métier : le référentiel
  ou le formulaire sont à revoir.
- Les évaluations d'un agent baissent après un changement de modèle : on garde l'ancien, ou on retire l'agent.
  Le processus fonctionne sans lui (formulaire, gabarit).
