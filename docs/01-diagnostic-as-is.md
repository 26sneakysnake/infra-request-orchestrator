# Diagnostic de l'existant : l'exposition d'un service

> NetCo est une entreprise **fictive**. Le traitement décrit ici est un traitement manuel plausible, construit pour
> le projet. Ses ordres de grandeur sont des **hypothèses déclarées** (`hypotheses/as-is.yaml`), pas des
> mesures. Ils sont à remplacer par un relevé de tickets réels avant toute décision.

## Périmètre
Une équipe demande qu'un service soit joignable depuis certaines zones du réseau, parfois avec une VM. La demande
va de l'expression du besoin jusqu'aux tickets clos. Elle traverse cinq acteurs : le demandeur, le service desk,
l'équipe réseau, le CAB, et les équipes plateforme et virtualisation.

## Cartographie
![Exposition d'un service, existant](img/expose_service_as_is.svg)

Le modèle (`bpmn/as-is/expose_service_as_is.bpmn`, non exécutable) compte 9 étapes, toutes manuelles (AS-01 à
AS-09). Il y a au moins 6 passages de relais entre équipes, et deux boucles d'attente : les allers-retours avec
le demandeur, et le CAB.

| Demande | Étapes | Effort humain supposé | Délai calendaire supposé |
|---|---|---|---|
| Standard, sans VM | 7 | 185 min | 3 à 12 jours ouvrés |
| Normale (CAB), avec VM | 9 | 240 min | 4 à 20 jours ouvrés |

Ces totaux sont recalculés par `make metrics` (section `as_is_hypotheses` de `results/metrics.json`).

## Irritants
1. **Demande en texte libre.** Il manque souvent l'environnement, le port ou la zone source, d'où des
   allers-retours (AS-02). C'est l'étape dont le délai varie le plus.
2. **Règles vérifiées de tête.** La conformité (ports interdits, zones, nommage) dépend de l'expert présent. Aucun
   référentiel n'est lisible par une machine.
3. **CAB hebdomadaire pour tout changement normal**, y compris répétitif et à faible risque : jusqu'à une semaine
   d'attente.
4. **Double saisie.** La règle de pare-feu et le déploiement sont ressaisis à la main depuis le ticket : un écart
   entre la demande et la règle appliquée passe inaperçu.
5. **Vérification non tracée.** Le test de flux est manuel, et son résultat n'est rattaché à rien.
6. **Documentation reportée.** La fiche de service et le compte rendu de changement manquent, ou ne
   correspondent plus à la réalité.
7. **Aucune vue de bout en bout.** La demande, le changement et le ticket de travaux vivent dans trois outils.
   Le demandeur ne sait pas où en est sa demande.
8. **Rien n'est mesuré.** Personne ne connaît le délai réel ni l'endroit où il se perd.

## Priorisation de 8 processus du département
Scores de 1 à 5, déclarés par hypothèse pour NetCo :
- **fréquence** : volume mensuel ;
- **effort** : temps humain et allers-retours par demande ;
- **risque** : conséquence d'une erreur ou d'un oubli (panne, faille, non-conformité).

Le score est le produit des trois (125 au plus).

| Processus | Fréquence | Effort | Risque | Score |
|---|---|---|---|---|
| Exposition d'un service | 4 | 4 | 4 | 64 |
| Ouverture de flux pare-feu seule | 5 | 3 | 4 | 60 |
| Diagnostic d'incident réseau de niveau 1 | 5 | 4 | 3 | 60 |
| Renouvellement de certificat TLS | 3 | 2 | 5 | 30 |
| Création de VM seule | 4 | 3 | 2 | 24 |
| Accès VPN d'un prestataire | 3 | 2 | 4 | 24 |
| Décommissionnement d'un service | 2 | 3 | 4 | 24 |
| Enregistrement DNS | 4 | 1 | 2 | 8 |

**Lecture.**
- **L'exposition d'un service passe en premier.** Elle est fréquente et coûteuse. Elle couvre aussi les briques
  dont les autres processus ont besoin : référentiel, intégration ServiceNow et Jira, provisionnement,
  vérification.
- **Les flux seuls et le diagnostic de niveau 1 réutilisent ces briques.** Ils forment la vague 2
  ([feuille de route](03-feuille-de-route.md)).
- **Les certificats ont un risque élevé pour un effort faible.** Ils relèvent d'abord d'un inventaire et d'une
  alerte, plus que d'un processus orchestré.
- **Le DNS, rare et simple, n'a pas besoin d'un moteur de processus.** Un script suffit.

## Ce qu'il faut valider sur le terrain
- Relever 20 à 30 tickets récents par processus, pour remplacer les hypothèses par des délais mesurés (création,
  premier traitement, clôture) et compter les allers-retours.
- Mener un entretien d'une heure par équipe, pour confirmer la cartographie, les irritants et les règles
  implicites à écrire dans le référentiel.
- Revoir les scores de la matrice avec les responsables d'équipe : ils sont déclaratifs et doivent être
  contestés.
