# Machines virtuelles

> NetCo est une entreprise fictive. Dans le laboratoire, les VM sont créées sur vcsim, le simulateur de l'API
> vSphere : elles répondent à l'API mais n'exécutent rien.

## VM-01 : machines virtuelles
Une demande peut réclamer une VM en plus de l'exposition du service. Elle doit alors préciser une taille :

| Taille | vCPU | Mémoire (Mo) |
|---|---|---|
| S | 1 | 2048 |
| M | 2 | 4096 |
| L | 4 | 8192 |

La VM est rangée dans le dossier `netco/<environnement>`, s'appelle `<service>-<environnement>-vm` et se
connecte au réseau `VM Network`. Une VM demandée sans taille S, M ou L rend la demande non conforme.
