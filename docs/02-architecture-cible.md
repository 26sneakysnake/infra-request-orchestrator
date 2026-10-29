# Architecture cible

> NetCo est fictive. Le laboratoire remplace chaque système d'entreprise par un équivalent local, nommé comme
> tel : kind pour la plateforme de conteneurs, vcsim (simulateur de l'API vSphere) pour la virtualisation, des
> NetworkPolicy pour le pare-feu.

## Le processus cible
![Exposition d'un service, cible](img/expose_service.svg)

Le modèle exécutable est `bpmn/expose_service.bpmn`.
- **Les humains n'interviennent qu'à trois endroits** : la réponse du demandeur quand il manque une
  information, l'approbation du CAB pour un changement normal ou urgent, et la validation d'une remédiation.
- **Tout le reste est automatique et tracé dans Camunda.** Cela couvre la qualification, la conformité, le
  classement, les tickets, le provisionnement de la plateforme et de la VM en parallèle, la vérification, la
  documentation et la clôture.

## Composants
| Composant | Rôle | Laboratoire | Cible réelle |
|---|---|---|---|
| ServiceNow | Demande (catalogue), changement, communication avec le demandeur | Instance développeur personnelle | Instance de l'entreprise, compte d'intégration dédié en OAuth |
| Camunda 8 | Orchestration, historique, tâches humaines (Operate, Tasklist) | Docker Compose « léger », sans authentification | Self-Managed avec licence de production, ou SaaS |
| Workers Python | Intégrations et agents, un handler par type de tâche | Un processus local | Conteneurs déployés et supervisés |
| Référentiel | Règles de nommage, ports, zones, VM, runbooks | YAML et Markdown versionnés | Identique, revu par pull request |
| Table DMN | Classe du changement : standard, normal ou urgent | `change_class.dmn` | Identique, propriété du CAB |
| Jira | Ticket de travaux, lien vers le changement | Jira Cloud gratuit | Jira de l'entreprise |
| Plateforme de conteneurs | Déploiement, Service, règle d'accès | kind et NetworkPolicy | Plateforme de l'entreprise, plus l'API du pare-feu |
| Virtualisation | VM à la demande | vcsim, l'API vSphere simulée | Plateforme de virtualisation de l'entreprise |
| Agents IA | Qualification, diagnostic, documentation | API Anthropic, réponses enregistrées pour la CI | Identique, avec le même plafond de coût et les mêmes évaluations |

## Principes de conception
- **L'IA propose, le processus décide.** La conformité vient du référentiel, la classe du changement de la DMN,
  et toute correction d'une validation humaine.
- **Une livraison au moins une fois, donc des handlers idempotents.**
  - Le changement est retrouvé par `correlation_id`, le ticket Jira par un label.
  - Les objets Kubernetes passent par un *server-side apply*.
  - La VM est retrouvée par son nom, et les pièces jointes par leur nom de fichier.
- **Deux sortes d'échec.**
  - Une erreur technique est relancée trois fois, puis devient un incident dans Operate.
  - Un échec métier (la vérification réseau) est une erreur BPMN modélisée, qui suit son propre chemin :
    diagnostic, puis validation.
- **Tout est versionné et testé** : modèles, règles, prompts, cas d'évaluation et résultats. Voir la
  [gouvernance](04-gouvernance.md).

## Intégration
- **Entrée.**
  - Dans le laboratoire, ServiceNow est interrogé toutes les 10 s, faute d'adresse publique.
  - En cible, une règle métier ServiceNow appelle un webhook. Un connecteur entrant Camunda démarre l'instance, en
    gardant le numéro de la demande comme identifiant métier.
- **Sorties.** Elles passent par des API REST : Table, Change Management et Attachment pour ServiceNow, l'API v3
  pour Jira, l'API Kubernetes et l'API vSphere.
- **Corrélation.** La réponse du demandeur est un message Camunda corrélé par le numéro de la demande, avec un
  délai de 72 h.
- **Secrets.** Ils sont dans des variables d'environnement, jamais dans le dépôt. En cible, ils iraient dans le
  coffre de l'entreprise.

## Choisir l'outil d'orchestration : Camunda, n8n ou des scripts
| Critère | Camunda 8 | n8n | Scripts (Python, planificateur) |
|---|---|---|---|
| Modèle lisible par le métier | BPMN et DMN, des standards relus par le CAB | Graphe de nœuds propre à l'outil | Code |
| Tâches humaines, formulaires | Natifs (Tasklist) | Possibles (attente, formulaire), sans gestion de groupes avancée | À développer |
| Attentes longues (72 h, CAB) | État persistant, minuteries, messages | Exécutions en attente, moins outillées | À développer (base, reprise) |
| Historique, audit, incidents | Operate : chaque étape datée, relance en un clic | Journal des exécutions | Journaux à construire |
| Versions des modèles | Chaque instance finit sur sa version | Une version active par workflow | Celle du dépôt |
| Mise en route | Plus lourde : moteur, Elasticsearch ou base, compétences BPMN | Rapide, centaines d'intégrations prêtes | Immédiate |
| Licence | Self-Managed gratuit hors production ; licence Enterprise exigée pour un usage de production depuis la 8.6 ([licences](https://docs.camunda.io/docs/reference/licenses/)) | Auto-hébergement gratuit pour un usage interne, sous Sustainable Use License ([licence](https://docs.n8n.io/privacy-and-security/sustainable-use-license/)) | Aucune |

**Recommandation.**
- **Camunda** pour les processus qui traversent plusieurs équipes, durent des jours et comportent des décisions
  humaines ou réglementées : exposition, ouverture de flux, incidents.
- **Des scripts** pour une automatisation simple, propre à une seule équipe, sans décision (l'enregistrement
  DNS).
- **n8n** reste défendable comme colle de notification entre outils. Mieux vaut pourtant ne pas multiplier les
  plateformes : un deuxième moteur, c'est un deuxième socle à exploiter et à gouverner.
- **Le coût de licence** est à chiffrer avec l'éditeur avant la vague 1 ([feuille de route](03-feuille-de-route.md)).

## Agents IA : des workers Python plutôt que le connecteur AI Agent
| Agent | Rôle | Outils | Garde-fou principal |
|---|---|---|---|
| Qualification | Texte libre vers formulaire, questions au demandeur | Recherche dans le référentiel (lecture) | Le formulaire l'emporte ; conformité vérifiée par le référentiel ; citations contrôlées |
| Diagnostic | Cause d'un échec de vérification, et une action de la liste fermée | Lecture d'un instantané figé, runbooks | Validation humaine avant toute action |
| Documentation | Fiche de service et compte rendu de changement | Aucun (un seul appel) | Contrôle des valeurs ; gabarit en secours |

Camunda 8.10 propose un connecteur AI Agent, qui rend chaque appel d'outil visible dans Operate. Le projet a
préféré des workers, pour trois raisons :
- **la reproductibilité** : réponses enregistrées, rejouées en CI sans clé ;
- **l'évaluation directe** sur des cas figés ;
- **des contrôles déterministes** écrits dans le même code que l'appel.

Le détail de chaque choix et ses paramètres sont dans l'[annexe sur les agents](annexe-agents.md). Les
résultats sont dans `results/`.
