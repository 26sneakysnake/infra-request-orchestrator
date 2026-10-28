# Ports

## PORT-01 : ports interdits
Ces ports ne sont jamais ouverts par une demande d'exposition, quel que soit l'environnement :

| Port | Service | Raison |
|---|---|---|
| 21 | FTP en clair | Identifiants transmis en clair |
| 22 | SSH | L'administration passe par le bastion, pas par une exposition de service |
| 23 | Telnet | Protocole non chiffré |
| 445 | SMB | Surface d'attaque connue (rançongiciels) |
| 3389 | RDP | Bureau à distance : accès prestataire par le bastion uniquement |

## PORT-02 : ports autorisés
- Exposition interne : 443, 3306, 5432, 6379, 8080, 8443, 9090.
- Exposition externe : 443 uniquement (HTTPS).

Un port qui n'est ni interdit ni autorisé demande une dérogation, hors du périmètre de ce processus.

## PORT-03 : un seul port par demande
Limite de la démonstration : une demande expose un seul port. Plusieurs ports donnent plusieurs demandes.

## PORT-04 : protocole
Seul TCP est pris en charge (`443/tcp`).

## PORT-05 : ports sensibles
Les ports de bases de données et de caches (3306 MySQL, 5432 PostgreSQL, 6379 Redis) sont sensibles : même en
interne et hors production, leur ouverture passe par une approbation (voir [securite.md](securite.md)).
