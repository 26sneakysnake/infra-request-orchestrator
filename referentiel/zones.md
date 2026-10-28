# Zones réseau

## ZONE-01 : réseaux sources
Une demande indique les réseaux autorisés à joindre le service, en notation CIDR. Chaque réseau doit appartenir à
une zone NetCo connue :

| Zone | CIDR | Contenu |
|---|---|---|
| dev | 10.20.0.0/16 | Postes et outils des équipes de développement |
| data | 10.30.0.0/16 | Plateformes data et reporting |
| finance | 10.40.12.0/24 | Applications de la direction financière |
| bureautique | 10.50.0.0/16 | Postes bureautiques |
| internet | 0.0.0.0/0 | Internet, pour l'exposition externe uniquement |

Un réseau plus petit que sa zone (par exemple 10.20.5.0/24) est accepté et ouvre l'accès à toute la zone : la
règle réseau est posée au niveau de la zone.

## ZONE-02 : Internet
La zone `internet` (0.0.0.0/0) n'est acceptée que pour une exposition `externe`.

## Traduction en règle réseau
Le pare-feu est modélisé par une NetworkPolicy Kubernetes sur le service : elle n'autorise que les zones demandées,
et seulement sur le port demandé. Tout le reste est bloqué. Dans le laboratoire, chaque zone est un namespace
`zone-<nom>` qui contient une sonde, ce qui permet de vérifier qu'une zone autorisée passe et qu'une autre est
bloquée.
