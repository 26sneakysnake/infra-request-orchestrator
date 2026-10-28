# Référentiel NetCo

> NetCo est une entreprise fictive. Ce référentiel est inventé pour la démonstration.

Règles qu'une demande d'exposition de service doit respecter avant d'être traitée. Chaque règle porte un
identifiant stable (`NOM-01`, `PORT-02`…) : le processus le cite quand il refuse une demande, et l'agent de
qualification (phase P3) le citera quand il s'appuie sur une règle.

| Fichier | Contenu |
|---|---|
| [nommage.md](nommage.md) | Noms de services et de namespaces, environnements, types d'exposition |
| [ports.md](ports.md) | Ports interdits, autorisés et sensibles |
| [zones.md](zones.md) | Zones réseau sources et leur traduction en règles réseau |
| [securite.md](securite.md) | Classement des changements et approbations |

Les valeurs lues par le code sont dans [netco.yaml](netco.yaml). En cas d'écart, `netco.yaml` fait foi ; un test
vérifie que chaque valeur y figure aussi dans ces pages.
